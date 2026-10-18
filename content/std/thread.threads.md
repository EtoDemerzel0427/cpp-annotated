---
title: 线程
summary: std::thread 与 std::jthread 逐条精读——"一个对象唯一表示一个执行线程"、实参在哪个线程被复制、构造与 join 建立的两条同步边、可 join 时析构即 terminate、jthread 的自动停止与 join、thread::id 的值复用，以及 this_thread 的 sleep/yield 不同步
status: done
covers: *
papers: P0660R10
related: intro.multithread, intro.progress, thread.stoptoken, thread.req, futures, basic.start.term, basic.stc.thread
tags: 标准库, 并发, thread, jthread
updated: 2026-10-18
---

[thread.threads] 是"创建线程"的唯一标准手段。核心语言的 [[intro.multithread]] 说"一个线程创建另一个线程时，新线程的顶层函数由新线程执行"，但没说怎么创建——答案在这里：构造一个 `std::thread` 或 `std::jthread`。

本页覆盖 [thread.threads] 的全部子条款：`<thread>` 概要、`thread` 类（含线程属性 `name_hint`/`stack_size_hint`、`thread::id`、构造、析构、赋值、成员、静态成员）、`jthread` 类、命名空间 `this_thread`。

## 总述（[thread.threads.general]、[thread.syn]）

[thread.threads.general] ¶1：本子条款描述创建与管理线程的组件。注 1：这些线程**意图与操作系统线程一一对应**。这句注不是规范，但它解释了很多设计：创建线程很贵（系统调用、分配栈），`thread` 不可复制，`hardware_concurrency()` 指的是硬件线程数。需要轻量任务时，标准的答案是 [[exec]] 而不是 `std::thread`。

`<thread>` 概要声明 `thread`、`swap`、`jthread`，以及 `this_thread` 里的 `get_id`、`yield`、`sleep_until`、`sleep_for`。它还包含 `<compare>`（`thread::id` 有 `<=>`）。

## thread 类（[thread.thread.class]）

### 对象与执行线程的对应关系（[thread.thread.class.general] ¶1）

> 一个 `thread` 对象**唯一地**表示一个特定的执行线程。这种表示可以转移给其他 `thread` 对象，但不会有两个 `thread` 对象**同时**表示同一个执行线程。当没有 `thread` 对象表示某个执行线程时，该线程是**分离的**（detached）。

所以 `thread` 是一种"唯一所有权"句柄，类似 `unique_ptr`：可移动、不可复制。注 1 列出 `thread` 对象**不表示**任何执行线程的三种情况：默认构造之后、被移动之后、成功调用 `detach()` 或 `join()` 之后。

类定义里的成员：`id`、线程属性 `name_hint`/`stack_size_hint`、`native_handle_type`（[[thread.req]] 的 native handle，存在与否由实现定义）、构造/析构/移动、`swap`、`joinable`、`join`、`detach`、`get_id`、`native_handle`、静态 `hardware_concurrency`。

### 线程属性（[thread.attributes]）

这是 C++23 之后加入草案的新措辞。

[thread.attributes.general]：

- ¶1 **线程属性**可以给 `thread`/`jthread` 对象定义额外的、由实现定义的行为；
- ¶2 **线程属性类型**的集合包括 `thread::name_hint`、`thread::stack_size_hint`，以及一组由实现定义的其他属性；
- ¶3 把线程属性对象传给 `thread`/`jthread` 的构造函数时，它**可能**影响新线程的行为——一切都是提示。

[thread.attributes.hint]：`name_hint<T>` 要求 `T` 是 `char`（模板形参写作 `same_as<char> T`），保存一个 `basic_string_view<T>`，不可复制也不可移动。¶1 它用于"出于调试或平台显示目的"设置线程名。两条*推荐做法*：实现**不应**把名字存进 `thread` 对象（名字交给操作系统就行，不该让 `sizeof(thread)` 变大）；名字按 `T` 的关联字符编码解释。

[thread.attributes.size]：`stack_size_hint` 保存一个 `size_t`。¶1 用于配置线程的平台相关存储（注 1：通常是自动存储期变量所在的栈）的期望字节数；¶2 实现可以上下调整以满足平台要求；¶3 为零时忽略该属性。

属性写在可调用对象**之前**：

```cpp
std::jthread t(std::thread::name_hint("io-worker"),
               std::thread::stack_size_hint(1 << 20),
               worker_fn, arg1, arg2);
```

