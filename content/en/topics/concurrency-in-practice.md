---
title: Concurrency in practice
summary: "Writing real concurrent code on top of the memory model: a thread pool built from jthread, a condition variable and packaged_task that propagates exceptions and shuts down cleanly; two surprises in std::async; a bounded queue and a lock-free SPSC ring buffer; choosing a synchronization primitive; parallel algorithms and std::execution; and common mistakes such as deadlock, lost wakeups and shared_ptr races, all checked with Clang 23 and TSan."
tags: concurrency, thread pool, condition variables, future, lock-free, parallel algorithms, TSan, topic
updated: 2026-10-19
---

!!! tldr
    - The skeleton of a thread pool is one mutex, one condition variable and one task queue. `std::packaged_task` stores both the task's return value and its exception in the shared state, and `future::get()` rethrows in the caller.
    - If the `future` returned by `std::async` is discarded, its destructor blocks until the task completes. The default policy also lets the task be deferred until `get()`, running on the calling thread.
    - Always wait on a condition variable with a predicate: a notification may come before the wait, and a wait may wake up for no reason.
    - A single-producer single-consumer ring buffer needs only two atomic indices and acquire/release. For multi-producer multi-consumer lock-free structures, the hard parts are ABA and memory reclamation, for which the standard provides hazard pointers and RCU.
    - Avoid deadlock with a fixed lock order or by locking several mutexes at once with `std::scoped_lock`. The reference count of `shared_ptr` is thread-safe; the same `shared_ptr` object and the object it points to are not.

