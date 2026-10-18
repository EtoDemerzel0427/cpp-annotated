---
title: 弃用的原子操作（D.24）
summary: Annex D.24：非免锁 atomic 上的 volatile 成员函数、atomic_init、ATOMIC_VAR_INIT、memory_order::consume 与 kill_dependency。讲清每项为什么被弃用——特别是 consume 为什么"名义上存在、实际上等同 acquire"——以及替代写法和 libc++ 实测。
status: draft
covers: *
related: depr, atomics, atomics.types.generic, atomics.order, intro.races
tags: 附录, 弃用, 原子操作, 内存模型
updated: 2026-10-18
---

这一页是 [[depr]] 的最后一部分，对应 Annex D.24。它收录了 `<atomic>` 中四类弃用设施。其中最值得 language lawyer 关注的是 `memory_order::consume`：它曾经是 C++11 内存模型里最精巧也最失败的部分，当前草案把它从正文中彻底移除，只在这里留下一句"与 `acquire` 含义相同"。

实测环境：Clang 23.1.3 + libc++。

## D.24.1 概述 {#depr.atomics.general}

**¶1**：`<atomic>` 额外提供：

```cpp
namespace std {
  template<class T>
    void atomic_init(volatile atomic<T>*, typename atomic<T>::value_type) noexcept;
  template<class T>
    void atomic_init(atomic<T>*, typename atomic<T>::value_type) noexcept;
  template<class T>
    constexpr T kill_dependency(T y) noexcept;                                  // freestanding
  inline constexpr memory_order memory_order_consume = memory_order::consume;   // freestanding

  #define ATOMIC_VAR_INIT(value) see below
}
```

## D.24.2 `volatile` 访问 {#depr.atomics.volatile}

**¶1**：如果某个 `atomic` 特化（[[atomics.types.generic]]）有下列重载之一，那么即使 `atomic<T>::is_always_lock_free` 为 `false`，该重载也参与重载决议：`volatile` 版本的 `store`、`operator=`、`load`、`operator T`、`exchange`、`compare_exchange_weak/strong`、`fetch_key`、复合赋值运算符、`++`/`--`、`wait`、`notify_one`、`notify_all`。

要理解这一条，得先看正文。正文 [[atomics.types.operations]] 给每个 `volatile` 重载都加了一条 *Constraints*："对于 volatile 重载，`is_always_lock_free` 为 `true`"。也就是说，按正文，**非免锁**的原子类型没有可用的 `volatile` 成员函数。Annex D 这一条又把约束放开了：这些重载仍然参与重载决议，只是这种用法已弃用。两处合起来的效果是：

| | `is_always_lock_free == true` | `is_always_lock_free == false` |
|---|---|---|
| `volatile atomic<T>` 的成员函数 | 正常使用 | 可用，但已弃用 |

**为什么弃用**：`volatile` 的语义是"每次访问都必须真实发生，不能合并或删除"，这对映射到硬件或与信号处理函数共享的内存有意义。非免锁的原子类型内部要靠锁实现（通常是一个全局的锁表），一个"带锁的 `volatile` 访问"在硬件层面并没有一致的含义：锁本身不是 `volatile` 的，信号处理函数里也不能安全地获取这个锁。

```cpp
#include <atomic>
struct Big { int a[16]; };
volatile std::atomic<Big> vb;   // Big 太大，不可能免锁
void f() {
  Big b = vb.load();            // 弃用（正文中这个重载本应因约束不满足而不可用）
}
```

**libc++ 实测**：上例在 `-std=c++20` 和 `-std=c++2c` 下都能编译，没有任何警告。libc++ 没有给 `volatile` 重载加约束，也没有加弃用标记。

**替代**：去掉 `volatile`。如果确实需要 `volatile` 语义，就保证类型是免锁的（用 `static_assert(std::atomic<T>::is_always_lock_free)` 检查）。

## D.24.3 非成员函数 `atomic_init` {#depr.atomics.nonmembers}

**¶1**：`atomic_init(object, desired)` 等价于 `atomic_store_explicit(object, desired, memory_order::relaxed)`。

**为什么弃用**：`atomic_init` 是 C11 `<stdatomic.h>` 兼容接口的遗留。在 C++20 之前，`std::atomic<T>` 的默认构造函数**不初始化**值（与 C 的 `_Atomic` 一致），所以需要 `atomic_init` 来初始化一个默认构造的原子对象，而且这个"初始化"不是原子操作，与其他线程的并发访问构成数据竞争。C++20 改为默认构造函数对值进行**值初始化**（`std::atomic<int> a;` 的值是 0），`atomic_init` 也就没有必要了。当前草案把它定义成一次 `relaxed` 存储，至少消除了数据竞争的隐患。

```cpp
#include <atomic>
std::atomic<int> ai;
void f() { std::atomic_init(&ai, 1); }   // 弃用
```

**libc++ 实测**：`-std=c++20` 起警告 `'atomic_init<int>' is deprecated [-Wdeprecated-declarations]`。

