---
title: 线程
summary: std::thread 与 std::jthread：实参在哪个线程被复制、构造和 join 建立的两条同步关系、可 join 的 thread 析构时为何调用 terminate、jthread 怎样自动请求停止并 join，以及 thread::id、线程属性和 this_thread。
status: done
covers: *
papers: P0660R10, P2019R8
related: intro.multithread, intro.progress, thread.stoptoken, thread.req, futures, basic.start.term, basic.stc.thread
tags: 标准库, 并发, thread, jthread
updated: 2026-10-19
---

!!! tldr
    - 线程函数的实参总是被复制或移动一份，副本在创建线程的那个线程里构造；要传引用，用 `std::ref`。
    - 两条同步关系：构造函数完成与线程函数开始同步，线程结束与 `join()` 返回同步。启动前写的数据新线程能看到，线程写的数据 `join()` 之后能看到。
    - `std::thread` 在可 join 状态下析构或被移动赋值，调用 `std::terminate`；`std::jthread` 改为先请求停止再 join。
    - `jthread` 的可调用对象如果能以 `stop_token` 为第一个实参调用，就会自动收到一个停止令牌。
    - `sleep_for`、`yield` 不提供任何同步；`thread::id` 的值在线程结束后可能被复用。

[[intro.multithread]] 说一个线程可以创建另一个线程，但没说怎么创建。答案在这里：构造一个 `std::thread` 或 `std::jthread`。[[thread.threads.general]] 注 1 说明，这些线程意在与操作系统线程一一对应。所以创建线程开销不小（系统调用、分配栈），`thread` 不可复制，`hardware_concurrency()` 指的是硬件线程数。

## 创建线程 [thread.thread.constr]

### 实参被复制到哪里

```cpp run title="thread-ref.cpp" ok
#include <cstdio>
#include <functional>
#include <thread>

void inc(int& x) { ++x; }

int main() {
  int n = 0;
  // std::thread t0(inc, n);        // error: 副本是右值，不能绑定到 int&
  std::thread t1(inc, std::ref(n));  // OK：显式传引用
  t1.join();
  std::printf("%d\n", n);            // 1
}
```

`template<class... Args> explicit thread(Args&&... args)` 是创建线程的构造函数。¶3 要求 `Args` 非空，且第一个实参去掉引用和 cv 后不是 `thread`，否则它会抢走移动构造函数的位置。

¶4 C++23 之后，实参列表开头可以放几个线程属性（见下文）。构造函数取第一个退化（decay）后不是线程属性类型的实参作为可调用对象 `f`，它之前的是属性，之后的是传给 `f` 的实参 `fargs`。

¶6 新线程执行

```cpp
invoke(auto(std::forward<F>(f)), auto(std::forward<FArgs>(fargs))...)
```

其中 `auto(...)` 产生的值在构造线程中物化（[[conv.rval]]），返回值被忽略。由此得到两点：

1. 实参总是被复制或移动一份，新线程用的是副本。上例中 `inc` 的形参是 `int&`，`std::thread t0(inc, n)` 传过去的是 `n` 的副本，而且是右值，绑不到 `int&` 上。¶5 的 *Mandates* 要求 `is_invocable_v<decay_t<F>, decay_t<FArgs>...>`，不满足就非良构。要传引用，用 `std::ref`。
2. 副本在构造线程中创建，构造函数返回时副本已经存在，原来的实参可以销毁。注 1 指出，复制 `f` 和实参时抛出的异常因此从构造函数抛出，不会出现在新线程中。只有 `invoke` 本身以异常退出时，才调用 `std::terminate`。

取消上例中 `t0` 那行的注释，libc++ 在 `<__thread/thread.h>` 中以 `static_assert` 失败报错，指出 `__is_invocable_v<void (*)(int &), int>` 不成立。

### 第一条同步关系

!!! std
    The completion of the invocation of the constructor synchronizes with the beginning of the invocation of the copy of `f`.