[[topics/memory-model|The memory model topic]] covers the rules: what a [[g:data-race|data race]] is (two threads access the same memory location, at least one access is a write, at least one is not atomic, and there is no [[g:happens-before|happens before]] between them; the behavior is undefined, [[intro.races#17]]), and how acquire/release establishes happens before. On top of those rules, writing actual concurrent components involves another class of problems: how tasks are handed over, how results and exceptions are passed back, how threads are shut down, and how to avoid deadlock and lost wakeups.

All examples below were compiled with `-std=c++2c` on an Apple M2 Pro (12 cores, macOS, Homebrew Clang 23 + libc++), and every multithreaded example was run under `-fsanitize=thread` (ThreadSanitizer, TSan below). The machine was heavily loaded while this was written (`uptime` load average between 50 and 190), so all timings are only good to an order of magnitude.

## A thread pool

### Design

A **thread pool** creates a set of worker threads up front, which repeatedly take tasks from a shared task queue and run them. A thread that submits a task puts it in the queue and gets back a `std::future`, which it later uses to fetch the result.

Four questions need answers:

1. Who protects the queue? A `std::mutex`.
2. How do workers wait when the queue is empty? They sleep on a condition variable and are woken when a new task arrives.
3. How are return values and exceptions handed back to the submitter? `std::packaged_task`.
4. How do we shut down? With the stop token that comes with `std::jthread`.

`std::packaged_task<R()>` wraps a callable and owns a [[g:shared-state|shared state]], a piece of storage shared by the side providing the result and the side reading it. When it is invoked, a normal return stores the return value in the shared state and an exception stores the exception; then the state is made ready ([[futures.task.members#22]]). `get_future()` returns a `std::future<R>` attached to the same shared state; `get()` waits until it is ready and takes out the value, rethrowing if what was stored is an exception ([[futures.unique.future#19]]).

`std::jthread` (C++20, [[P0660R10]]) differs from `std::thread` in two ways. If the first parameter of the thread function can accept a `std::stop_token`, the constructor passes in its own stop token ([[thread.jthread.cons#6]]); and on destruction, if the thread is still joinable, it calls `request_stop()` and then `join()` ([[thread.jthread.cons#12]]), rather than calling `std::terminate` the way `std::thread` does.

### The code

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
    for (auto& w : workers_) w.join();  // wait for the queue to drain
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
        // true if there is a task; false only when stop was requested and the queue is empty
        if (!cv_.wait(lock, st, [&] { return !q_.empty(); }))
          return;
        job = std::move(q_.front());
        q_.pop_front();
      }
      job();  // runs outside the lock; exceptions are captured by packaged_task
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

A separate stress test had 4 threads each submit 20,000 tasks at the same time, destroyed the pool immediately, then called `get()` on each future. TSan and ASan builds reported nothing, and all 80,000 tasks ran.

### The key points, line by line

#### Why the task is wrapped in a `shared_ptr`

`packaged_task` is move-only, while `std::function` requires a copyable callable. C++23's `std::move_only_function` ([[func.wrap.move]]) can hold a `packaged_task` directly and save this allocation, but libc++ in our tests doesn't have it yet.

#### Why `condition_variable_any`

Only `condition_variable_any` has the `wait` overload that takes a `stop_token` ([[thread.condvarany.intwait#2]]). It registers a callback during the wait that wakes it up when a stop is requested, and is then equivalent to:

```cpp
while (!stoken.stop_requested()) {
  if (pred()) return true;
  wait(lock);
}
return pred();
```

So after a stop is requested, `wait` still returns `true` as long as tasks remain in the queue; workers drain the queue first and exit only when the final `pred()` is false. Every `future` already handed out gets a result. With `std::condition_variable` instead, you'd have to maintain your own `stopping_` flag, set it under the lock and then `notify_all`.

#### Why tasks run outside the lock

Running a task while holding the lock makes all other workers queue up for that lock, and the pool degenerates to a single thread. If the task called `submit` again, it would also deadlock on the same non-recursive lock.

#### Where the exceptions go

An exception thrown by a task is stored in the shared state by `packaged_task::operator()` and never leaves `job()`. This matters: if the thread function exits via an exception, `jthread` calls `std::terminate` ([[thread.jthread.cons#6]]).

#### Why the destructor does its own `join`

It first calls `request_stop()` on all threads so they start winding down at the same time, then `join()`s them one by one. That way `m_`, `cv_` and `q_` are destroyed only after all workers have finished.

!!! pitfall "Relying on member destruction order"
    If the destructor only called `request_stop()` and left the `join` to `jthread`'s destructor, `workers_` would have to be declared last. Members are destroyed in reverse order of declaration; put `workers_` before `m_` and `m_` is destroyed before the `join`, while workers are still using it. Rewritten that way in our tests, a worker in the stress test threw `std::system_error` ("mutex lock failed: Invalid argument") and the program terminated. Local variables are the same: a mutex referenced by a thread must be declared before the `jthread`.

!!! note "Tasks discarded without running"
    If an implementation chose not to drain the queue and simply destroyed the remaining tasks, `packaged_task`'s destructor would abandon its shared state: it stores a `future_error` with error code `broken_promise` and makes the state ready ([[futures.state#7]]). A `get()` waiting on it throws that exception rather than blocking forever.

## Task-based versus thread-based

Creating a `std::thread` directly for each piece of work is a **thread-based** design: work is bound one-to-one to the thread that runs it, and the caller is responsible for `join` and for getting results and exceptions back. A **task-based** design only describes the work and leaves it to a thread pool, `std::async` or a scheduler to decide where it runs; results come back through objects such as `future`.

The latter is usually better: the number of threads can be fixed to the number of cores, the cost of creating threads is amortized, and there is a ready-made mechanism for passing exceptions. In our tests creating a thread and joining it takes about 13 µs, and handing a task to a thread pool about 0.9 to 3 µs; the measurements are in the last section of [[perf/false-sharing|the page on multithreaded performance]].

`std::async` looks like a shortcut to task-based design, but two of its behaviors often surprise people.

### A discarded future blocks

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
  std::async(std::launch::async, work);   // the temporary future is destroyed at the end of this line
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

The two tasks did not run concurrently. The temporary `future` returned by `std::async` is destroyed at the end of the full-expression, and destruction has to release the shared state. Releasing normally doesn't block, but item 5.3 of [[futures.state#5]] leaves an exception: when the shared state was created by `std::async`, is not yet ready, and this is the last reference, the release may block. Combined with item 4.1 of [[futures.async#4]], which requires waiting for the result of an `async` thread to be like a `join`, the effect is that the destructor waits for the task to finish. Note 2 in [[futures.async#5]] also points this out.

libc++ marks `std::async` `[[nodiscard]]`, so the two lines above get a `-Wunused-result` warning. The standard itself doesn't require this. A `future` obtained from `std::promise` or `std::packaged_task` never blocks on destruction; a thread pool's `future` can be dropped without consequence.

### The default policy may not be concurrent

`std::async(f)` with no policy argument is equivalent to passing `launch::async | launch::deferred`, and the implementation may choose either ([[futures.async#3]]). With `deferred`, the function is stored and runs on the calling thread only at the first call to `get()` or `wait()` (item 3.2). The standard's own example ([[futures.async#8]]) points out that there may be no concurrency at all.

libc++ in our tests picks a new thread for the default policy. But code that relies on this may break on other implementations; polling is the typical case:

```cpp
auto f = std::async(task);
while (f.wait_for(0s) != std::future_status::ready) {
  do_other_work();   // if the task is deferred, wait_for always returns deferred and the loop never ends
}
```

If you need concurrency, write `std::launch::async` explicitly; if you need more control (number of threads, cancellation, priorities), use a thread pool.

## Two queues

### A bounded multi-producer multi-consumer queue

The thread pool's queue has no upper limit and grows without bound when producers are too fast. A **bounded queue** makes producers wait when it is full, creating back pressure. It needs two condition variables: consumers wait for not-empty, producers wait for not-full.

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

  // returns false if the queue is closed
  bool push(T v) {
    std::unique_lock lock(m_);
    not_full_.wait(lock, [&] { return closed_ || q_.size() < cap_; });
    if (closed_) return false;
    q_.push_back(std::move(v));
    lock.unlock();
    not_empty_.notify_one();
    return true;
  }

  // returns nullopt if the queue is closed and drained
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
    }            // all producers joined
    q.close();   // consumers exit after draining
  }
  long n = long(producers) * per;
  std::printf("count %ld, sum %ld, expected %ld\n",
              count.load(), sum.load(), n * (n - 1) / 2);
}
```

```text
count 200000, sum 19999900000, expected 19999900000
```

No reports under TSan. A few details:

- `notify_one` comes after unlocking. Putting it inside the lock is also correct; the woken thread may just run straight into the lock that hasn't been released yet.
- `close()` uses `notify_all`, because every waiting thread needs to see `closed_`.
- `pop` still takes the remaining elements after closing; `nullopt` means only closed and empty.
- Relaxed `fetch_add` is enough for the counters: they aren't used to publish other data, and the final reads happen after `join`, which provides the synchronization.

### A lock-free single-producer single-consumer ring buffer

With just one producer and one consumer, no lock is needed. The buffer is a fixed-size array; the producer writes `tail_`, the consumer writes `head_`, and each only reads the other's index:

```cpp title="spsc.hpp"
#pragma once
#include <atomic>
#include <cstddef>
#include <new>

template<class T, std::size_t N>   // N is a power of 2
class SpscRing {
  static_assert(N > 0 && (N & (N - 1)) == 0);
  static constexpr std::size_t line =
      std::hardware_destructive_interference_size;
  alignas(line) std::atomic<std::size_t> head_{0};  // written only by the consumer
  alignas(line) std::atomic<std::size_t> tail_{0};  // written only by the producer
  alignas(line) T buf_[N];

public:
  bool push(const T& v) {                  // producer thread only
    std::size_t t = tail_.load(std::memory_order::relaxed);
    std::size_t h = head_.load(std::memory_order::acquire);
    if (t - h == N) return false;          // full
    buf_[t % N] = v;
    tail_.store(t + 1, std::memory_order::release);
    return true;
  }
  bool pop(T& out) {                       // consumer thread only
    std::size_t h = head_.load(std::memory_order::relaxed);
    std::size_t t = tail_.load(std::memory_order::acquire);
    if (t == h) return false;              // empty
    out = buf_[h % N];
    head_.store(h + 1, std::memory_order::release);
    return true;
  }
};
```

The indices only ever increase, and `t - h` is the number of elements; after `size_t` wraps around, unsigned subtraction is still correct, so `N` is a power of 2 to keep `% N` consistent across the wrap.

Each memory order has its reason; the method of reasoning is in [[topics/memory-model|the memory model topic]]:

| Operation | Memory order | Reason |
|---|---|---|
| `push` reads its own `tail_` | relaxed | Only this thread writes it, so it always reads its own last write |
| `push` writes `tail_` | release | Publishes the slot: the earlier write to `buf_[t % N]` must be visible to a consumer that reads the new `tail_` |
| `pop` reads `tail_` | acquire | Pairs with the line above; after reading `t + 1`, there is happens before between the producer's write and the read of the slot |
| `pop` writes `head_` | release | Returns the slot: the earlier read of the slot must happen before the producer's next write to that slot |
| `push` reads `head_` | acquire | Pairs with the line above; otherwise the producer overwriting a slot could race with a read the consumer hasn't finished |

The two release/acquire pairs each cover one direction: `tail_` hands data from producer to consumer, and `head_` hands empty slots back to the producer. Looking only at the former, it's easy to miss the latter.

`alignas` puts the two indices on different cache lines. Each is written frequently by a different core; on the same line they would keep invalidating each other's cache, which is [[perf/false-sharing|false sharing]]. In our tests `hardware_destructive_interference_size` is 128 ([[hardware.interference]]).

A stress test checks it: the producer pushes 5 million messages in order, and the consumer checks order and contents:

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
      while (!ring.push({i, i * i})) {}    // retry when full
  });
  long errors = 0;
  Msg m;
  for (long i = 0; i < n; ++i) {
    while (!ring.pop(m)) {}                // retry when empty
    if (m.seq != i || m.square != i * i) ++errors;
  }
  std::printf("errors: %ld\n", errors);
}
```

Changing the memory orders to relaxed one at a time gives the following results in our tests (the `-O2` column is `errors` from three runs):

| Change | TSan | `-O2`, no sanitizer |
|---|---|---|
| As written | No report | 0, 0, 0 |
| `push` writes `tail_` relaxed | Data race | 17977, 21453, 13205 |
| `pop` also reads `tail_` relaxed | Data race | 7940, 36732, 63116 |
| `pop` writes `head_` relaxed | Data race | 0, 0, 0 |

The last row shows the limits of testing: the program already has a data race, yet on this machine it never fails, because the reordering required (the consumer reading the slot after it writes `head_`) rarely happens on arm64. TSan reasons in terms of happens before and doesn't depend on how this particular run happened to execute, so it can report it.

!!! impl "TSan also misses things"
    When the slot was changed to a 32-byte struct copied with a compiler-generated `memcpy`, TSan in our tests reported nothing for the same broken version, while the `-O2` run still produced errors. TSan can only show whether the accesses it saw race; it can't prove there is no race.

The lock-free version isn't necessarily faster either. Under high load in our tests, for the same single-producer single-consumer transfer, the ring buffer took about 34 to 42 ns per message and `BoundedQueue` about 69 to 146 ns. The main value of lock-free structures often isn't throughput but the fact that no thread gets stuck because another thread was suspended.

### Why general lock-free MPMC is hard

Once several threads may modify the same index at once, simple load/store isn't enough and you need compare-exchange (CAS). The simplest example is a lock-free stack (Treiber stack):

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
    while (old && !head_.compare_exchange_weak(old, old->next,  // ① reads old->next
               std::memory_order::acquire, std::memory_order::acquire)) {}
    if (!old) return std::nullopt;
    T v = std::move(old->value);
    delete old;                     // ② another thread may be stopped at ①
    return v;
  }
};
```

`push` is correct. `pop` has two problems:

1. **Memory reclamation**. Thread A reads `old` and is suspended; thread B pops the same node and `delete`s it at ②; A wakes up and reads `old->next` at ①, reading freed memory, which is UB.
2. **ABA**. B pops nodes X and Y, frees them, then pushes a new node, and the allocator happens to reuse X's address. A's CAS compares addresses, sees that `head_` is still X, and succeeds, setting `head_` to the `X->next` that A read earlier, which is the freed Y. The value went from A to B and back to A, and CAS can't tell the difference, hence the name ABA.

With 4 threads each doing 200,000 push/pop operations, three ASan runs in our tests all reported heap-use-after-free at ①, and TSan also reported a data race at ①; the `-O2` build without sanitizers finished normally all three times.

The root problem is that a thread deleting a node doesn't know whether other threads still hold a pointer to it. Garbage-collected languages don't have this problem. C++26 provides two standard solutions in [[saferecl]]:

- **Hazard pointers** ([[saferecl.hp.general#1]], [[P2530R3]]): before dereferencing, a reader registers the pointer in its own hazard pointer; the deleter retires the node, and only nodes not pointed to by any hazard pointer are actually reclaimed.
- **RCU** (read-copy update, [[saferecl.rcu.general#1]], [[P2545R4]]): readers enter a protected region; a writer replaces the pointer and defers deleting the old object until all protected regions that had already begun have ended. Suited to read-mostly structures.

Both defer reclamation, so a node's address isn't reused while it is referenced, and ABA goes away as well. libc++ in our tests doesn't have the `<hazard_pointer>` and `<rcu>` headers yet. Until they are available, and unless you have solid measurements to justify otherwise, use a lock-based implementation like `BoundedQueue` for multi-producer multi-consumer cases.

## Choosing a synchronization primitive

| Need | Choice | Clause |
|---|---|---|
| Protect an invariant (several variables change together) | `std::mutex` + `std::scoped_lock`/`std::unique_lock` | [[thread.mutex.requirements.mutex.general]] |
| Reads far outnumber writes, and read critical sections aren't short | `std::shared_mutex` | [[thread.sharedmutex.requirements.general]] |
| A single counter or flag that doesn't publish other data | `std::atomic`, relaxed read-modify-write | [[atomics.order]] |
| Publish data through a flag | `std::atomic`, release store paired with acquire load | [[atomics.order]] |
| Wait for a condition to hold | Condition variable (with predicate), or `atomic::wait` | [[thread.condition.condvar]], [[atomics.wait]] |
| Limit how many threads enter at once | `std::counting_semaphore` | [[thread.sema.cnt]] |
| Wait for N things to happen once each | `std::latch` | [[thread.latch]] |
| Several threads synchronizing in rounds | `std::barrier` | [[thread.barrier.class]] |

The last three all come from C++20 ([[P1135R6]]). Choose among them by semantics, not speed; for a performance comparison see [[perf/false-sharing|the page on multithreaded performance]], whose conclusion is that as long as all threads update the same data, no primitive will make it scale.

### `shared_mutex`: many readers, one writer

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
    std::shared_lock lock(m_);             // several readers may hold it at once
    auto it = kv_.find(k);
    return it == kv_.end() ? -1 : it->second;
  }
  void set(const std::string& k, int v) {
    std::unique_lock lock(m_);             // the writer has exclusive access
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
  ts.clear();                              // join all threads
  std::printf("%d\n", c.get("port"));
}
```

A shared lock can be held by several threads at once but excludes the exclusive lock ([[thread.sharedmutex.requirements.general#2]]). Readers still have to atomically update the lock's internal count among themselves, so when critical sections are short, `shared_mutex` is often no faster than a plain `mutex`. The standard also doesn't specify whether readers or writers have priority; whether a continuous stream of readers can starve a writer depends on the implementation.

### `counting_semaphore`: limiting concurrency

```cpp title="sema.cpp" run ok
#include <atomic>
#include <cstdio>
#include <semaphore>
#include <thread>
#include <vector>
std::counting_semaphore<3> slots(3);       // at most 3 threads inside at once
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

A semaphore maintains a counter: `acquire` decrements it when it is positive and otherwise blocks; `release` increments it and wakes waiters ([[thread.sema.cnt#1]]). Unlike a mutex it has no owner, and `release` may be called by another thread, so it can also be used for notification between threads. `std::binary_semaphore` is `counting_semaphore<1>`.

### `barrier`: computing in rounds

```cpp title="barrier.cpp" run ok
#include <barrier>
#include <cstdio>
#include <thread>
#include <vector>
int main() {
  constexpr int n = 4, steps = 3;
  std::vector<int> cur(n, 1), next(n);
  int step = 0;
  auto on_phase_done = [&]() noexcept {    // run by one thread after everyone arrives each round
    cur.swap(next);
    std::printf("step %d: %d %d %d %d\n", ++step, cur[0], cur[1], cur[2], cur[3]);
  };
  std::barrier sync(n, on_phase_done);
  std::vector<std::jthread> ts;
  for (int i = 0; i < n; ++i)
    ts.emplace_back([&, i] {
      for (int s = 0; s < steps; ++s) {
        next[i] = cur[i] + cur[(i + 1) % n] + i;  // read the previous round, write own element
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

Each thread reads `cur`, writes `next[i]`, then arrives at the barrier. Once all threads have arrived, exactly one thread runs the completion function, swapping the two arrays, and then all threads continue to the next round. There is no data race because each `arrive` strongly happens before the start of the round's completion step ([[thread.barrier.class#14]]), and the end of the completion step strongly happens before the return of the calls it unblocks ([[thread.barrier.class#3]]).

!!! impl "TSan false positive on barrier in our tests"
    TSan in our tests reports a data race between `swap` and the worker threads' reads of `cur` for this program. By the two synchronization rules above, the program has no race. libc++'s `<barrier>` declares the arrival algorithm as a function exported from the shared library (`__arrive_barrier_algorithm_base`), which isn't instrumented by TSan; presumably that is why TSan can't see the synchronization inside it. For a `std::latch` example see [[topics/memory-model|the memory model topic]].

## Parallel algorithms

C++17 added overloads taking an **execution policy** to most standard algorithms ([[P0024R2]]). `std::execution::par` allows the implementation to run the element access functions on several threads ([[algorithms.parallel.exec#6]]):

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

In libc++ the parallel algorithms are not available by default: without `-fexperimental-library`, `std::execution::par` doesn't exist. With it, they use libdispatch (Grand Central Dispatch) as the backend. Over three runs `transform_reduce` sped up 4.7 to 7.9 times, and `sort` about 2.1 times every time. Reductions where each element is expensive and independent parallelize most easily; sorting has to merge and touches a lot of memory, so the speedup is limited. These numbers would look very different on a fully loaded machine.

The `diff` in the output is not zero. The result of `reduce` and `transform_reduce` is specified as GENERALIZED_SUM ([[transform.reduce#9]]), that is, summed in any grouping and any order ([[numerics.defns#2]]). Floating-point addition isn't associative, so the parallel result can differ from the sequential one; even with the `seq` policy the standard doesn't guarantee summing in order. Use `std::accumulate` when you need reproducible results.

Two more rules apply when using `par`:

- There is no synchronization between element access functions; avoiding data races and deadlocks is the caller's responsibility (Note 6 in [[algorithms.parallel.exec#6]]). Calling `push_back` on a shared `vector` inside the lambda is a data race, and the standard uses exactly that as its example.
- If an element access function throws, `std::terminate` is called ([[execpol.par#2]]); the exception does not propagate to the caller. In our tests, wrapping a `par` `for_each` in `try`/`catch` still terminated the program with "terminating due to uncaught exception".

## `std::execution`: the direction

`std::future`'s interface has some fundamental limits: every `future` needs a heap-allocated shared state; `async` starts executing as soon as it is called, with no way to describe first and launch later; there is no cancellation; and the standard has no continuation like `then`. C++26's `std::execution` ([[P2300R10]]) uses a different model; for an introduction see [[exec]]:

- A [[g:sender|sender]] only describes a piece of asynchronous work and does not run by itself;
- Adaptors compose senders: `then` chains a continuation, `when_all` waits for several concurrently;
- A consumer (such as `sync_wait`) connects it to a receiver and starts it. There are only three ways to complete: value, error, stopped.

```cpp
namespace ex = std::execution;
ex::parallel_scheduler sch = ex::get_parallel_scheduler();
auto work = ex::when_all(
                ex::schedule(sch) | ex::then([] { return part(0); }),
                ex::schedule(sch) | ex::then([] { return part(1); }))
          | ex::then([](long a, long b) { return a + b; });
auto [total] = std::this_thread::sync_wait(std::move(work)).value();
```

libc++'s `<execution>` in our tests has only execution policies and no senders; this code is written from the draft and has not been compiled. Compared with the thread pool above: exceptions propagate along the error channel and `sync_wait` rethrows them in the caller ([[exec.sync.wait#10]]); no `future` or shared state is needed; child operations must complete before their parent completes (item 2.5 of [[exec.async.ops#2]]), so lifetimes are determined by structure. `parallel_scheduler` ([[exec.par.scheduler]], [[P2079R10]]) is the system thread pool provided by the standard. The [[patterns/observer|observer pattern]] page discusses how this structured approach handles the lifetimes of callbacks.

This facility has only just entered the standard; implementations, practice and the surrounding facilities (networking, async scopes [[exec.scope]]) are all still developing.

## Common mistakes

### Deadlock: inconsistent lock order

```cpp title="deadlock.cpp" run
#include <cstdio>
#include <mutex>
#include <thread>
struct Account {
  std::mutex m;
  long balance = 1000;
};
void transfer(Account& from, Account& to, long amount) {
  std::lock_guard l1(from.m);              // lock the source first
  std::lock_guard l2(to.m);                // then the destination
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

`t1` holds `a.m` and waits for `b.m`, `t2` holds `b.m` and waits for `a.m`, and neither gives way. In our tests both runs failed to finish before a 10-second timeout. Deadlock is not UB; the program just waits forever.

Two fixes:

<div class="compare" markdown="1">

```cpp
// lock both at once
std::scoped_lock lock(from.m, to.m);
```

```cpp
// fixed order: lower address first
std::mutex* p = &from.m;
std::mutex* q = &to.m;
if (std::less<>{}(q, p)) std::swap(p, q);
std::scoped_lock l1(*p);
std::scoped_lock l2(*q);
```

</div>

With several mutexes, `std::scoped_lock` calls `std::lock` ([[thread.lock.scoped#2]]), which guarantees no deadlock from lock ordering; the algorithm is unspecified ([[thread.lock.algorithm#5]]) and may be to try locking, release everything on failure and retry. Both fixes finished normally in our tests, and TSan reported nothing. The fixed-order approach applies when the locks can't be acquired together in one place, such as with hierarchical locking.

ThreadSanitizer has a feature for detecting lock-order inversions, but TSan on macOS in our tests reported nothing for the program above, nor when the two threads were changed to run one after the other (which can't actually deadlock). Don't rely on it.

### Lost wakeups and spurious wakeups

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
    cv.notify_one();                       // nobody is waiting yet
  });
  std::this_thread::sleep_for(100ms);      // let the notification happen first
  std::unique_lock lock(m);
  bool ok = cv.wait_for(lock, 2s) == std::cv_status::no_timeout;
  std::printf(ok ? "woken\n" : "timed out: wakeup lost\n");
}
```

```text
timed out: wakeup lost
```

A condition variable has no memory: `notify_one` only wakes a thread that is waiting at that moment ([[thread.condition.condvar#5]]); if nobody is waiting, the notification is lost. Conversely, `wait` may return without a notification, a **spurious wakeup** (item 8.3 of [[thread.condition.condvar#8]]).

Both problems have the same solution: keep the state in a variable protected by the mutex, and check it while waiting. The `wait` with a predicate is defined exactly that way, equivalent to `while (!pred()) wait(lock);` ([[thread.condition.condvar#13]]). Change the wait above to:

```cpp
bool ok = cv.wait_for(lock, 2s, [] { return ready; });
```

and the program prints `woken` immediately: the predicate is true from the start, so it never blocks.

!!! pitfall "Modifying the condition outside the lock"
    ```cpp
    std::atomic<bool> ready{false};
    // notifier:
    ready = true;            // no lock held
    cv.notify_one();
    // waiter:
    std::unique_lock lock(m);
    cv.wait(lock, [] { return ready.load(); });
    ```
    Even though `ready` is atomic, the wakeup can still be lost: after the waiter finds the predicate false but before it actually blocks, the notifier completes the write and the notification, the notification goes nowhere, and the waiter then goes to sleep with nobody left to wake it. `wait` atomically unlocks and blocks (item 8.1 of [[thread.condition.condvar#8]]), and the gap is closed only if the notifier also holds the same lock when modifying the condition. The modification can be very short: `{ std::scoped_lock l(m); ready = true; }`, with the notification outside the lock.

### `shared_ptr`: which part is thread-safe

The thread safety of `shared_ptr` has three levels (see [[topics/ownership-and-smart-pointers|the topic page on ownership and smart pointers]]):

1. The reference count: distinct `shared_ptr` objects, even sharing one control block, may be copied and destroyed independently in different threads. The standard says member functions only access the `shared_ptr` object itself ([[util.smartptr.shared.general#5]]), and the count is maintained atomically by the implementation.
2. The same `shared_ptr` object: one thread assigning while another copies is a data race, just as with an ordinary variable.
3. The pointed-to object: `shared_ptr` provides no protection at all.

```cpp title="sp.cpp" run ub
#include <cstdio>
#include <memory>
#include <thread>
struct Config { int port; };
std::shared_ptr<const Config> current = std::make_shared<Config>(80);
std::shared_ptr<const Config> load() { return current; }   // copies current
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

This is a level-2 mistake: `load` copies the global `current` while `store` assigns to it. Copying first reads the control block pointer and then increments the count; the assignment can, between those two steps, drop the old control block's count to zero and free the object. TSan in our tests reports data races on the two pointers inside `current`; an ASan build crashed in 2 of 5 runs, once with SEGV and once with heap-use-after-free.

C++20's `std::atomic<std::shared_ptr<T>>` ([[util.smartptr.atomic]], [[P0718R2]]) was designed exactly for this, but libc++ in our tests hasn't implemented it yet; instantiating it hits a static assertion requiring `T` to be trivially copyable. The portable approach is to protect `current` itself with a mutex:

```cpp
std::mutex m;
std::shared_ptr<const Config> load() { std::scoped_lock l(m); return current; }
void store(std::shared_ptr<const Config> p) {
  std::scoped_lock l(m);
  current.swap(p);
}                          // the old object is released with p, outside the lock
```

With this change TSan no longer reports anything. Each reader gets its own copy, and reading `c->port` outside the lock afterwards is safe because `Config` is `const` and nobody modifies it after publication.

### False sharing

Two threads each write their own variable, with no data race, yet the result is slower than a single thread: the two variables sit on the same cache line, and every write has to grab the whole line from the other core. This is a performance problem, not a correctness problem. Result arrays indexed by thread number are the most common source; the fix is to accumulate in a local variable first, or to separate them with `alignas(std::hardware_destructive_interference_size)` as `SpscRing` does above. Measurements and details are in [[perf/false-sharing|false sharing]].

### Static variables in functions

```cpp title="statics.cpp" run ub
#include <cstdio>
#include <string>
#include <thread>
#include <unordered_map>
const std::string& name_of(int id) {
  static std::unordered_map<int, std::string> cache;  // initialization is thread-safe
  auto it = cache.find(id);                            // later reads and writes are not
  if (it == cache.end())
    it = cache.emplace(id, "user" + std::to_string(id)).first;
  return it->second;
}
int main() {
  std::jthread t1([] { for (int i = 0; i < 1000; ++i) name_of(i); });
  std::jthread t2([] { for (int i = 0; i < 1000; ++i) name_of(i); });
}
```

Since C++11, initialization of block-scope static variables is thread-safe: when several threads pass the declaration for the first time at once, the others wait for the initialization to complete ([[stmt.dcl#3]]). That makes a function-local static a simple way to implement a singleton. But this covers only the initialization; the later `find` and `emplace` on `cache` are ordinary container operations, and two threads running them at once is a data race. TSan in our tests reports a race inside `__hash_table`. Either add a lock, or make it `thread_local` so each thread has its own copy.

(GCC and Clang have a `-fno-threadsafe-statics` option that turns off the synchronization on initialization; code compiled that way isn't safe even during initialization.)

The same problem shows up in some library functions inherited from C: they return pointers to internal static buffers. The standard says explicitly that `strtok`, `strerror` ([[cstring.syn#2]]), `gmtime` and `localtime` ([[ctime.syn#2]]) are not required to avoid data races. Other standard library functions don't modify objects accessible to other threads unless the caller passed them in through arguments ([[res.on.data.races#3]]), so calls on different objects are safe, while concurrent calls to non-`const` member functions on the same object are not.

## Questions

!!! question "1. In the thread pool's `run`, what goes wrong if `cv_.wait(lock, st, pred)` is replaced with `cv_.wait(lock, pred)`, and the destructor calls `cv_.notify_all()` after `request_stop()`?"

<details markdown="1">
<summary>Answer</summary>

The `wait` without a `stop_token` checks only the predicate `!q_.empty()`. When the queue is empty, a worker woken by `notify_all` rechecks the predicate, finds it still false, and goes back to sleep; it never exits, so `join` waits forever. Either put the stop condition into the predicate (`st.stop_requested() || !q_.empty()`, in which case you also have to ensure no wakeup is lost between `request_stop` and the predicate check), or use the `condition_variable_any` overload taking a `stop_token`, which registers a stop callback during the wait, so the stop request itself wakes the waiter ([[thread.condvarany.intwait#2]]).
</details>

!!! question "2. In `SpscRing::push`, `head_` is read with acquire. Looking only at data flowing from producer to consumer, it seems this could be relaxed. Why not?"

<details markdown="1">
<summary>Answer</summary>

When the producer reads a new `head_`, the consumer has finished reading the corresponding slot, and the producer will overwrite it next. If this read were relaxed, there would be no happens before between the consumer's read of the slot (before its release write of `head_`) and the producer's later write to the same slot; the two conflict, at least one isn't atomic, and that is a data race ([[intro.races#17]]). The acquire pairs with the consumer's release and establishes the order "consumer finishes reading → producer writes again".
</details>

!!! question "3. The code below doesn't discard the return value of `std::async` but stores it in a `vector`. Does it still run serially?"
    ```cpp
    std::vector<std::future<void>> fs;
    for (int i = 0; i < 4; ++i)
      fs.push_back(std::async(std::launch::async, work));
    ```

<details markdown="1">
<summary>Answer</summary>

No. The temporary `future` is moved into the `vector`, and move construction doesn't release the shared state, so there is no blocking; the four tasks run concurrently. The blocking happens when `fs` is destroyed: each element's destructor waits for its own task to finish (item 5.3 of [[futures.state#5]]). This is usually exactly what you want, the equivalent of an automatic `join` when leaving the scope.
</details>

## Summary

| Problem | Approach |
|---|---|
| Running many small tasks | A thread pool; `packaged_task` passes back results and exceptions; tasks run outside the lock |
| Shutting down the pool | `jthread`'s stop token + `condition_variable_any::wait(lock, stoken, pred)`; `request_stop` all threads, then `join` |
| `std::async` | Write `launch::async` explicitly; keep the returned `future`, or its destructor blocks |
| Producers faster than consumers | Bounded queue with two condition variables |
| Low-latency one-to-one handoff | SPSC ring buffer, two release/acquire pairs, indices on separate cache lines |
| Many-to-many lock-free structures | Use locks first; if it must be lock-free, handle ABA and reclamation (hazard pointers, RCU) |
| Many independent per-element computations | `std::execution::par` (libc++ needs `-fexperimental-library`); element functions must not throw; floating-point reductions have no guaranteed order |
| Locking several mutexes | Lock them at once with `std::scoped_lock`, or use a fixed order |
| Waiting for a condition | Keep the state in a lock-protected variable, modify it under the lock, wait with a predicate |
| Several threads reading and writing the same `shared_ptr` variable | Protect it with a mutex, or `std::atomic<std::shared_ptr<T>>` |
| Checking | TSan for data races, though it has both false negatives and false positives; stress tests on weakly ordered hardware |