构造函数从左往右找第一个"decay 后不是线程属性类型"的实参，把它当作可调用对象；它之前的都是属性，之后的都是实参（见下文 ¶4）。

!!! impl "libc++ 尚未实现"
    Clang 23 自带的 libc++ 中 `std::thread` 没有 `name_hint`、`stack_size_hint` 成员。上面的代码片段未经编译验证。目前在 macOS 上设置线程名只能在线程内部调用 `pthread_setname_np`。

### thread::id（[thread.thread.id]）

¶1 `thread::id` 为每个执行线程提供唯一标识，并为所有"不表示执行线程"的 `thread` 对象提供**同一个**独特的值。每个执行线程的 id 不等于任何其他执行线程的 id，也不等于不表示线程的 `thread` 对象的 id。

¶2 对字符类型 `charT`，id 的**文本表示**是一个未指定的字符序列 {{unspec}}，满足：相等的 id 文本相同，不等的 id 文本不同。

¶3 `thread::id` 是**可平凡复制**的类。**库可以复用一个已终止且再也不能被 join 的线程的 id 值。** 这意味着用 `thread::id` 作为键来记录"哪个线程做过什么"时，旧线程结束后它的 id 可能被新线程拿到——不能把它当作全局唯一、永不重复的标识。

¶4 注 1：关系运算符使 `thread::id` 可以作为关联容器的键。

¶5 默认构造的 id 不表示任何执行线程。¶6 `==`：表示同一执行线程，或都不表示任何线程。¶7–¶8 `<=>`：基于一个未指定的全序 P(x, y)（[[alg.sorting]]），返回 `strong_ordering`。

¶9–¶10 `operator<<` 插入文本表示。¶11–¶13 `formatter<thread::id, charT>` 接受的格式说明只有 *fill-and-align* 和 *width*，¶12 对齐默认为 `>`（右对齐，像数字一样）。¶14 `hash<thread::id>` 已启用。

```cpp run title="thread-id.cpp" ok
#include <format>
#include <iostream>
#include <thread>
#include <type_traits>

int main() {
  static_assert(std::is_trivially_copyable_v<std::thread::id>);   // ¶3
  std::cout << std::format("[{:>20}]\n", std::this_thread::get_id());
  std::cout << std::format("[{}]\n", std::thread::id{});          // "不表示线程"的那个值
}
```

在 libc++/macOS 上，第一行打印 `pthread_t` 转成的整数（右对齐到 20 列），第二行打印 `[0]`。具体文本是未指定的，不要解析它。

### 构造（[thread.thread.constr]）

¶1–¶2 默认构造函数：不表示任何执行线程，`get_id() == id()`。

`template<class... Args> explicit thread(Args&&... args)` 是重点：

¶3 *Constraints*：`Args` 不是空包，且 `remove_cvref_t<Args...[0]>` 不是 `thread`（防止它劫持移动构造）。

¶4 设 `i` 是使 `decay_t<Args...[i]>` **不是**线程属性类型的最小下标。则 `F`/`f` 是第 `i` 个，`Attrs`/`attrs` 是它之前的，`FArgs`/`fargs` 是它之后的。

¶5 *Mandates*（违反则非良构）：`i` 存在；`decay_t<F>` 可从 `F` 构造；每个 `decay_t<FArgs>` 可从对应 `FArgs` 构造；`is_invocable_v<decay_t<F>, decay_t<FArgs>...>`；`Attrs` 中没有重复类型。

¶6 *Effects*：新执行线程执行

```cpp
invoke(auto(std::forward<F>(f)), auto(std::forward<FArgs>(fargs))...)
```

**其中 `auto(...)` 产生的值在构造线程中物化**（[[conv.rval]]）。返回值被忽略。注 1：这意味着复制 `f` 与实参时抛出的异常**在构造线程中**抛出，而不是在新线程中。若 `invoke` 以未捕获的异常终止，调用 `std::terminate`。

两个要点：

1. **实参总是被复制（或移动）一份**，新线程用的是副本。`std::thread t(f, x)` 里，即使 `f` 的形参是 `int&`，传入的也是 `x` 的副本——而且由于副本以右值传给 `invoke`，`int&` 根本绑不上，¶5 的 *Mandates* 不满足，程序非良构。需要传引用时用 `std::ref`。
2. **副本在构造线程中创建**，所以构造函数返回时副本已经存在，原实参可以销毁。但如果副本本身是指针或 `reference_wrapper`，它指向的东西仍须活着。

