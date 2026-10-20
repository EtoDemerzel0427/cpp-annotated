---
title: 并发编程实战
summary: 在内存模型之上写真正的并发代码：用 jthread、条件变量和 packaged_task 搭一个能传递异常、能干净关闭的线程池，std::async 的两个意外，有界队列与无锁 SPSC 环形缓冲区，同步原语怎么选，并行算法和 std::execution，以及死锁、丢失唤醒、shared_ptr 竞争等常见错误，全部用 Clang 23 和 TSan 验证。
status: draft
order: 86
since: c++11
papers: P0660R10, P1135R6, P0024R2, P2300R10, P2079R10, P2530R3, P2545R4, P0718R2
related: futures.async, futures.state, futures.task.members, thread.jthread.cons, thread.stoptoken, thread.condition.condvar, thread.condvarany.intwait, thread.lock.scoped, thread.sharedmutex.requirements.general, thread.sema.cnt, thread.barrier.class, algorithms.parallel.exec, execpol.par, exec, saferecl, stmt.dcl, util.smartptr.shared.general, topics/memory-model, perf/false-sharing, patterns/observer, topics/ownership-and-smart-pointers
tags: 并发, 线程池, 条件变量, future, 无锁, 并行算法, TSan, 专题
updated: 2026-10-19
---

!!! tldr
    - 线程池的骨架是一把互斥量、一个条件变量和一个任务队列；`std::packaged_task` 把任务的返回值和异常都存进共享状态，`future::get()` 在调用方重新抛出。
    - `std::async` 返回的 `future` 如果被丢弃，析构时会阻塞到任务完成；默认策略还允许任务延迟到 `get()` 时才在调用线程上执行。
    - 等条件变量时总要带谓词：通知可能早于等待，等待也可能无故醒来。
    - 单生产者单消费者的环形缓冲区只需两个原子下标和 acquire/release；多生产者多消费者的无锁结构难在 ABA 和内存回收，标准为此提供了 hazard pointer 和 RCU。
    - 死锁靠固定加锁顺序或 `std::scoped_lock` 一次锁多个来避免；`shared_ptr` 的引用计数是线程安全的，同一个 `shared_ptr` 对象和它指向的对象都不是。