¶7 构造函数调用的完成，与 `f` 的副本开始执行同步。所以创建线程之前的所有写，新线程都能看到。先准备好数据、再启动线程去处理，不需要额外同步。

¶8 构造成功后 `get_id() != id()`，`*this` 表示新线程。¶9–¶10 无法启动线程时抛 `system_error`，错误条件是 `resource_unavailable_try_again`，表示资源不足或超出了进程的线程数上限。

¶1–¶2 默认构造的 `thread` 不表示任何线程。¶11 移动构造之后，`*this` 接管 `x` 原来表示的线程，`x` 不再表示任何线程。

### 一个对象表示一个线程 [thread.thread.class.general]

¶1 一个 `thread` 对象唯一地表示一个执行线程。这种表示可以转移给另一个 `thread` 对象，但任何时候不会有两个 `thread` 对象同时表示同一个线程。没有任何 `thread` 对象表示的线程叫做**分离的**（detached）。

所以 `thread` 像 `unique_ptr` 一样，可移动、不可复制。注 1 列出了 `thread` 不表示任何线程的三种情况：默认构造之后，被移动之后，成功调用 `detach()` 或 `join()` 之后。

## 等待线程结束 [thread.thread.member]

### join 与第二条同步关系

¶3 `join()` 阻塞到 `*this` 表示的线程完成。¶4 这个线程的完成与对应的成功 `join()` 返回同步。线程的全部副作用，包括 `thread_local` 对象的析构，在 `join()` 之后都可见。

注 1 补充，对 `*this` 本身的操作不同步：两个线程同时对同一个 `thread` 对象调用 `join()` 是数据竞争。

¶5 返回后 `get_id() == id()`。¶6–¶7 列出了三种错误条件：`resource_deadlock_would_occur`（检测到死锁，或者线程 join 自己）、`no_such_process`（线程无效）、`invalid_argument`（不可 join）。¶2 `joinable()` 就是 `get_id() != id()`。

### detach

¶8 `detach()` 让线程继续运行，调用者不阻塞，`*this` 不再表示这个线程，线程结束时由实现释放资源。被分离的线程没有 join 那条同步关系，要读它写的数据，必须另外同步，例如原子变量、`promise` 或 `notify_all_at_thread_exit`。

```cpp title="detach-dangling.cpp" ub
#include <thread>
void start() {
  int local = 0;
  std::thread([&local] { ++local; }).detach();   // UB：线程可能在 start 返回后访问已销毁的 local
}
int main() { start(); }
```

!!! pitfall "分离的线程与程序退出"
    `main` 返回后，静态存储期对象开始析构（[[basic.start.term]]）。仍在运行的分离线程如果访问这些对象，包括 `std::cout`、全局容器和单例，行为未定义。

¶12 `get_id()` 不表示线程时返回默认构造的 `id`，否则返回那个线程中 `this_thread::get_id()` 的值。

### 析构与赋值：可 join 就 terminate

```cpp run title="joinable-dtor.cpp" ok
#include <thread>
int main() {
  std::thread t([] {});
}   // ~thread：t 仍可 join，调用 std::terminate
```

[thread.thread.destr] ¶1：析构时如果 `joinable()`，调用 `std::terminate`，否则什么也不做。这个程序的行为是有定义的，结果就是被终止，本机输出 `libc++abi: terminating`。

注 1 解释了为什么不在析构时自动 join 或自动分离。自动分离会带来难以调试的正确性问题：线程可能还在访问已经销毁的局部变量。自动 join 会带来难以调试的性能问题：栈展开时意外地阻塞等待。而且这两种问题都只在抛出异常时才出现。所以标准要求程序员在析构之前显式处理。

[thread.thread.assign] ¶1：移动赋值时如果 `*this` 可 join，同样调用 `std::terminate`；否则接管 `x` 的线程，并把 `x` 置为默认构造的状态。

