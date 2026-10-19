---
title: 弃用的原子操作（D.24）
summary: <atomic> 中被弃用的四类设施：非免锁原子类型的 volatile 成员函数、atomic_init、ATOMIC_VAR_INIT，以及已经等同于 acquire 的 memory_order::consume 和 kill_dependency。
status: done
covers: *
papers: P0883R2, P3475R2
related: depr, atomics, atomics.types.generic, atomics.types.operations, atomics.order, intro.races
tags: 附录, 弃用, 原子操作, 内存模型
updated: 2026-10-19
---

!!! tldr
    - `memory_order::consume` 仍然可以写，但含义与 `acquire` 完全相同。原来依赖链上的语义没有编译器实现过，已从正文删除。
    - `kill_dependency(y)` 现在只是返回 `y` 的恒等函数，可以直接删掉。
    - C++20 起 `std::atomic<T>` 的默认构造函数会值初始化，`atomic_init` 和 `ATOMIC_VAR_INIT` 这两个 C 兼容的初始化手段都不再需要。
    - 正文规定只有免锁的原子类型才有可用的 `volatile` 成员函数；对非免锁类型使用它们仍被允许，但已弃用。

**弃用**（deprecated）的特性仍然是规范性的，只是已被确定为将来可能删除的候选；实现可以给这些名字加上 `[[deprecated]]`（[[depr.general#2]]）。本页的实测环境是 Clang 23.1.3 和 libc++。

## D.24.1 概述 {#depr.atomics.general}

¶1 `<atomic>` 额外提供以下声明，其中 `kill_dependency` 和 `memory_order_consume` 在独立实现（freestanding）中也必须提供：

```cpp
namespace std {
  template<class T>
    void atomic_init(volatile atomic<T>*, typename atomic<T>::value_type) noexcept;
  template<class T>
    void atomic_init(atomic<T>*, typename atomic<T>::value_type) noexcept;
  template<class T>
    constexpr T kill_dependency(T y) noexcept;
  inline constexpr memory_order memory_order_consume = memory_order::consume;

  #define ATOMIC_VAR_INIT(value) see below
}
```

## D.24.5 `memory_order::consume` {#depr.atomics.order}

```cpp
#include <atomic>
struct Node { int payload; };
std::atomic<Node*> head;

int reader() {
  Node* p = head.load(std::memory_order_consume);  // 等同于 acquire
  return p->payload;
}
```

¶1 `memory_order` 枚举额外有枚举项 `consume = 1`。凡是允许 `memory_order::acquire` 的地方都允许 `memory_order::consume`，而且两者含义相同。

¶2 `kill_dependency(y)` 返回 `y`。

### consume 原本的设计

C++11 中，`consume` 是比 `acquire` 更弱的获取语义。`acquire` 保证发布方在 release 之前的所有写入，对获取方此后的所有操作可见。`consume` 只对数据上依赖于读到的那个值的后续操作提供这个保证。上例中 `p->payload` 依赖于 `p`，所以能读到发布方写入的 `payload`。

这样设计是为了 RCU 风格的指针发布。ARM、POWER 这类弱内存序架构上，硬件本来就保证依赖于某次加载结果的访问不会被重排到这次加载之前，所以 `consume` 不需要屏障指令，而 `acquire` 需要。`kill_dependency` 用来告诉编译器依赖链在这里结束，之后的代码可以自由优化。

### 为什么没有实现

要让 `consume` 真的不加屏障，编译器必须在整个优化流程中追踪依赖链，禁止任何可能打断依赖的变换。例如编译器发现 `p` 只可能是某个已知地址，就不能把 `p->payload` 换成直接访问那个地址。依赖链还会穿过函数调用，为此又引入了 `[[carries_dependency]]` 属性。

主流编译器都没有做这种追踪，GCC、Clang、MSVC 一直把 `consume` 当作 `acquire` 处理。当前草案承认了这一点：正文删除了 carries a dependency、dependency-ordered before 等概念（见 [[intro.races]]），`[[carries_dependency]]` 属性也被删除，只在这里保留枚举项以兼容旧代码（[[P3475R2]]）。

libc++ 对 `memory_order_consume` 和 `kill_dependency` 不给警告。改用 `memory_order::acquire` 即可，生成的代码与以前相同；`kill_dependency` 的调用可以直接删掉。

## D.24.3 非成员函数 `atomic_init` {#depr.atomics.nonmembers}

```cpp
#include <atomic>
std::atomic<int> ai;
void f() { std::atomic_init(&ai, 1); }  // 弃用
```

¶1 `atomic_init(object, desired)` 等价于 `atomic_store_explicit(object, desired, memory_order::relaxed)`。

`atomic_init` 来自 C11 `<stdatomic.h>` 的兼容接口。C++20 之前，`std::atomic<T>` 的默认构造函数和 C 的 `_Atomic` 一样不初始化值，需要 `atomic_init` 补上初始化。当时这一步不是原子操作，与其他线程的并发访问会构成数据竞争。C++20 让默认构造函数对值进行值初始化，`std::atomic<int> a;` 的值就是 0（[[P0883R2]]），`atomic_init` 也就没有必要了。当前草案把它定义成一次 `relaxed` 存储，消除了数据竞争的隐患。

libc++ 从 `-std=c++20` 起警告。替代写法是构造时直接初始化 `std::atomic<int> ai{1};`；对已经构造的对象，写 `ai.store(1, std::memory_order::relaxed)`。

## D.24.4 `ATOMIC_VAR_INIT` {#depr.atomics.types.operations}

<div class="compare" markdown="1">

```cpp
#include <atomic>
// 弃用
std::atomic<int> v = ATOMIC_VAR_INIT(5);
```

```cpp
#include <atomic>
// 替代
std::atomic<int> w{5};
```

</div>

¶1 `ATOMIC_VAR_INIT(value)` 展开成一个记号序列，可以用于对静态存储期原子变量进行常量初始化，变量的类型要能用 `value` 初始化。注 1 指出这个操作可能需要初始化锁。对正在被初始化的变量的并发访问构成数据竞争，即使是通过原子操作访问。

这个宏同样来自 C。C 的 `_Atomic` 类型没有构造函数，静态原子变量需要一个宏给出初始值；C17 已经把它标为过时。C++ 的 `std::atomic<T>` 有 `constexpr` 构造函数，`std::atomic<int> w{5};` 本身就是常量初始化。

libc++ 从 `-std=c++20` 起警告，诊断是 `macro 'ATOMIC_VAR_INIT' has been marked as deprecated [-Wdeprecated-pragma]`。宏不是声明，不能加 `[[deprecated]]`，libc++ 用的是 Clang 的 `#pragma clang deprecated(ATOMIC_VAR_INIT)`，所以警告选项不是 `-Wdeprecated-declarations`。

## D.24.2 `volatile` 访问 {#depr.atomics.volatile}

```cpp
#include <atomic>
struct Big { int a[16]; };
volatile std::atomic<Big> vb;  // Big 太大，不可能免锁
Big f() {
  return vb.load();  // 弃用
}
```

**免锁**（lock-free）的原子类型不借助锁实现，`atomic<T>::is_always_lock_free` 为 `true` 表示这个类型总是免锁的。正文 [[atomics.types.operations]] 给每个成员函数的 `volatile` 重载都加了约束：只有 `is_always_lock_free` 为 `true` 时，这个重载才可用。

¶1 本条放宽了这个约束。`atomic` 特化中的 `volatile` 版本的 `store`、`operator=`、`load`、`operator T`、`exchange`、`compare_exchange_weak`、`compare_exchange_strong`、`fetch_key`、复合赋值、`++`、`--`、`wait`、`notify_one`、`notify_all`，即使 `is_always_lock_free` 为 `false` 也参与重载决议。两条规定合起来的效果是：

| | `is_always_lock_free` 为 `true` | `is_always_lock_free` 为 `false` |
|---|---|---|
| `volatile atomic<T>` 的成员函数 | 正常使用 | 可用，但已弃用 |

`volatile` 的含义是每次访问都必须真实发生，不能合并或删除，这对映射到硬件的内存或与信号处理函数共享的内存有用。非免锁的原子类型内部靠锁实现，通常是一张全局锁表。锁本身不是 `volatile` 的，信号处理函数里也不能安全地获取它，所以带锁的 `volatile` 访问没有一致的含义。

libc++ 没有给 `volatile` 重载加约束，也没有加弃用标记，上例在 `-std=c++20` 和 `-std=c++2c` 下都没有警告。替代做法是去掉 `volatile`；确实需要 `volatile` 语义时，用 `static_assert(std::atomic<T>::is_always_lock_free)` 保证类型免锁。

## 小结

| 条款 | 特性 | 弃用原因 | 替代 | libc++ 警告 |
|---|---|---|---|---|
| D.24.5 | `consume`、`kill_dependency` | 没有编译器实现依赖追踪 | `acquire` | 无 |
| D.24.3 | `atomic_init` | C++20 起默认构造即值初始化 | 构造时初始化，或 `store(relaxed)` | C++20 起 |
| D.24.4 | `ATOMIC_VAR_INIT` | `atomic` 有 `constexpr` 构造函数 | `std::atomic<T> v{x};` | C++20 起（`-Wdeprecated-pragma`） |
| D.24.2 | 非免锁 `atomic` 的 `volatile` 成员 | 带锁实现与 `volatile` 语义不相容 | 去掉 `volatile` | 无 |