**替代**：构造时直接初始化 `std::atomic<int> ai{1};`；已经构造的对象，用 `ai.store(1, std::memory_order::relaxed)`。

## D.24.4 原子类型上的操作：`ATOMIC_VAR_INIT` {#depr.atomics.types.operations}

**¶1**：`ATOMIC_VAR_INIT(value)` 展开为一个适合对静态存储期原子变量进行**常量初始化**的记号序列，被初始化的原子变量的类型与 `value` 初始化兼容。（注：这个操作可能需要初始化锁。）对正在被初始化的变量的并发访问，即使是通过原子操作，也构成数据竞争。

```cpp
#include <atomic>
std::atomic<int> v = ATOMIC_VAR_INIT(5);   // 弃用
std::atomic<int> w{5};                     // 替代
```

**为什么弃用**：同样是 C11 兼容的遗留。C 的 `_Atomic` 类型没有构造函数，静态原子变量需要一个宏来给出初始值；C++ 的 `std::atomic<T>` 有 `constexpr` 构造函数，`std::atomic<int> v{5};` 本身就是常量初始化。C17 已经把这个宏标为过时（obsolescent）。

**libc++ 实测**：`-std=c++20` 起警告

```text
warning: macro 'ATOMIC_VAR_INIT' has been marked as deprecated [-Wdeprecated-pragma]
```

注意这里的标志不是 `-Wdeprecated-declarations`：宏不是声明，不能加 `[[deprecated]]`，libc++ 用的是 Clang 的 `#pragma clang deprecated(ATOMIC_VAR_INIT)`。

## D.24.5 `memory_order::consume` {#depr.atomics.order}

**¶1**：`memory_order` 枚举有一个额外的枚举项 `consume = 1`。`memory_order::consume` 在所有允许 `memory_order::acquire` 的地方都允许使用，并且**含义与之相同**。

**¶2**：`kill_dependency(y)` 返回 `y`。

### consume 原本是什么

C++11 的内存模型里，`consume` 是比 `acquire` 更弱的一种获取语义：它只对**数据依赖于**被读取值的后续操作建立 happens-before 关系，而不是对所有后续操作。典型场景是 RCU 风格的指针发布：

```cpp
#include <atomic>
struct Node { int payload; };
std::atomic<Node*> head;

int reader() {
  Node* p = head.load(std::memory_order_consume);
  return p->payload;   // p->payload 依赖于 p 的值：consume 保证读到发布者写入的 payload
}
```

在 ARM、POWER 这类弱内存序架构上，硬件天然保证"依赖于某个加载结果的后续访问"不会被重排到这个加载之前，所以 `consume` 不需要任何屏障，而 `acquire` 需要一条屏障指令。这就是 `consume` 存在的理由。`kill_dependency` 用来告诉编译器"依赖链到此为止"，让编译器可以对其后的代码自由优化。

### 为什么失败

为了让 `consume` 真的不加屏障，编译器必须在整个优化流程中**追踪依赖链**：任何可能打断依赖的变换（例如发现 `p` 只可能是某个已知值，于是把 `p->payload` 换成直接访问那个地址）都必须禁止。这些依赖链还会穿过函数调用，于是又引入了 `[[carries_dependency]]` 属性。实践中没有任何主流编译器做到了这一点：GCC、Clang、MSVC 一直都把 `consume` 直接**提升为 `acquire`**。也就是说，C++11 以来 `consume` 在所有实现中都只是 `acquire` 的一个别名。

当前草案承认了这个现实：从正文中删除 `consume` 的全部语义（"carries a dependency"、"dependency-ordered before" 等定义都不复存在，见 [[intro.races]]），只在 Annex D 保留这个枚举项以兼容旧代码，并规定它与 `acquire` 含义相同。`[[carries_dependency]]` 属性也已从标准中删除。

**libc++ 实测**：`std::memory_order_consume` 和 `std::kill_dependency(1)` 在 `-std=c++2c` 下都没有警告。

**替代**：`memory_order::acquire`。生成的代码与以前完全相同（因为编译器一直就是这么做的）。删掉所有 `kill_dependency` 调用，它现在只是恒等函数。

## 小结

| 条款 | 特性 | 弃用原因 | 替代 | libc++ 警告 |
|---|---|---|---|---|
| D.24.2 | 非免锁 `atomic` 的 `volatile` 成员 | 带锁实现与 `volatile` 语义不相容 | 去掉 `volatile` | 无 |
| D.24.3 | `atomic_init` | C++20 起默认构造即值初始化 | 构造时初始化 / `store(relaxed)` | 有（C++20 起） |
| D.24.4 | `ATOMIC_VAR_INIT` | `atomic` 有 `constexpr` 构造函数 | `std::atomic<T> v{x};` | 有（`-Wdeprecated-pragma`） |
| D.24.5 | `consume`、`kill_dependency` | 没有编译器能实现依赖追踪 | `acquire` | 无 |