```cpp run title="thread-ref.cpp" ok
#include <cstdio>
#include <functional>
#include <thread>

void inc(int& x) { ++x; }

int main() {
  int n = 0;
  // std::thread t0(inc, n);        // error：decay 后的 int 右值不能绑定到 int&（¶5.3）
  std::thread t1(inc, std::ref(n));  // OK：显式传引用
  t1.join();                         // join 返回之后读取 n：线程完成 synchronizes with join 返回
  std::printf("%d\n", n);            // 1
}
```

取消注释 `t0` 那一行，libc++ 在 `<__thread/thread.h>` 里以 `static_assert` 失败报错，提示 `__is_invocable_v<void (*)(int &), int>` 不成立。

¶7 *Synchronization*：

!!! std
    The completion of the invocation of the constructor synchronizes with the beginning of the invocation of the copy of `f`.

    构造函数调用的完成，与 `f` 的副本的调用开始同步。

这是线程模型的第一条同步边：创建线程**之前**的所有写，对新线程**可见**。所以"先准备好数据，再启动线程去处理"不需要任何额外同步。

¶8 *Postconditions*：`get_id() != id()`，`*this` 表示新启动的线程。¶9–¶10 无法启动线程时抛 `system_error`，错误条件 `resource_unavailable_try_again`（资源不足或超出进程线程数上限）。

¶11 移动构造：`x.get_id() == id()`，`*this` 接管 `x` 原来表示的线程。

### 析构与赋值：可 join 就 terminate（[thread.thread.destr]、[thread.thread.assign]）

[thread.thread.destr] ¶1：若 `joinable()`，调用 `std::terminate`；否则无效果。

注 1 解释了为什么不选择"析构时自动 join"或"自动 detach"：自动 detach 会造成难以调试的**正确性**问题（线程还在访问已销毁的局部变量），自动 join 会造成难以调试的**性能**问题（异常展开时意外地阻塞等待）——而且两者都"只在抛异常时才出现"。所以干脆要求程序员在析构前显式处理。

```cpp run title="joinable-dtor.cpp" ok
#include <thread>
int main() {
  std::thread t([] {});
}   // ~thread：t 仍 joinable，调用 std::terminate（行为有定义，但程序被终止）
```

[thread.thread.assign] ¶1：移动赋值时，若 `*this` 是 `joinable()`，同样调用 `std::terminate`；否则接管 `x` 的状态并把 `x` 置为默认构造状态。¶2–¶3 后置条件与返回值。

!!! pitfall "构造与 join 之间的异常"
    ```cpp
    void f() {
      std::thread t(work);
      do_something();   // 若抛异常，栈展开时 ~thread 发现 t 可 join → terminate
      t.join();
    }
    ```
    这是 `std::thread` 最常见的误用。C++20 的解决办法是改用 `std::jthread`，它的析构函数会请求停止并 join。

### 成员函数（[thread.thread.member]）

- ¶1 `swap`。¶2 `joinable()` 返回 `get_id() != id()`。
- ¶3 `join()`：阻塞直到 `*this` 表示的线程完成。
- ¶4 *Synchronization*：该线程的完成 **synchronizes with** 对应的成功 `join()` 返回。注 1：**对 `*this` 本身的操作不同步**——两个线程同时对同一个 `thread` 对象调用 `join()` 是数据竞争。
- ¶5 后置条件：线程已完成，`get_id() == id()`。
- ¶6–¶7 错误条件：`resource_deadlock_would_occur`（检测到死锁，或 `get_id() == this_thread::get_id()`，即线程 join 自己）、`no_such_process`（线程无效）、`invalid_argument`（不可 join）。
- ¶8 `detach()`：线程继续执行，调用线程不阻塞；返回后 `*this` 不再表示该线程；线程结束时实现释放它拥有的资源。¶9–¶11 后置条件与错误条件（`no_such_process`、`invalid_argument`）。
- ¶12 `get_id()`：不表示线程时返回默认 id，否则返回那个线程的 `this_thread::get_id()`。

¶4 是第二条同步边：线程的**所有**副作用（包括 `thread_local` 对象的析构，因为它们发生在线程"完成"之前）对 `join()` 之后的代码可见。被 detach 的线程**没有**这条边：要想安全地读取 detach 线程写的数据，必须另外同步（原子变量、promise、`notify_all_at_thread_exit` 等）。

