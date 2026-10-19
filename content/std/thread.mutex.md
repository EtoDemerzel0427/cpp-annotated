---
title: 互斥
summary: <mutex> 与 <shared_mutex> 提供了哪些互斥量、锁和一次调用工具，各自用在什么场合；为什么只有 std::mutex 保证常量初始化。
status: done
covers: thread.mutex.general, mutex.syn, shared.mutex.syn
related: thread.mutex.requirements, thread.lock, thread.once, thread.req, thread.condition, intro.multithread
tags: 标准库, 并发, 互斥量, 导读
updated: 2026-10-19
---

!!! tldr
    - 互斥量本身不阻止数据竞争。它提供的是同步：`unlock()` 与随后获得同一互斥量的加锁操作同步。保护来自每次访问共享数据都持有同一把锁。
    - `<mutex>` 提供四种互斥量、三种 RAII 锁、`std::lock`/`std::try_lock` 和 `call_once`；`<shared_mutex>` 提供两种读写锁和 `shared_lock`。
    - 默认用 `std::mutex`；读多写少用 `shared_mutex`；需要超时才用 timed 版本；递归互斥量通常说明设计可以改进。
    - 只有 `std::mutex` 的默认构造函数是 `constexpr`，所以命名空间作用域的 `std::mutex` 总是常量初始化的，不存在初始化顺序问题。

¶1 [thread.mutex] 提供三种互斥机制：互斥量、锁和一次调用（call once）。标准说它们让编写无竞争的程序更容易（[[intro.multithread]]）。这个说法很准确：互斥量只是建立 happens before 的手段，程序员仍须保证每次访问共享数据时都持有同一把锁。

## 组件一览

| 子条款 | 内容 | 本站笔记 |
|---|---|---|
| [mutex.syn]、[shared.mutex.syn] | 两个头文件的概要 | 本页 |
| [thread.mutex.requirements] | 互斥量的同步语义和六个互斥量类 | [[thread.mutex.requirements]] |
| [thread.lock] | RAII 锁 `lock_guard`、`scoped_lock`、`unique_lock`、`shared_lock`，以及标签 `defer_lock`、`try_to_lock`、`adopt_lock` | [[thread.lock]] |
| [thread.lock.algorithm] | `std::try_lock`、`std::lock`：不会死锁地锁住多个对象 | [[thread.lock]] |
| [thread.once] | `once_flag`、`call_once` | [[thread.once]] |

`<mutex>`（[mutex.syn]）声明 `mutex`、`recursive_mutex`、`timed_mutex`、`recursive_timed_mutex` 四个类；`lock_guard`、`scoped_lock`、`unique_lock` 三种锁；接受至少两个实参的 `try_lock` 和 `lock`；`once_flag` 和 `call_once`。

三个标签类型 `defer_lock_t`、`try_to_lock_t`、`adopt_lock_t` 的默认构造函数都是 `explicit` 的。这样 `{}` 不能隐式转换成某个标签，`unique_lock lk(m, {})` 这种含糊的写法无法通过编译。

`<shared_mutex>`（[shared.mutex.syn]）声明 `shared_mutex`、`shared_timed_mutex` 和 `shared_lock`。其中 `shared_timed_mutex` 是 C++14 加入的，比 `shared_mutex`（C++17）还早：C++14 先标准化了带超时的版本，C++17 才补上更简单、可能更快的无超时版本。

## 六种互斥量怎么选

| 类型 | 递归 | 超时 | 共享 | 适用场合 |
|---|---|---|---|---|
| `mutex` | 否 | 否 | 否 | 默认选择 |
| `recursive_mutex` | 是 | 否 | 否 | 持锁的函数会调用另一个也要加这把锁的函数（通常说明设计可以改进） |
| `timed_mutex` | 否 | 是 | 否 | 最多等待一段时间 |
| `recursive_timed_mutex` | 是 | 是 | 否 | 以上两者 |
| `shared_mutex` | 否 | 否 | 是 | 读多写少 |
| `shared_timed_mutex` | 否 | 是 | 是 | 读多写少，并且需要超时 |

## 只有 std::mutex 保证常量初始化

[[thread.mutex.requirements]] 中，只有 `mutex` 的默认构造函数声明为 `constexpr mutex() noexcept;`。所以命名空间作用域的 `std::mutex` 总是**常量初始化**的（[[basic.start.static]]），在任何动态初始化之前就已就绪。另一个翻译单元的动态初始化代码去锁它，也不会碰到一个还没构造的互斥量。

其他五种互斥量的构造函数不是 `constexpr` 的，在命名空间作用域使用它们时，要考虑跨翻译单元的初始化顺序。

## 实现视角

!!! impl "libc++/macOS 上的大小与实现（Clang 23，Apple Silicon）"
    | 类型 | `sizeof` | 底层 |
    |---|---|---|
    | `mutex` | 64 | `pthread_mutex_t`，静态初始化器 `PTHREAD_MUTEX_INITIALIZER` |
    | `recursive_mutex` | 64 | `pthread_mutex_t`，`PTHREAD_MUTEX_RECURSIVE` 属性 |
    | `timed_mutex` | 120 | 一个 `mutex`、一个 `condition_variable` 和一个 `bool` |
    | `shared_mutex` | 168 | 一个 `mutex`、两个 `condition_variable` 和一个状态字 |
    | `shared_timed_mutex` | 168 | 同上 |
    | `condition_variable` | 48 | `pthread_cond_t` |
    | `once_flag` | 8 | 一个状态字 |

    `timed_mutex` 和 `shared_mutex` 用条件变量自己实现，不包装 `pthread_rwlock_t` 之类的原生对象；macOS 的 pthreads 也没有 `pthread_mutex_timedlock`。所以它们的 `try_lock_for` 受 [[thread.req]] 中所述条件变量计时方式的影响。
