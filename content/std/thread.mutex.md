---
title: 互斥
summary: [thread.mutex] 导读——<mutex> 与 <shared_mutex> 里的六种互斥量、四种锁、std::lock/try_lock 与 call_once 如何分工；为什么只有 std::mutex 的构造函数是 constexpr；各类型在 libc++/macOS 上的大小与底层实现
status: done
covers: thread.mutex.general, mutex.syn, shared.mutex.syn
related: thread.mutex.requirements, thread.lock, thread.once, thread.req, thread.condition, intro.multithread
tags: 标准库, 并发, 互斥量, 导读
updated: 2026-10-18
---

[thread.mutex.general] ¶1：本子条款提供互斥机制——**互斥量**、**锁**和**一次调用**（call once）。这些机制让编写无竞争的程序更容易（[[intro.multithread]]）。

"更容易"这个措辞很准确：互斥量本身不阻止数据竞争，它只提供一种建立 happens before 的手段——`unlock()` 与随后的 `lock()` 同步。程序员仍须保证每次访问共享数据时都持有同一把锁。

## 组件一览

| 子条款 | 内容 | 本站笔记 |
|---|---|---|
| [mutex.syn]、[shared.mutex.syn] | 两个头文件的概要 | 本页 |
| [thread.mutex.requirements] | 互斥量类型的要求与六个类：`mutex`、`recursive_mutex`、`timed_mutex`、`recursive_timed_mutex`、`shared_mutex`、`shared_timed_mutex` | [[thread.mutex.requirements]] |
| [thread.lock] | RAII 锁：`lock_guard`、`scoped_lock`、`unique_lock`、`shared_lock`，以及标签 `defer_lock`、`try_to_lock`、`adopt_lock` | [[thread.lock]] |
| [thread.lock.algorithm] | `std::try_lock`、`std::lock`（免死锁地锁多个对象） | [[thread.lock]] |
| [thread.once] | `once_flag`、`call_once` | [[thread.once]] |

## &lt;mutex&gt; 概要（[mutex.syn]）

`<mutex>` 声明：

- 四个互斥量类：`mutex`、`recursive_mutex`、`timed_mutex`、`recursive_timed_mutex`；
- 三个标签类型及其常量：`defer_lock_t`/`defer_lock`、`try_to_lock_t`/`try_to_lock`、`adopt_lock_t`/`adopt_lock`。它们的默认构造函数都是 `explicit` 的，这样 `{}` 不会被意外地隐式转换成某个标签（防止 `unique_lock lk(m, {})` 这种含糊写法）；
- 锁：`lock_guard`、`scoped_lock`、`unique_lock` 及其 `swap`；
- 算法：`try_lock(L1&, L2&, L3&...)`、`lock(L1&, L2&, L3&...)`——至少两个实参；
- `once_flag`、`call_once`。

## &lt;shared_mutex&gt; 概要（[shared.mutex.syn]）

`<shared_mutex>` 声明 `shared_mutex`（C++17）、`shared_timed_mutex`（C++14）、`shared_lock` 及其 `swap`。

`shared_timed_mutex` 比 `shared_mutex` **早**进入标准：C++14 只来得及标准化带超时的版本，C++17 才补上更简单、可能更快的无超时版本。

## 六种互斥量怎么选

| 类型 | 递归 | 超时 | 共享 | 典型用途 |
|---|---|---|---|---|
| `mutex` | 否 | 否 | 否 | 默认选择 |
| `recursive_mutex` | 是 | 否 | 否 | 加锁的函数会递归调用自己或其他加锁函数（通常说明设计可以改进） |
| `timed_mutex` | 否 | 是 | 否 | 需要"最多等 X 毫秒" |
| `recursive_timed_mutex` | 是 | 是 | 否 | 以上两者 |
| `shared_mutex` | 否 | 否 | 是 | 读多写少 |
| `shared_timed_mutex` | 否 | 是 | 是 | 读多写少且需要超时 |

只有 `std::mutex` 的默认构造函数是 `constexpr` 的（[[thread.mutex.requirements]] 中 `mutex` 的类定义）。这意味着命名空间作用域的 `std::mutex` 总是**常量初始化**的（[[basic.start.static]]），在任何动态初始化之前就可用——不存在"另一个 TU 的静态初始化函数在 `mutex` 构造之前就去锁它"的问题。其他五种互斥量没有这个保证。

## 实现视角

!!! impl "libc++/macOS 上的大小与实现（Clang 23，Apple Silicon）"
    | 类型 | `sizeof` | 底层 |
    |---|---|---|
    | `mutex` | 64 | `pthread_mutex_t`（默认属性，静态初始化器 `PTHREAD_MUTEX_INITIALIZER`） |
    | `recursive_mutex` | 64 | `pthread_mutex_t`，`PTHREAD_MUTEX_RECURSIVE` 属性 |
    | `timed_mutex` | 120 | 一个 `mutex` + 一个 `condition_variable` + 一个 `bool` 标志 |
    | `shared_mutex` | 168 | 一个 `mutex` + 两个 `condition_variable` + 一个状态字 |
    | `shared_timed_mutex` | 168 | 同上 |
    | `condition_variable` | 48 | `pthread_cond_t` |
    | `once_flag` | 8 | 一个状态字 |

    `timed_mutex` 和 `shared_mutex` 用条件变量"自己实现"，而不是包装 `pthread_rwlock_t` 等原生对象——macOS 的 pthreads 没有 `pthread_mutex_timedlock`。这也意味着它们的 `try_lock_for` 受 [[thread.req]] 中描述的条件变量计时方式影响。

## 小结

- 互斥量提供同步，不提供保护；保护来自"每次访问都持有同一把锁"的纪律。
- `<mutex>`：四种互斥量、三种锁、`std::lock`/`try_lock`、`call_once`；`<shared_mutex>`：两种共享互斥量与 `shared_lock`。
- 只有 `std::mutex` 保证常量初始化。