!!! pitfall "构造与 join 之间抛出异常"
    ```cpp
    void f() {
      std::thread t(work);
      do_something();   // 若抛异常，栈展开时 ~thread 发现 t 可 join，调用 terminate
      t.join();
    }
    ```
    这是 `std::thread` 最常见的误用。C++20 起可以改用 `std::jthread`。

## jthread {{c++20}}

[thread.jthread.class.general] ¶1：`jthread` 的功能与 `thread` 相同，另外能向新线程提供停止令牌（[[thread.stoptoken]]）、发出停止请求，并在析构时自动 join。类里有一个仅说明用的成员 `stop_source ssource`。

### 析构时先请求停止再 join [thread.jthread.cons]

```cpp run title="jthread-stop.cpp" ok
#include <chrono>
#include <condition_variable>
#include <cstdio>
#include <deque>
#include <mutex>
#include <thread>

std::mutex m;
std::condition_variable_any cv;
std::deque<int> q;

int main() {
  std::jthread worker([](std::stop_token st) {
    std::unique_lock lk(m);
    while (true) {
      // 有任务或收到停止请求时返回；返回值是谓词的最终结果
      if (!cv.wait(lk, st, [] { return !q.empty(); }))
        break;                      // 收到停止请求，且队列为空
      int x = q.front(); q.pop_front();
      lk.unlock();
      std::printf("got %d\n", x);
      lk.lock();
    }
    std::puts("worker: stop requested");
  });
  {
    std::lock_guard lk(m);
    q.push_back(1);
  }
  cv.notify_one();
  std::this_thread::sleep_for(std::chrono::milliseconds(50));
}   // ~jthread：request_stop() 唤醒 cv.wait，然后 join()
```

¶12 析构时如果 `joinable()`，先调用 `request_stop()`，再调用 `join()`。顺序很重要：线程函数在循环里检查停止令牌，停止请求让它退出循环，`join()` 才不会一直等下去。不检查令牌的线程函数，会让 `~jthread` 一直等到它自然结束。

上例中 `condition_variable_any` 的可中断等待会被停止请求唤醒（[[thread.condition]]）。换成 `std::condition_variable`，它没有接受 `stop_token` 的 `wait`，线程会一直睡在条件变量上。

¶13 移动赋值也一样：如果 `*this` 可 join，先请求停止再 join，然后接管 `x` 的状态。`&x == this` 时什么也不做。这与 `thread` 移动赋值时直接 terminate 不同。

### 自动传入停止令牌 [thread.jthread.cons]

¶6 `jthread` 的构造函数先初始化 `ssource`。如果

```cpp
invoke(auto(std::forward<F>(f)), get_stop_token(), auto(std::forward<FArgs>(fargs))...)
```

良构，新线程就执行它，否则执行不带停止令牌的版本。所以可调用对象能以 `stop_token` 为第一个实参调用时，就会自动收到令牌。¶5 相应地把可调用性要求放宽为两种调用之一可行即可。¶7 的同步规则与 `thread` 相同。

!!! lawyer "能良构就抢走第一个实参"
    ¶6 只看带令牌的调用是否良构，不看你的意图。泛型可调用对象很容易让它意外地良构：

    ```cpp run title="jthread-generic.cpp" ok
    #include <cstdio>
    #include <stop_token>
    #include <thread>
    #include <type_traits>
    int main() {
      auto f = [](auto x, int y = 0) {
        std::printf("x is stop_token: %d, y = %d\n",
                    (int)std::is_same_v<decltype(x), std::stop_token>, y);
      };
      std::jthread t(f, 42);   // 打印 "x is stop_token: 1, y = 42"
    }
    ```

    `invoke(f, stop_token, 42)` 良构，`x` 推导为 `stop_token`，`y` 取 42，于是选中了它。

¶8 构造之后 `ssource.stop_possible()` 为 `true`。注 3 指出，调用线程只能发出一次停止请求，因为它不能替换这个停止令牌。¶1–¶2 默认构造的 `jthread` 不分配停止状态，`ssource.stop_possible()` 为 `false`。¶11 移动构造之后，`x` 的停止源变为脱离状态。