```cpp title="detach-dangling.cpp" ub
#include <thread>
void start() {
  int local = 0;
  std::thread([&local] { ++local; }).detach();   // UB：线程可能在 start 返回后访问已销毁的 local
}
int main() { start(); }
```

!!! pitfall "detach 的线程与程序退出"
    `main` 返回后开始执行静态存储期对象的析构（[[basic.start.term]]）。仍在运行的 detach 线程如果访问这些对象（包括 `std::cout`、全局容器、单例），行为未定义。detach 并不意味着"不用管了"；它只是放弃了 join 这条同步边。

### 静态成员与特化算法（[thread.thread.static]、[thread.thread.algorithm]）

[thread.thread.static] ¶1：`hardware_concurrency()` 返回硬件线程上下文的数量。注 1：只应作为**提示**；无法计算或没有明确定义时，实现应返回 0。所以 `std::max(1u, std::thread::hardware_concurrency())` 是常见写法。

[thread.thread.algorithm] ¶1：非成员 `swap(x, y)` 如同 `x.swap(y)`。

## jthread 类（[thread.jthread.class]） {{c++20}}

[thread.jthread.class.general] ¶1：`jthread` 的功能与 `thread` 相同，另外能向新线程提供 `stop_token`、发出停止请求，并**自动 join**。类里有一个仅说明用的成员 `stop_source ssource`。

### 构造（[thread.jthread.cons]）

- ¶1–¶2 默认构造：不表示线程，`ssource.stop_possible()` 为 `false`（即用 `nostopstate` 构造，不分配停止状态）。
- ¶3–¶5 与 `thread` 相同的约束和 *Mandates*，只是可调用性改为：`is_invocable_v<decay_t<F>, decay_t<FArgs>...>` **或** `is_invocable_v<decay_t<F>, stop_token, decay_t<FArgs>...>`。
- ¶6 *Effects*：初始化 `ssource`。若

  ```cpp
  invoke(auto(std::forward<F>(f)), get_stop_token(), auto(std::forward<FArgs>(fargs))...)
  ```

  良构就执行它，否则执行不带 `stop_token` 的版本。也就是说，**可调用对象的第一个形参能接受 `stop_token`，就会自动传给它**。
- ¶7 同步规则与 `thread` 相同。
- ¶8 后置条件：`ssource.stop_possible()` 为 `true`。注 3：调用线程只能发出一次停止请求，因为它不能替换这个停止令牌。
- ¶11 移动构造：接管 `x` 的线程和 `ssource`，之后 `x.ssource.stop_possible()` 为 `false`。

!!! lawyer "“如果良构”会抢走第一个实参"
    ¶6 的判断依据只是"`invoke(f, stop_token, args...)` 是否良构"，不看你的意图。泛型可调用对象很容易让带令牌的版本意外地良构：

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
      std::jthread t(f, 42);   // 打印 "x is stop_token: 1, y = 42"，而不是 x = 42, y = 0
    }
    ```

    `invoke(f, stop_token, 42)` 良构（`x` 推导为 `stop_token`，`y` 取 42），于是优先选它。

### 析构与赋值（¶12–¶15）

¶12 析构函数：若 `joinable()`，**先调用 `request_stop()`，再调用 `join()`**。注 4：对 `*this` 的操作不同步。

¶13 移动赋值：若 `&x == this` 无效果；否则若 `joinable()`，先 `request_stop()` 再 `join()`，然后接管 `x` 的状态。注意这与 `thread` 的移动赋值（直接 terminate）不同。

析构时先请求停止再 join，顺序很重要：如果线程函数在循环里检查 `stop_token`，请求停止让它退出循环，join 才不会永远阻塞。但这只对**检查了令牌**的线程函数有效；不看令牌的线程函数会让 `~jthread` 一直等到它自然结束。

```cpp run title="jthread-stop.cpp" ok
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

`condition_variable_any` 的可中断等待会在停止请求时被唤醒（[[thread.condition]]），所以 `~jthread` 不会卡住。如果把 `cv` 换成 `std::condition_variable`，它没有接受 `stop_token` 的 `wait`，线程会一直睡在条件变量上。

### 其他成员（[thread.jthread.mem]、[thread.jthread.stop]、[thread.jthread.special]、[thread.jthread.static]）

[thread.jthread.mem] 的 `swap`、`joinable`、`join`（同样的同步规则与错误条件）、`detach`、`get_id` 与 `thread` 完全相同。

[thread.jthread.stop]：