[[topics/memory-model|内存模型实战]]讲的是规则：什么是[[g:data-race|数据竞争]]（两个线程访问同一内存位置，至少一个是写，至少一个不是原子操作，两者之间又没有 [[g:happens-before|happens before]]，行为未定义，[[intro.races#17]]），以及 acquire/release 怎样建立 happens before。在这些规则之上，写实际的并发组件还要解决另一类问题：任务怎样交接，结果和异常怎样传回，线程怎样关闭，以及怎样避开死锁和丢失唤醒。

下文的例子都在本机（Apple M2 Pro，12 核，macOS，Homebrew Clang 23 + libc++）上用 `-std=c++2c` 编译，多线程的例子都在 `-fsanitize=thread`（ThreadSanitizer，下称 TSan）下运行过。写作时机器负载很高（`uptime` 的 load average 在 50 到 190 之间），所有计时都只能看数量级。

## 一个线程池

### 设计

**线程池**（thread pool）预先创建一组工作线程，它们反复从共享的任务队列里取任务执行。提交任务的线程把任务放进队列，拿回一个 `std::future`，以后用它取结果。

这需要回答四个问题：

1. 队列由谁保护？一把 `std::mutex`。
2. 队列空时工作线程怎么等？在条件变量上睡眠，有新任务时被唤醒。
3. 返回值和异常怎么交回提交者？`std::packaged_task`。
4. 怎么关闭？`std::jthread` 自带的停止令牌（stop token）。

`std::packaged_task<R()>` 包装一个可调用对象，并拥有一个[[g:shared-state|共享状态]]（shared state），即提供结果的一方与读取结果的一方共用的一块存储。调用它时，函数正常返回就把返回值存入共享状态，抛出异常就把异常存入，然后把状态标记为就绪（[[futures.task.members#22]]）。`get_future()` 返回连接同一共享状态的 `std::future<R>`；`get()` 等到就绪后取出值，存的是异常就重新抛出（[[futures.unique.future#19]]）。

`std::jthread`（C++20，[[P0660R10]]）与 `std::thread` 有两点不同。如果线程函数的第一个形参可以接受 `std::stop_token`，构造函数会把自己的停止令牌传进去（[[thread.jthread.cons#6]]）；析构时，如果线程还可汇合，先 `request_stop()` 再 `join()`（[[thread.jthread.cons#12]]），不会像 `std::thread` 那样调用 `std::terminate`。

### 代码

```cpp title="pool.hpp"
#pragma once
#include <condition_variable>
#include <deque>
#include <functional>
#include <future>
#include <memory>
#include <mutex>
#include <thread>
#include <type_traits>
#include <vector>

class ThreadPool {
public:
  explicit ThreadPool(unsigned n) {
    for (unsigned i = 0; i < n; ++i)
      workers_.emplace_back([this](std::stop_token st) { run(st); });
  }
  ~ThreadPool() {
    for (auto& w : workers_) w.request_stop();
    for (auto& w : workers_) w.join();  // 等队列排空
  }

  template<class F, class... Args>
  auto submit(F&& f, Args&&... args) {
    using R = std::invoke_result_t<std::decay_t<F>,
                                   std::decay_t<Args>...>;
    auto task = std::make_shared<std::packaged_task<R()>>(
        std::bind_front(std::forward<F>(f),
                        std::forward<Args>(args)...));
    std::future<R> fut = task->get_future();
    {
      std::scoped_lock lock(m_);
      q_.emplace_back([task] { (*task)(); });
    }
    cv_.notify_one();
    return fut;
  }

private:
  void run(std::stop_token st) {
    for (;;) {
      std::function<void()> job;
      {
        std::unique_lock lock(m_);
        // 有任务就返回 true；收到停止请求且队列已空才返回 false
        if (!cv_.wait(lock, st, [&] { return !q_.empty(); }))
          return;
        job = std::move(q_.front());
        q_.pop_front();
      }
      job();  // 锁外执行；异常已被 packaged_task 截获
    }
  }

  std::mutex m_;
  std::condition_variable_any cv_;
  std::deque<std::function<void()>> q_;
  std::vector<std::jthread> workers_;
};
```

```cpp title="pool-demo.cpp" run ok
#include "pool.hpp"
#include <cstdio>
#include <stdexcept>
int main() {
  ThreadPool pool(4);
  auto a = pool.submit([](int x, int y) { return x + y; }, 2, 3);
  auto b = pool.submit([] {
    throw std::runtime_error("task failed");
  });
  std::vector<std::future<long>> parts;
  for (long i = 0; i < 8; ++i)
    parts.push_back(pool.submit([i] {
      long s = 0;
      for (long k = i * 1000; k < (i + 1) * 1000; ++k) s += k;
      return s;
    }));
  std::printf("a = %d\n", a.get());
  try {
    b.get();
  } catch (const std::exception& e) {
    std::printf("b threw: %s\n", e.what());
  }
  long total = 0;
  for (auto& p : parts) total += p.get();
  std::printf("total = %ld\n", total);
}
```

```text
a = 5
b threw: task failed
total = 31996000
```

另一个压力测试让 4 个线程同时各提交 2 万个任务，随即销毁线程池，再逐个 `get()`。TSan 和 ASan 构建下都没有报告，8 万个任务全部执行。

### 逐行看关键之处

#### 任务为什么包在 `shared_ptr` 里

`packaged_task` 只能移动，不能复制，而 `std::function` 要求可调用对象可复制。C++23 的 `std::move_only_function`（[[func.wrap.move]]）可以直接存放 `packaged_task`，省掉这次分配，但本机 libc++ 还没有它。

#### 为什么用 `condition_variable_any`

带 `stop_token` 的 `wait` 重载只有 `condition_variable_any` 才有（[[thread.condvarany.intwait#2]]）。它在等待期间注册一个回调，停止请求到来时唤醒自己，然后等价于：

```cpp
while (!stoken.stop_requested()) {
  if (pred()) return true;
  wait(lock);
}
return pred();
```

所以收到停止请求后，只要队列里还有任务，`wait` 仍返回 `true`，工作线程会先把队列取空，最后一次 `pred()` 为假才退出。已经提交的 `future` 都能得到结果。如果改用 `std::condition_variable`，就得自己维护一个 `stopping_` 标志，在锁内设置它再 `notify_all`。

#### 为什么在锁外执行任务

持锁运行任务会让其他工作线程都排队等这把锁，池退化成单线程。任务里如果再调用 `submit`，还会在同一把非递归锁上自我死锁。

#### 异常去了哪里

任务抛出的异常被 `packaged_task::operator()` 存入共享状态，不会离开 `job()`。这一点很重要：线程函数如果因异常退出，`jthread` 会调用 `std::terminate`（[[thread.jthread.cons#6]]）。

#### 析构函数为什么自己 `join`

先对所有线程 `request_stop()`，让它们同时开始收尾，再逐个 `join()`。这样 `m_`、`cv_`、`q_` 在所有工作线程结束之后才销毁。

!!! pitfall "依赖成员的析构顺序"
    如果析构函数只调用 `request_stop()`，把 `join` 交给 `jthread` 的析构函数，那么 `workers_` 必须声明在最后。成员按声明的逆序销毁，把 `workers_` 放在 `m_` 前面，`m_` 就会先于 `join` 销毁，而工作线程还在用它。本机这样改写后，压力测试的工作线程抛出 `std::system_error`（"mutex lock failed: Invalid argument"）并终止程序。局部变量也一样：被线程引用的互斥量要声明在 `jthread` 之前。

!!! note "任务没有执行就被丢弃"
    如果某个实现选择不排空队列，直接销毁剩余任务，`packaged_task` 的析构函数会放弃（abandon）它的共享状态：存入一个错误码为 `broken_promise` 的 `future_error`，再标记为就绪（[[futures.state#7]]）。等待它的 `get()` 会抛出这个异常，不会永远阻塞。

## 基于任务还是基于线程

直接为每件工作创建一个 `std::thread`，是**基于线程**的设计：工作和执行它的线程一一绑定，调用者要负责 `join`、负责把结果和异常传回来。**基于任务**的设计只描述要做的工作，交给线程池、`std::async` 或调度器决定在哪里运行，结果通过 `future` 之类的对象取回。

后者通常更好：线程数可以按核心数固定，创建线程的开销被摊薄，异常传递也有现成的机制。本机创建一个线程再 `join` 约 13 µs，线程池交接一个任务约 0.9 到 3 µs，测量见 [[perf/false-sharing|多线程下的性能]]的最后一节。

`std::async` 看起来是基于任务的捷径，但有两处行为常让人意外。

### 被丢弃的 future 会阻塞

```cpp title="async.cpp" run ok
#include <chrono>
#include <cstdio>
#include <future>
#include <thread>
using namespace std::chrono;
void work() { std::this_thread::sleep_for(milliseconds(200)); }
long ms_since(steady_clock::time_point t0) {
  return duration_cast<milliseconds>(steady_clock::now() - t0).count();
}
int main() {
  auto t0 = steady_clock::now();
  std::async(std::launch::async, work);   // 临时 future 在这一行末尾析构
  std::async(std::launch::async, work);
  std::printf("discarded futures: %ld ms\n", ms_since(t0));

  t0 = steady_clock::now();
  auto f1 = std::async(std::launch::async, work);
  auto f2 = std::async(std::launch::async, work);
  f1.get(); f2.get();
  std::printf("kept futures:      %ld ms\n", ms_since(t0));
}
```

```text
discarded futures: 410 ms
kept futures:      205 ms
```

两个任务没有并发。`std::async` 返回的临时 `future` 在完整表达式结束时析构，析构要释放（release）共享状态。一般的释放不会阻塞，但 [[futures.state#5]] 第 5.3 项留了一个例外：共享状态由 `std::async` 创建、尚未就绪、而这是最后一个引用时，释放可以阻塞。再加上 [[futures.async#4]] 第 4.1 项要求等待 `async` 线程的结果时要像 `join` 一样等它结束，实际效果就是析构函数等任务做完。[[futures.async#5]] 的注 2 也提醒了这一点。

libc++ 给 `std::async` 加了 `[[nodiscard]]`，上面两行会得到 `-Wunused-result` 警告。标准本身没有这样要求。`std::promise` 和 `std::packaged_task` 给出的 `future` 析构时从不阻塞，线程池的 `future` 丢掉就丢掉了。

### 默认策略可能不并发

不带策略参数的 `std::async(f)` 等价于传入 `launch::async | launch::deferred`，实现可以任选其一（[[futures.async#3]]）。选 `deferred` 时，函数被保存起来，直到第一次调用 `get()` 或 `wait()` 时才在调用线程上执行（第 3.2 项）。标准自己的例子（[[futures.async#8]]）指出这样可能完全没有并发。

本机 libc++ 对默认策略选择了新线程。但依赖这一点的代码在别的实现上可能出错，典型的是轮询：

```cpp
auto f = std::async(task);
while (f.wait_for(0s) != std::future_status::ready) {
  do_other_work();   // 若任务被延迟，wait_for 永远返回 deferred，循环不会结束
}
```

需要并发就显式写 `std::launch::async`；需要更多控制（线程数、取消、优先级）就用线程池。

## 两种队列

### 有界的多生产者多消费者队列

线程池的队列没有上限，生产者太快时会无限增长。**有界队列**在满时让生产者等待，形成背压。它需要两个条件变量：消费者等不空，生产者等不满。

```cpp title="bounded.hpp"
#pragma once
#include <condition_variable>
#include <cstddef>
#include <deque>
#include <mutex>
#include <optional>

template<class T>
class BoundedQueue {
public:
  explicit BoundedQueue(std::size_t cap) : cap_(cap) {}

  // 返回 false 表示队列已关闭
  bool push(T v) {
    std::unique_lock lock(m_);
    not_full_.wait(lock, [&] { return closed_ || q_.size() < cap_; });
    if (closed_) return false;
    q_.push_back(std::move(v));
    lock.unlock();
    not_empty_.notify_one();
    return true;
  }

  // 返回 nullopt 表示队列已关闭且取空
  std::optional<T> pop() {
    std::unique_lock lock(m_);
    not_empty_.wait(lock, [&] { return closed_ || !q_.empty(); });
    if (q_.empty()) return std::nullopt;
    T v = std::move(q_.front());
    q_.pop_front();
    lock.unlock();
    not_full_.notify_one();
    return v;
  }

  void close() {
    { std::scoped_lock lock(m_); closed_ = true; }
    not_empty_.notify_all();
    not_full_.notify_all();
  }

private:
  std::mutex m_;
  std::condition_variable not_empty_, not_full_;
  std::deque<T> q_;
  std::size_t cap_;
  bool closed_ = false;
};
```

```cpp title="bounded-test.cpp" run ok
#include "bounded.hpp"
#include <atomic>
#include <cstdio>
#include <thread>
#include <vector>
int main() {
  constexpr int producers = 4, consumers = 4, per = 50000;
  BoundedQueue<int> q(64);
  std::atomic<long> sum{0}, count{0};
  {
    std::vector<std::jthread> cs;
    for (int c = 0; c < consumers; ++c)
      cs.emplace_back([&] {
        while (auto v = q.pop()) {
          sum.fetch_add(*v, std::memory_order::relaxed);
          count.fetch_add(1, std::memory_order::relaxed);
        }
      });
    {
      std::vector<std::jthread> ps;
      for (int p = 0; p < producers; ++p)
        ps.emplace_back([&, p] {
          for (int i = 0; i < per; ++i) q.push(p * per + i);
        });
    }            // 生产者全部 join
    q.close();   // 消费者取空后退出
  }
  long n = long(producers) * per;
  std::printf("count %ld, sum %ld, expected %ld\n",
              count.load(), sum.load(), n * (n - 1) / 2);
}
```

```text
count 200000, sum 19999900000, expected 19999900000
```

TSan 下运行没有报告。几个细节：

- `notify_one` 放在解锁之后。放在锁内也正确，只是被唤醒的线程可能立刻撞上还没释放的锁。
- `close()` 用 `notify_all`，因为所有在等的线程都需要看到 `closed_`。
- `pop` 在关闭后仍把剩余元素取完，`nullopt` 只表示关闭且已空。
- 计数用 relaxed 的 `fetch_add` 就够了：它们不用来发布别的数据，最后读取发生在 `join` 之后，`join` 提供了同步。

### 无锁的单生产者单消费者环形缓冲区

只有一个生产者和一个消费者时，可以不用锁。缓冲区是一个固定大小的数组，生产者写 `tail_`，消费者写 `head_`，各自只读对方的下标：

```cpp title="spsc.hpp"
#pragma once
#include <atomic>
#include <cstddef>
#include <new>

template<class T, std::size_t N>   // N 是 2 的幂
class SpscRing {
  static_assert(N > 0 && (N & (N - 1)) == 0);
  static constexpr std::size_t line =
      std::hardware_destructive_interference_size;
  alignas(line) std::atomic<std::size_t> head_{0};  // 只有消费者写
  alignas(line) std::atomic<std::size_t> tail_{0};  // 只有生产者写
  alignas(line) T buf_[N];

public:
  bool push(const T& v) {                  // 只能由生产者线程调用
    std::size_t t = tail_.load(std::memory_order::relaxed);
    std::size_t h = head_.load(std::memory_order::acquire);
    if (t - h == N) return false;          // 满
    buf_[t % N] = v;
    tail_.store(t + 1, std::memory_order::release);
    return true;
  }
  bool pop(T& out) {                       // 只能由消费者线程调用
    std::size_t h = head_.load(std::memory_order::relaxed);
    std::size_t t = tail_.load(std::memory_order::acquire);
    if (t == h) return false;              // 空
    out = buf_[h % N];
    head_.store(h + 1, std::memory_order::release);
    return true;
  }
};
```

下标只增不减，`t - h` 是元素个数；`size_t` 回绕后无符号减法仍然正确，所以 `N` 取 2 的幂，让 `% N` 在回绕前后一致。

每个内存序都有它的理由，推理方法见[[topics/memory-model|内存模型实战]]：

| 操作 | 内存序 | 理由 |
|---|---|---|
| `push` 读自己的 `tail_` | relaxed | 只有本线程写它，读到的一定是自己上次写的值 |
| `push` 写 `tail_` | release | 发布槽位：之前对 `buf_[t % N]` 的写要对读到新 `tail_` 的消费者可见 |
| `pop` 读 `tail_` | acquire | 与上一行配对；读到 `t + 1` 后，读槽位与生产者的写之间有 happens before |
| `pop` 写 `head_` | release | 归还槽位：之前对槽位的读要 happens before 生产者下一次写这个槽位 |
| `push` 读 `head_` | acquire | 与上一行配对；否则生产者覆盖槽位可能与消费者还没完成的读构成数据竞争 |

两对 release/acquire 各管一个方向：`tail_` 把数据从生产者交给消费者，`head_` 把空槽位还给生产者。只看前者很容易漏掉后者。

`alignas` 把两个下标放在不同的缓存行上。它们分别由两个核心频繁写入，放在同一行里会互相使对方的缓存失效，这就是[[perf/false-sharing|伪共享]]。本机 `hardware_destructive_interference_size` 是 128（[[hardware.interference]]）。

用一个压力测试检查：生产者按顺序推入 500 万条消息，消费者检查顺序和内容：

```cpp title="spsc-test.cpp" run ok
#include "spsc.hpp"
#include <cstdio>
#include <thread>
struct Msg { long seq, square; };
SpscRing<Msg, 1024> ring;
int main() {
  constexpr long n = 5'000'000;
  std::jthread producer([] {
    for (long i = 0; i < n; ++i)
      while (!ring.push({i, i * i})) {}    // 满了就重试
  });
  long errors = 0;
  Msg m;
  for (long i = 0; i < n; ++i) {
    while (!ring.pop(m)) {}                // 空了就重试
    if (m.seq != i || m.square != i * i) ++errors;
  }
  std::printf("errors: %ld\n", errors);
}
```

逐一把某个内存序改成 relaxed，本机的结果如下（`-O2` 一列是三次运行的 `errors`）：

| 改动 | TSan | `-O2`，无 sanitizer |
|---|---|---|
| 原样 | 无报告 | 0、0、0 |
| `push` 写 `tail_` 改 relaxed | 数据竞争 | 17977、21453、13205 |
| `pop` 读 `tail_` 也改 relaxed | 数据竞争 | 7940、36732、63116 |
| `pop` 写 `head_` 改 relaxed | 数据竞争 | 0、0、0 |

最后一行说明了测试的局限：程序已经有数据竞争，在这台机器上却从不出错，因为需要的重排（消费者读槽位晚于它写 `head_`）在 arm64 上很少发生。TSan 按 happens before 推理，不依赖这次碰巧怎样执行，所以能报告。

!!! impl "TSan 也会漏报"
    把槽位换成 32 字节、由编译器生成 `memcpy` 复制的结构体时，本机 TSan 对同样错误的版本没有报告，`-O2` 运行仍然出错。TSan 只能证明它看到的访问有没有竞争，不能证明没有竞争。

无锁版本也不一定更快。本机在高负载下，同一个单生产者单消费者的传递，环形缓冲区每条消息约 34 到 42 ns，`BoundedQueue` 约 69 到 146 ns。无锁结构的主要价值往往不在吞吐，而在没有线程会因为另一个线程被挂起而卡住。

### 为什么通用的无锁 MPMC 难

允许多个线程同时修改同一个下标后，简单的 load/store 就不够了，要用 compare-exchange（CAS）。最简单的例子是无锁栈（Treiber 栈）：

```cpp title="treiber.cpp"
#include <atomic>
#include <optional>
#include <utility>

template<class T>
class Stack {
  struct Node { T value; Node* next; };
  std::atomic<Node*> head_{nullptr};
public:
  void push(T v) {
    Node* n = new Node{std::move(v), head_.load(std::memory_order::relaxed)};
    while (!head_.compare_exchange_weak(n->next, n,
               std::memory_order::release, std::memory_order::relaxed)) {}
  }
  std::optional<T> pop() {
    Node* old = head_.load(std::memory_order::acquire);
    while (old && !head_.compare_exchange_weak(old, old->next,  // ① 读 old->next
               std::memory_order::acquire, std::memory_order::acquire)) {}
    if (!old) return std::nullopt;
    T v = std::move(old->value);
    delete old;                     // ② 另一个线程可能正停在 ①
    return v;
  }
};
```

`push` 是正确的。`pop` 有两个问题：

1. **内存回收**。线程 A 读到 `old` 后被挂起；线程 B 弹出同一个节点并在 ② 处 `delete`；A 醒来在 ① 读 `old->next`，读的是已释放的内存，这是 UB。
2. **ABA**。B 弹出节点 X 和 Y、释放它们，再压入一个新节点，分配器恰好复用了 X 的地址。A 的 CAS 比较的是地址，看到 `head_` 仍是 X，于是成功，把 `head_` 设成 A 早先读到的 `X->next`，也就是已经释放的 Y。值从 A 变成 B 又变回 A，CAS 看不出区别，所以叫 ABA。

4 个线程各做 20 万次 push/pop，本机三次 ASan 运行都报告 ① 处的 heap-use-after-free，TSan 也报告 ① 处的数据竞争；不加 sanitizer 的 `-O2` 构建三次都正常结束。

根本的问题是：一个线程删除节点时，不知道其他线程是否还持有它的指针。带垃圾回收的语言没有这个问题。C++26 在 [[saferecl]] 中给了两种标准方案：

- **hazard pointer**（[[saferecl.hp.general#1]]，[[P2530R3]]）：读者在解引用前把指针登记到自己的 hazard pointer 里，删除者把节点退休（retire），只有没被任何 hazard pointer 指着的节点才真正回收。
- **RCU**（read-copy update，[[saferecl.rcu.general#1]]，[[P2545R4]]）：读者进入一个保护区，写者替换指针后把旧对象的删除推迟到所有已开始的保护区结束之后，适合读多写少的结构。

两者都推迟回收，因此节点在被引用期间地址不会被复用，ABA 也随之消失。本机 libc++ 还没有 `<hazard_pointer>` 和 `<rcu>` 头文件。在它们可用之前，除非有充分的测量依据，多生产者多消费者的场景先用 `BoundedQueue` 这样基于锁的实现。

## 选哪一种同步原语

| 需求 | 选择 | 条款 |
|---|---|---|
| 保护一段不变式（几个变量要一起改） | `std::mutex` + `std::scoped_lock`/`std::unique_lock` | [[thread.mutex.requirements.mutex.general]] |
| 读远多于写，读的临界区不短 | `std::shared_mutex` | [[thread.sharedmutex.requirements.general]] |
| 单个计数器或标志，不发布其他数据 | `std::atomic`，relaxed 的读-改-写 | [[atomics.order]] |
| 用标志发布数据 | `std::atomic`，release 写配 acquire 读 | [[atomics.order]] |
| 等某个条件成立 | 条件变量（带谓词），或 `atomic::wait` | [[thread.condition.condvar]]、[[atomics.wait]] |
| 限制同时进入的线程数 | `std::counting_semaphore` | [[thread.sema.cnt]] |
| 等 N 件事各发生一次 | `std::latch` | [[thread.latch]] |
| 多个线程分轮次同步 | `std::barrier` | [[thread.barrier.class]] |

后三种都来自 C++20（[[P1135R6]]）。它们之间的选择看的是语义，而不是速度；性能对比见[[perf/false-sharing|多线程下的性能]]，结论是只要所有线程都在更新同一处数据，换哪种原语都扩展不了。

### `shared_mutex`：多个读者，一个写者

```cpp title="shared.cpp" run ok
#include <cstdio>
#include <map>
#include <mutex>
#include <shared_mutex>
#include <string>
#include <thread>
#include <vector>
class Config {
  mutable std::shared_mutex m_;
  std::map<std::string, int> kv_;
public:
  int get(const std::string& k) const {
    std::shared_lock lock(m_);             // 多个读者可同时持有
    auto it = kv_.find(k);
    return it == kv_.end() ? -1 : it->second;
  }
  void set(const std::string& k, int v) {
    std::unique_lock lock(m_);             // 写者独占
    kv_[k] = v;
  }
};
int main() {
  Config c;
  c.set("port", 80);
  std::vector<std::jthread> ts;
  for (int i = 0; i < 4; ++i)
    ts.emplace_back([&] { for (int k = 0; k < 10000; ++k) c.get("port"); });
  ts.emplace_back([&] { for (int k = 0; k < 100; ++k) c.set("port", k); });
  ts.clear();                              // join 全部线程
  std::printf("%d\n", c.get("port"));
}
```

共享锁可以被多个线程同时持有，但与独占锁互斥（[[thread.sharedmutex.requirements.general#2]]）。读者之间仍然要原子地修改锁内部的计数，临界区很短时，`shared_mutex` 常常不比普通 `mutex` 快。标准也没有规定读者和写者谁优先，持续不断的读者是否会饿死写者取决于实现。

### `counting_semaphore`：限制并发数

```cpp title="sema.cpp" run ok
#include <atomic>
#include <cstdio>
#include <semaphore>
#include <thread>
#include <vector>
std::counting_semaphore<3> slots(3);       // 最多 3 个线程同时进入
std::atomic<int> inside{0}, peak{0};
void download(int) {
  slots.acquire();
  int now = inside.fetch_add(1) + 1;
  int p = peak.load();
  while (now > p && !peak.compare_exchange_weak(p, now)) {}
  std::this_thread::sleep_for(std::chrono::milliseconds(10));
  inside.fetch_sub(1);
  slots.release();
}
int main() {
  std::vector<std::jthread> ts;
  for (int i = 0; i < 12; ++i) ts.emplace_back(download, i);
  ts.clear();
  std::printf("peak concurrency: %d\n", peak.load());
}
```

信号量维护一个计数器：`acquire` 在计数为正时减一，否则阻塞；`release` 加一并唤醒等待者（[[thread.sema.cnt#1]]）。与互斥量不同，它没有所有者，`release` 可以由另一个线程调用，所以也能用作线程间的通知。`std::binary_semaphore` 是 `counting_semaphore<1>`。

### `barrier`：分轮次的计算

```cpp title="barrier.cpp" run ok
#include <barrier>
#include <cstdio>
#include <thread>
#include <vector>
int main() {
  constexpr int n = 4, steps = 3;
  std::vector<int> cur(n, 1), next(n);
  int step = 0;
  auto on_phase_done = [&]() noexcept {    // 每轮全部到达后，由一个线程执行
    cur.swap(next);
    std::printf("step %d: %d %d %d %d\n", ++step, cur[0], cur[1], cur[2], cur[3]);
  };
  std::barrier sync(n, on_phase_done);
  std::vector<std::jthread> ts;
  for (int i = 0; i < n; ++i)
    ts.emplace_back([&, i] {
      for (int s = 0; s < steps; ++s) {
        next[i] = cur[i] + cur[(i + 1) % n] + i;  // 读上一轮，写自己的元素
        sync.arrive_and_wait();
      }
    });
}
```

```text
step 1: 2 3 4 5
step 2: 5 8 11 10
step 3: 13 20 23 18
```

每个线程读 `cur`、写 `next[i]`，然后到达屏障。所有线程到达后，恰好一个线程执行完成函数，交换两个数组，然后所有线程继续下一轮。没有数据竞争是因为：每次 `arrive` strongly happens before 本轮完成步骤的开始（[[thread.barrier.class#14]]），完成步骤的结束 strongly happens before 被它解除阻塞的调用的返回（[[thread.barrier.class#3]]）。

!!! impl "本机 TSan 对 barrier 误报"
    本机 TSan 对这段程序报告 `swap` 与工作线程读 `cur` 之间的数据竞争。按上面两条同步规则，程序没有竞争。libc++ 的 `<barrier>` 把到达算法声明为动态库导出的函数（`__arrive_barrier_algorithm_base`），这部分代码没有经过 TSan 插桩，推测 TSan 因此看不到其中的同步。`std::latch` 的例子见[[topics/memory-model|内存模型实战]]。

## 并行算法

C++17 给大多数标准算法加了接受**执行策略**的重载（[[P0024R2]]）。`std::execution::par` 允许实现把元素访问函数分到多个线程上执行（[[algorithms.parallel.exec#6]]）：

```cpp title="par.cpp" run ok flags="-std=c++2c -O2 -fexperimental-library"
#include <algorithm>
#include <chrono>
#include <cmath>
#include <cstdio>
#include <execution>
#include <numeric>
#include <random>
#include <vector>
using namespace std::chrono;
template<class F> double ms(F f) {
  auto t0 = steady_clock::now(); f();
  return duration<double, std::milli>(steady_clock::now() - t0).count();
}
int main() {
  std::vector<double> v(20'000'000);
  std::mt19937_64 rng(1);
  std::uniform_real_distribution<double> d(0, 1);
  for (auto& x : v) x = d(rng);
  double r1 = 0, r2 = 0;
  auto f = [](double x) { return std::sqrt(x) * std::sin(x); };
  double t_seq = ms([&] { r1 = std::transform_reduce(std::execution::seq,
                       v.begin(), v.end(), 0.0, std::plus<>{}, f); });
  double t_par = ms([&] { r2 = std::transform_reduce(std::execution::par,
                       v.begin(), v.end(), 0.0, std::plus<>{}, f); });
  std::printf("transform_reduce: seq %.0f ms, par %.0f ms (%.1fx), diff %.2g\n",
              t_seq, t_par, t_seq / t_par, r1 - r2);
  auto a = v, b = v;
  t_seq = ms([&] { std::sort(std::execution::seq, a.begin(), a.end()); });
  t_par = ms([&] { std::sort(std::execution::par, b.begin(), b.end()); });
  std::printf("sort:             seq %.0f ms, par %.0f ms (%.1fx), equal %d\n",
              t_seq, t_par, t_seq / t_par, a == b);
}
```

```text
transform_reduce: seq 86 ms, par 14 ms (6.3x), diff 2.2e-06
sort:             seq 1520 ms, par 725 ms (2.1x), equal 1
```

本机 libc++ 的并行算法默认不可用，不加 `-fexperimental-library` 时 `std::execution::par` 不存在。加上之后，它用 libdispatch（Grand Central Dispatch）作后端。三次运行中 `transform_reduce` 加速 4.7 到 7.9 倍，`sort` 三次都约 2.1 倍。每个元素计算量大、彼此独立的归约最容易并行；排序要合并，访存多，加速有限。机器满载时这些数字会差很多。

输出里的 `diff` 不是零。`reduce` 和 `transform_reduce` 的结果规定为 GENERALIZED_SUM（[[transform.reduce#9]]），即按任意分组、任意顺序相加（[[numerics.defns#2]]）。浮点加法不满足结合律，所以并行结果与顺序结果可以不同，即使用 `seq` 策略，标准也不保证按顺序加。需要可复现的结果就用 `std::accumulate`。

使用 `par` 时还有两条规则：

- 元素访问函数之间没有同步，避免数据竞争和死锁是调用者的责任（[[algorithms.parallel.exec#6]] 的注 6）。在 lambda 里向共享的 `vector` `push_back` 是数据竞争，标准正好用它作例子。
- 元素访问函数抛出异常时调用 `std::terminate`（[[execpol.par#2]]），异常不会传到调用者。本机在 `par` 的 `for_each` 外面写 `try`/`catch`，程序仍以 "terminating due to uncaught exception" 终止。

## `std::execution`：方向

`std::future` 的接口有几处根本的限制：每个 `future` 都要在堆上分配共享状态；`async` 一调用就开始执行，没有办法先描述再启动；没有取消；标准里也没有 `then` 这样的续接。C++26 的 `std::execution`（[[P2300R10]]）换了一个模型，导读见 [[exec]]：

- **发送器**（[[g:sender|sender]]）只描述一段异步工作，本身不执行；
- 适配器把发送器组合起来，`then` 接续，`when_all` 并发等待多个；
- 消费者（如 `sync_wait`）把它连接到接收器并启动。完成方式只有三种：值、错误、停止。

```cpp
namespace ex = std::execution;
ex::parallel_scheduler sch = ex::get_parallel_scheduler();
auto work = ex::when_all(
                ex::schedule(sch) | ex::then([] { return part(0); }),
                ex::schedule(sch) | ex::then([] { return part(1); }))
          | ex::then([](long a, long b) { return a + b; });
auto [total] = std::this_thread::sync_wait(std::move(work)).value();
```

本机 libc++ 的 `<execution>` 只有执行策略，没有发送器，这段代码按草案写成，没有编译过。对照前面的线程池：异常沿错误通道传播，`sync_wait` 在调用方重新抛出（[[exec.sync.wait#10]]）；不需要 `future` 和共享状态；子操作必须在父操作完成之前完成（[[exec.async.ops#2]] 第 2.5 项），生命周期由结构决定。`parallel_scheduler`（[[exec.par.scheduler]]，[[P2079R10]]）是标准提供的系统线程池。[[patterns/observer|观察者模式]]一页讨论了这种结构化方式怎样处理回调的生命周期。

这套设施刚进入标准，实现、实践和配套设施（网络、异步作用域 [[exec.scope]]）都还在发展中。

## 常见错误

### 死锁：加锁顺序不一致

```cpp title="deadlock.cpp" run
#include <cstdio>
#include <mutex>
#include <thread>
struct Account {
  std::mutex m;
  long balance = 1000;
};
void transfer(Account& from, Account& to, long amount) {
  std::lock_guard l1(from.m);              // 先锁转出方
  std::lock_guard l2(to.m);                // 再锁转入方
  from.balance -= amount;
  to.balance += amount;
}
int main() {
  Account a, b;
  std::jthread t1([&] { for (int i = 0; i < 100000; ++i) transfer(a, b, 1); });
  std::jthread t2([&] { for (int i = 0; i < 100000; ++i) transfer(b, a, 1); });
  t1.join(); t2.join();
  std::printf("%ld %ld\n", a.balance, b.balance);
}
```

`t1` 持有 `a.m` 等 `b.m`，`t2` 持有 `b.m` 等 `a.m`，谁也不让。本机两次运行都在 10 秒超时前没有结束。死锁不是 UB，程序只是永远等下去。

两种修法：

<div class="compare" markdown="1">

```cpp
// 一次锁住两个
std::scoped_lock lock(from.m, to.m);
```

```cpp
// 固定顺序：先锁地址小的
std::mutex* p = &from.m;
std::mutex* q = &to.m;
if (std::less<>{}(q, p)) std::swap(p, q);
std::scoped_lock l1(*p);
std::scoped_lock l2(*q);
```

</div>

`std::scoped_lock` 有多个互斥量时调用 `std::lock`（[[thread.lock.scoped#2]]），后者保证不会因加锁顺序死锁，具体算法未指定（[[thread.lock.algorithm#5]]），可能是尝试加锁，失败就全部释放再重试。两种改法本机都正常结束，TSan 也没有报告。固定顺序的办法适用于锁不能在同一处一起获得的情形，比如按层级加锁。

ThreadSanitizer 有检测锁顺序反转的功能，但本机 macOS 上的 TSan 对上面的程序没有报告，把两个线程改成先后运行（不会真的死锁）也没有报告。不能依赖它。

### 丢失唤醒与虚假唤醒

```cpp title="lost.cpp" run
#include <chrono>
#include <condition_variable>
#include <cstdio>
#include <mutex>
#include <thread>
using namespace std::chrono_literals;
std::mutex m;
std::condition_variable cv;
bool ready = false;
int main() {
  std::jthread notifier([] {
    { std::scoped_lock lock(m); ready = true; }
    cv.notify_one();                       // 此时还没有人在等
  });
  std::this_thread::sleep_for(100ms);      // 让通知先发生
  std::unique_lock lock(m);
  bool ok = cv.wait_for(lock, 2s) == std::cv_status::no_timeout;
  std::printf(ok ? "woken\n" : "timed out: wakeup lost\n");
}
```

```text
timed out: wakeup lost
```

条件变量不记事：`notify_one` 只唤醒此刻正在等的线程（[[thread.condition.condvar#5]]），没有人等，通知就丢了。反过来，`wait` 也可能在没有通知时返回，即**虚假唤醒**（spurious wakeup，[[thread.condition.condvar#8]] 第 8.3 项）。

两个问题有同一个解法：状态存在受互斥量保护的变量里，等待时检查它。带谓词的 `wait` 就是这样定义的，等价于 `while (!pred()) wait(lock);`（[[thread.condition.condvar#13]]）。把上面的等待改成：

```cpp
bool ok = cv.wait_for(lock, 2s, [] { return ready; });
```

程序立即输出 `woken`：谓词一开始就为真，根本不阻塞。

!!! pitfall "条件在锁外修改"
    ```cpp
    std::atomic<bool> ready{false};
    // 通知方：
    ready = true;            // 没有加锁
    cv.notify_one();
    // 等待方：
    std::unique_lock lock(m);
    cv.wait(lock, [] { return ready.load(); });
    ```
    即使 `ready` 是原子的，也可能丢失唤醒：等待方检查谓词为假之后、真正进入阻塞之前，通知方完成了写入和通知，通知落空，等待方随后睡下去，再也没人唤醒它。`wait` 原子地解锁并阻塞（[[thread.condition.condvar#8]] 第 8.1 项），只有当通知方修改条件时也持有同一把锁，这个空隙才被封住。修改可以很短：`{ std::scoped_lock l(m); ready = true; }`，通知放在锁外即可。

### `shared_ptr`：哪一部分是线程安全的

`shared_ptr` 的线程安全有三个层次（详见[[topics/ownership-and-smart-pointers|所有权与智能指针]]）：

1. 引用计数：不同的 `shared_ptr` 对象即使共享同一个控制块，也可以在不同线程里各自复制、销毁，标准规定成员函数只访问 `shared_ptr` 对象本身（[[util.smartptr.shared.general#5]]），计数由实现原子地维护。
2. 同一个 `shared_ptr` 对象：一个线程赋值、另一个线程复制，是数据竞争，与普通变量一样。
3. 被指向的对象：`shared_ptr` 不提供任何保护。

```cpp title="sp.cpp" run ub
#include <cstdio>
#include <memory>
#include <thread>
struct Config { int port; };
std::shared_ptr<const Config> current = std::make_shared<Config>(80);
std::shared_ptr<const Config> load() { return current; }   // 复制 current
void store(std::shared_ptr<const Config> p) { current = std::move(p); }
int main() {
  std::jthread writer([] {
    for (int i = 0; i < 10000; ++i) store(std::make_shared<Config>(i));
  });
  long sum = 0;
  for (int i = 0; i < 10000; ++i) {
    auto c = load();
    sum += c->port;
  }
  std::printf("%ld\n", sum);
}
```

这是第 2 层的错误：`load` 复制全局的 `current`，`store` 同时给它赋值。复制要先读出控制块指针再增加计数，赋值可能在两步之间把旧控制块的计数减到零、释放对象。本机 TSan 报告 `current` 内部两个指针上的数据竞争；ASan 构建运行 5 次，2 次崩溃，一次是 SEGV，一次是 heap-use-after-free。

C++20 的 `std::atomic<std::shared_ptr<T>>`（[[util.smartptr.atomic]]，[[P0718R2]]）正是为此设计的，但本机 libc++ 还没有实现，实例化时静态断言要求 `T` 可平凡复制。可移植的写法是用一把互斥量保护 `current` 本身：

```cpp
std::mutex m;
std::shared_ptr<const Config> load() { std::scoped_lock l(m); return current; }
void store(std::shared_ptr<const Config> p) {
  std::scoped_lock l(m);
  current.swap(p);
}                          // 旧对象随 p 在锁外释放
```

改成这样后 TSan 不再报告。读者拿到的是自己的副本，之后在锁外读 `c->port` 是安全的，因为 `Config` 是 `const`，发布之后没人再改。

### 伪共享

两个线程各写各的变量，没有数据竞争，结果却比单线程还慢：这两个变量落在同一个缓存行里，每次写入都要把整行从另一个核心抢过来。这是性能问题，不是正确性问题。按线程下标划分的结果数组是最常见的来源，修法是先在局部变量里累加，或者像上面的 `SpscRing` 那样用 `alignas(std::hardware_destructive_interference_size)` 隔开。测量和细节见[[perf/false-sharing|伪共享]]。

### 函数内的静态变量

```cpp title="statics.cpp" run ub
#include <cstdio>
#include <string>
#include <thread>
#include <unordered_map>
const std::string& name_of(int id) {
  static std::unordered_map<int, std::string> cache;  // 初始化是线程安全的
  auto it = cache.find(id);                            // 之后的读写不是
  if (it == cache.end())
    it = cache.emplace(id, "user" + std::to_string(id)).first;
  return it->second;
}
int main() {
  std::jthread t1([] { for (int i = 0; i < 1000; ++i) name_of(i); });
  std::jthread t2([] { for (int i = 0; i < 1000; ++i) name_of(i); });
}
```

C++11 起，块作用域静态变量的初始化是线程安全的：几个线程同时第一次经过声明时，其余线程等初始化完成（[[stmt.dcl#3]]）。所以函数内的静态局部变量是实现单例的简单办法。但这只管初始化，之后对 `cache` 的 `find` 和 `emplace` 是普通的容器操作，两个线程同时执行就是数据竞争，本机 TSan 报告 `__hash_table` 内部的竞争。要么加锁，要么改成 `thread_local` 让每个线程各有一份。

（GCC 和 Clang 有 `-fno-threadsafe-statics` 选项关掉初始化时的同步，这样编译的代码连初始化也不安全。）

同样的问题也出现在一些继承自 C 的库函数里：它们返回指向内部静态缓冲区的指针。标准明确说 `strtok`、`strerror`（[[cstring.syn#2]]）和 `gmtime`、`localtime`（[[ctime.syn#2]]）不要求避免数据竞争。其余标准库函数不会修改调用者没有通过实参交给它的、其他线程可访问的对象（[[res.on.data.races#3]]），所以对不同的对象调用是安全的，对同一个对象并发调用非 `const` 成员函数则不是。

## 思考题

!!! question "1. 线程池的 `run` 里，如果把 `cv_.wait(lock, st, pred)` 换成 `cv_.wait(lock, pred)`，再在析构函数里 `request_stop()` 后调用 `cv_.notify_all()`，会出什么问题？"

<details markdown="1">
<summary>答案</summary>

不带 `stop_token` 的 `wait` 只检查谓词 `!q_.empty()`。队列空时，`notify_all` 唤醒的工作线程重新检查谓词，仍为假，又睡下去，永远不会退出，`join` 因此永远等待。要么把停止条件放进谓词（`st.stop_requested() || !q_.empty()`，此时还要保证 `request_stop` 与谓词检查之间不会丢失唤醒），要么用 `condition_variable_any` 带 `stop_token` 的重载，它在等待期间注册停止回调，停止请求本身就会唤醒等待者（[[thread.condvarany.intwait#2]]）。
</details>

!!! question "2. `SpscRing` 的 `push` 里，读 `head_` 用 acquire。只看数据从生产者流向消费者，这一处似乎可以用 relaxed，为什么不行？"

<details markdown="1">
<summary>答案</summary>

生产者读到新的 `head_`，意味着消费者已经读完对应的槽位，生产者接下来会覆盖它。如果这次读是 relaxed，消费者对槽位的读（在它的 release 写 `head_` 之前）与生产者之后对同一槽位的写之间就没有 happens before，两者冲突，至少一个不是原子操作，构成数据竞争（[[intro.races#17]]）。acquire 与消费者的 release 配对，建立了"消费者读完 → 生产者再写"的先后。
</details>

!!! question "3. 下面的写法丢弃了 `std::async` 的返回值，但把它存进了一个 `vector`。还会串行执行吗？"
    ```cpp
    std::vector<std::future<void>> fs;
    for (int i = 0; i < 4; ++i)
      fs.push_back(std::async(std::launch::async, work));
    ```

<details markdown="1">
<summary>答案</summary>

不会。临时 `future` 被移动进 `vector`，移动构造不释放共享状态，所以没有阻塞；四个任务并发运行。阻塞发生在 `fs` 销毁时：每个元素析构时等待自己的任务结束（[[futures.state#5]] 第 5.3 项）。这通常正是想要的效果，相当于离开作用域时自动 `join`。
</details>

## 小结

| 问题 | 做法 |
|---|---|
| 执行大量小任务 | 线程池；`packaged_task` 传回结果和异常；任务在锁外执行 |
| 关闭线程池 | `jthread` 的停止令牌 + `condition_variable_any::wait(lock, stoken, pred)`；先全部 `request_stop` 再 `join` |
| `std::async` | 显式写 `launch::async`；保存返回的 `future`，否则析构时阻塞 |
| 生产者比消费者快 | 有界队列，两个条件变量 |
| 一对一的低延迟传递 | SPSC 环形缓冲区，两对 release/acquire，下标隔开缓存行 |
| 多对多的无锁结构 | 先用锁；必须无锁时处理 ABA 和回收（hazard pointer、RCU） |
| 大量独立的元素计算 | `std::execution::par`（libc++ 需要 `-fexperimental-library`）；元素函数不能抛异常；浮点归约不保证顺序 |
| 锁多个互斥量 | `std::scoped_lock` 一次锁住，或固定顺序 |
| 等待条件 | 状态放在锁保护的变量里，修改时加锁，等待时带谓词 |
| 多线程读写同一个 `shared_ptr` 变量 | 互斥量保护，或 `std::atomic<std::shared_ptr<T>>` |
| 检查 | TSan 查数据竞争，但它会漏报也会误报；在弱内存序的硬件上做压力测试 |