### 其他成员

[thread.jthread.mem] 的 `swap`、`joinable`、`join`、`detach`、`get_id` 与 `thread` 的相同，`join` 的同步规则和错误条件也相同。[thread.jthread.stop] 提供 `get_stop_source()`（返回 `ssource` 的副本，交给别人后他们也能请求停止）、`get_stop_token()` 和 `request_stop()`。`detach()` 之后 `jthread` 仍然持有 `ssource`，所以仍然可以向已分离的线程发出停止请求。

## thread::id [thread.thread.id]

```cpp run title="thread-id.cpp" ok
#include <format>
#include <iostream>
#include <thread>
#include <type_traits>

int main() {
  static_assert(std::is_trivially_copyable_v<std::thread::id>);
  std::cout << std::format("[{:>20}]\n", std::this_thread::get_id());
  std::cout << std::format("[{}]\n", std::thread::id{});   // 不表示任何线程的值
}
```

本机 libc++ 第一行打印由 `pthread_t` 转成的整数，右对齐到 20 列；第二行打印 `[0]`。具体文本是未指定的，不要解析它。

¶1 `thread::id` 为每个执行线程提供唯一的标识，所有不表示线程的 `thread` 对象共用另一个独特的值。¶2 id 的文本表示是未指定的字符序列，只保证相等的 id 文本相同、不等的 id 文本不同。

¶3 `thread::id` 是可平凡复制的类。库可以复用一个已经终止、再也不能被 join 的线程的 id 值。所以用 `thread::id` 作键记录每个线程做过什么时，旧线程结束后，它的 id 可能被新线程拿到。

¶5–¶8 默认构造的 id 不表示线程；`==` 判断是否表示同一线程或都不表示线程；`<=>` 基于一个未指定的全序，返回 `strong_ordering`，注 1 指出这让 `thread::id` 可以作关联容器的键。¶9–¶14 还提供 `operator<<`、`formatter`（只接受填充、对齐和宽度，对齐默认是右对齐）和 `hash`。

## 线程属性 [thread.attributes]

```cpp
std::jthread t(std::thread::name_hint("io-worker"),
               std::thread::stack_size_hint(1 << 20),
               worker_fn, arg1, arg2);
```

这是 C++23 之后加入草案的特性（[[P2019R8]]）。[thread.attributes.general] ¶1–¶3：**线程属性**可以给 `thread` 或 `jthread` 定义额外的、由实现定义的行为；线程属性类型包括 `thread::name_hint`、`thread::stack_size_hint` 和实现定义的其他类型；把属性对象传给构造函数时，它可能影响新线程的行为。它们都只是提示。属性写在可调用对象之前。

`name_hint<T>` 要求 `T` 是 `char`，保存一个 `basic_string_view<T>`，不可复制也不可移动。[thread.attributes.hint] ¶1 说明它用于出于调试或平台显示的目的设置线程名，*推荐做法*是不把名字存进 `thread` 对象，免得 `sizeof(thread)` 变大。

`stack_size_hint` 保存一个 `size_t`，表示线程所需的平台相关存储的期望字节数，注 1 说明这通常是放自动变量的栈（[thread.attributes.size] ¶1）。实现可以为满足平台要求而上下调整（¶2），值为零时忽略（¶3）。

!!! impl "libc++ 尚未实现"
    Clang 23 自带的 libc++ 中 `std::thread` 没有 `name_hint`、`stack_size_hint` 成员，上面的片段未经编译验证。目前在 macOS 上设置线程名，只能在线程内部调用 `pthread_setname_np`。

## this_thread 与其他函数 [thread.thread.this]