- ¶1 `get_stop_source()` 返回 `ssource` 的副本——可以交给别人，让他们也能请求停止；
- ¶2 `get_stop_token()` 返回 `ssource.get_token()`；
- ¶3 `request_stop()` 返回 `ssource.request_stop()`。

detach 之后 `jthread` 仍然持有 `ssource`，所以仍可以对已分离的线程发出停止请求。

[thread.jthread.special] 友元 `swap`；[thread.jthread.static] `hardware_concurrency()` 返回 `thread::hardware_concurrency()`。

## this_thread（[thread.thread.this]）

- ¶1 `get_id()`：返回唯一标识当前执行线程的 id；同一线程每次调用返回相同值；不等于默认构造的 id。
- ¶2–¶3 `yield()`：给实现一个重新调度的机会。*Synchronization*：无。
- ¶4–¶6 `sleep_until(abs_time)`：阻塞调用线程直到绝对超时（[[thread.req]]）。*Synchronization*：无。*Throws*：超时相关异常。
- ¶7–¶9 `sleep_for(rel_time)`：阻塞调用线程一个相对超时。*Synchronization*：无。*Throws*：超时相关异常。

三处 "*Synchronization*: None" 不是废话：它们堵死了"睡一会儿等别的线程写完"这种推理（见 [[thread]] 的反例）。`yield()` 也不是同步原语——它甚至不保证真的让出 CPU。在自旋等待里，`yield()` 只是礼貌，循环条件本身必须是原子读。

## 实现视角

!!! impl "libc++/macOS"
    - `sizeof(std::thread) == 8`（一个 `pthread_t`），`sizeof(std::jthread) == 16`（再加一个 `stop_source`，即一个侵入式指针）。
    - `std::thread` 的构造函数把一个 `unique_ptr<__thread_struct>`（线程局部的簿记数据）与 `f`、实参的副本打包成一个 `tuple`，`new` 到堆上，再把指针交给 `pthread_create`；新线程的入口函数 `__thread_proxy` 取回这个 `tuple` 并调用。所以 ¶6"在构造线程中物化"就是在构造这个 `tuple` 时完成的。
    - `hardware_concurrency()` 在本机（12 核 Apple Silicon）返回 12。

## 历史与演进

!!! history "从 thread 到 jthread"
    - **C++11**：引入 `std::thread`，析构可 join 线程即 terminate 的规则从一开始就存在。
    - **C++20**：[[P0660R10]] 引入 `jthread` 与停止令牌（[[thread.stoptoken]]），把取消定型为"协作式取消 + 自动 join"。
    - 实参复制的规范原先用仅说明用的 *decay-copy* 表述，现行草案改用 `auto(...)` 加"在构造线程中物化"，含义不变。
    - **C++23 之后**：线程属性 `name_hint`、`stack_size_hint` 进入草案，构造函数的规范随之改为"先找第一个非属性实参"的写法。

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

没有，返回 2。`x = 1` sequenced before 构造函数完成，构造函数完成 synchronizes with lambda 开始（¶7），所以 `x = 1` happens before `x = 2`；线程完成 synchronizes with `join()` 返回（[thread.thread.member] ¶4），所以 `x = 2` happens before `return x`。三次访问被 happens before 完全排序。
</details>

!!! question "2. `std::thread t(f, std::string("abc"));` 中，`std::string` 的移动发生在哪个线程？若内存不足，异常在哪里抛出？"

<details markdown="1">
<summary>答案</summary>

¶6：`auto(std::forward<FArgs>(fargs))` 产生的值在**构造线程**中物化，所以移动构造发生在调用 `thread` 构造函数的线程里，任何异常（包括为保存副本分配内存时的 `bad_alloc`）都从构造函数抛出，新线程根本不会启动。只有 `f` 本身执行时抛出的异常才发生在新线程，且导致 `terminate`。
</details>

## 小结

| | `thread` | `jthread` |
|---|---|---|
| 析构时可 join | `std::terminate` | `request_stop()` 然后 `join()` |
| 移动赋值给可 join 对象 | `std::terminate` | `request_stop()` 然后 `join()` |
| 停止令牌 | 无 | 可调用对象第一个形参能接受 `stop_token` 时自动传入 |
| 同步边 | 构造完成 → 线程函数开始；线程完成 → `join()` 返回 | 同左 |
| 实参 | 在构造线程中复制/移动；需引用时用 `std::ref` | 同左 |

- `this_thread::sleep_*` 与 `yield` 没有任何同步作用。
- `thread::id` 的值可以在线程结束后被复用。