- ¶1 `get_id()` 返回唯一标识当前线程的 id，同一线程每次调用返回相同的值，且不等于默认构造的 id。
- ¶2–¶3 `yield()` 给实现一个重新调度的机会，*Synchronization*: None。
- ¶4–¶6 `sleep_until(abs_time)` 阻塞到绝对超时（[[thread.req]]），*Synchronization*: None，可能抛超时相关异常。
- ¶7–¶9 `sleep_for(rel_time)` 阻塞一个相对超时，同样没有同步。

三处 *Synchronization*: None 排除了睡一会儿等别的线程写完这类推理。`yield()` 也不是同步原语，它甚至不保证真的让出 CPU；自旋等待时，循环条件本身必须是原子读。

[thread.thread.static] ¶1 `hardware_concurrency()` 返回硬件线程上下文的数量。注 1 说明它只是提示，无法计算时实现应返回 0，所以常见写法是 `std::max(1u, std::thread::hardware_concurrency())`。

## 实现视角

!!! impl "libc++ 在 macOS 上"
    - `sizeof(std::thread)` 为 8，就是一个 `pthread_t`；`sizeof(std::jthread)` 为 16，多了一个 `stop_source`。
    - `std::thread` 的构造函数把一个 `unique_ptr<__thread_struct>`（线程局部的簿记数据）与 `f`、实参的副本打包成一个 `tuple`，在堆上分配，再把指针交给 `pthread_create`。新线程的入口 `__thread_proxy` 取回这个 `tuple` 并调用。¶6 所说的在构造线程中物化，就发生在构造这个 `tuple` 的时候。
    - 本机（12 核 Apple Silicon）`hardware_concurrency()` 返回 12。

## 历史与演进

!!! history "从 thread 到 jthread"
    - C++11 引入 `std::thread`，可 join 时析构即 terminate 的规则从一开始就存在。
    - C++20 的 [[P0660R10]] 引入 `jthread` 和停止令牌，把取消定为协作式取消加自动 join。
    - 实参复制原来用仅说明用的 *decay-copy* 表述，现行草案改用 `auto(...)` 加在构造线程中物化，含义不变。
    - C++23 之后，线程属性进入草案，构造函数的规格随之改为先找第一个非属性实参。

## 思考题

!!! question "1. 下面的程序有数据竞争吗？"
    ```cpp
    int x = 0;
    int main() {
      x = 1;
      std::thread t([] { x = 2; });
      t.join();
      return x;
    }
    ```

<details markdown="1">
<summary>答案</summary>

没有，返回 2。`x = 1` 按顺序先于构造函数完成，构造函数完成与 lambda 开始同步（[thread.thread.constr] ¶7），所以 `x = 1` happens before `x = 2`。线程完成与 `join()` 返回同步（[thread.thread.member] ¶4），所以 `x = 2` happens before `return x`。三次访问都由 happens before 排好了顺序。
</details>

!!! question "2. `std::thread t(f, std::string("abc"));` 中，`std::string` 的移动发生在哪个线程？内存不足时异常从哪里抛出？"

<details markdown="1">
<summary>答案</summary>

按 [thread.thread.constr] ¶6，`auto(std::forward<FArgs>(fargs))` 产生的值在构造线程中物化，所以移动构造发生在调用构造函数的线程里。任何异常，包括为保存副本分配内存时的 `bad_alloc`，都从构造函数抛出，新线程根本不会启动。只有 `f` 执行时抛出的异常才发生在新线程，并导致 `terminate`。
</details>

## 小结

| | `thread` | `jthread` |
|---|---|---|
| 析构时可 join | `std::terminate` | `request_stop()` 然后 `join()` |
| 移动赋值给可 join 的对象 | `std::terminate` | `request_stop()` 然后 `join()` |
| 停止令牌 | 无 | 可调用对象能接受 `stop_token` 作第一个实参时自动传入 |
| 同步关系 | 构造完成 → 线程函数开始；线程完成 → `join()` 返回 | 相同 |
| 实参 | 在构造线程中复制或移动；传引用用 `std::ref` | 相同 |
