---
title: call_once
summary: once_flag 与 call_once 的精确语义——被动/主动/异常/返回四种执行、"至多一次返回执行"的不变式、主动执行的全序与同步规则如何保证所有调用者都能看到初始化结果；与函数局部静态变量的线程安全初始化对比；libc++ 的快速路径
status: done
covers: *
related: thread.mutex, stmt.dcl, basic.start.dynamic, func.require, intro.races
tags: 标准库, 并发, 初始化, call_once
updated: 2026-10-18
---

"只初始化一次"是并发程序中最常见的需求之一：惰性创建单例、首次使用时加载配置、初始化某个库。朴素的"检查-加锁-再检查"（double-checked locking）在 C++11 之前几乎不可能写对。[thread.once] 提供了标准答案：`std::once_flag` 加 `std::call_once`。本页覆盖其两个子条款。

## once_flag（[thread.once.onceflag]）

```cpp
struct once_flag {
  constexpr once_flag() noexcept;
  once_flag(const once_flag&) = delete;
  once_flag& operator=(const once_flag&) = delete;
};
```

- ¶1 `once_flag` 是一个**不透明**的数据结构，`call_once` 用它来初始化数据，而不引起数据竞争或死锁。
- ¶2 *Synchronization*：`once_flag` 对象的**构造不同步**。
- ¶3 *Postconditions*：对象的内部状态被设置为"尚未调用任何函数"。

构造函数是 `constexpr` 的，所以命名空间作用域的 `once_flag` 是常量初始化的，在任何代码运行前就绪——这对它的用途至关重要：用来保护别的初始化的东西，自己不能有初始化顺序问题。¶2 说构造不同步：如果 `once_flag` 是动态创建的（比如某个对象的成员），它自身必须先被安全地发布给其他线程。

## call_once（[thread.once.callonce]）

```cpp
template<class Callable, class... Args>
  void call_once(once_flag& flag, Callable&& func, Args&&... args);
```

¶1 *Mandates*：`is_invocable_v<Callable, Args...>` 为 `true`。

### 四种执行（¶2）

¶2 定义了四个术语：

- 不调用 `func` 的 `call_once` 执行是**被动**（passive）执行；
- 调用 `func` 的执行是**主动**（active）执行，它求值 *INVOKE*`(std::forward<Callable>(func), std::forward<Args>(args)...)`（[[func.require]]）；
- 主动执行中，若对 `func` 的调用抛出异常，该执行是**异常的**（exceptional），否则是**返回的**（returning）。异常的执行把异常传播给 `call_once` 的调用者。

然后是三条不变式。**对给定 `once_flag` 的所有 `call_once` 执行**：

1. 至多一个是返回执行；
2. 若存在返回执行，它是**最后一个**主动执行；
3. 只有存在返回执行时才可能有被动执行。

注 1：被动执行让其他线程能可靠地观察到较早的返回执行产生的结果。

换句话说："一次"指的是"**成功**一次"。`func` 抛出异常不算数，下一个调用者会再试一次；一旦有一次正常返回，之后所有调用都是被动的。在第一次成功之前，不会有任何调用"跳过"——第 3 条保证了没有调用会在初始化完成前就返回。

```cpp run title="call-once-retry.cpp" ok
#include <cstdio>
#include <mutex>
#include <stdexcept>

std::once_flag flag;
int attempts = 0;

void init() {
  ++attempts;
  std::printf("active execution #%d\n", attempts);
  if (attempts < 3) throw std::runtime_error("init failed");   // 异常执行：不算"完成"
}

int main() {
  for (int i = 0; i < 5; ++i) {
    try {
      std::call_once(flag, init);
      std::puts("call_once returned normally");
    } catch (const std::exception& e) {
      std::printf("caught: %s\n", e.what());
    }
  }
}
```

输出：前两次是"主动执行 + 捕获异常"，第三次是返回执行，最后两次是被动执行（直接返回，不打印 `active execution`）。

### 同步（¶3）

!!! std
    For any given `once_flag`: all active executions occur in a total order; completion of an active execution synchronizes with the start of the next one in this total order; and the returning execution synchronizes with the return from all passive executions.

    对任一给定的 `once_flag`：所有主动执行处于一个全序中；一次主动执行的完成与全序中下一次主动执行的开始同步；返回执行与所有被动执行的返回同步。

三句话各有作用：

1. **全序**：主动执行不会并发——同一时刻至多一个线程在执行 `func`。这就是"不引起数据竞争"的来源：`func` 里可以随意写普通变量。
2. **主动 → 下一个主动**：一次失败的尝试留下的副作用（比如部分初始化的状态）对下一次尝试可见，后者可以据此清理或继续。
3. **返回 → 所有被动**：初始化的结果对所有之后的调用者可见。被动执行的线程从 `call_once` 返回后，可以不加任何同步地读取 `func` 写入的数据。

```cpp run title="call-once-init.cpp" ok
#include <cassert>
#include <mutex>
#include <thread>
#include <vector>

struct Config { int port = 0; };
Config* cfg = nullptr;
std::once_flag cfg_once;

const Config& get_config() {
  std::call_once(cfg_once, [] { cfg = new Config{8080}; });   // 只有一个线程会执行
  return *cfg;                                                  // OK：返回执行 sync-with 被动执行的返回
}

int main() {
  std::vector<std::jthread> ts;
  for (int i = 0; i < 8; ++i) ts.emplace_back([] { assert(get_config().port == 8080); });
}
```

¶4 *Throws*：需要时抛 `system_error`（[[thread.req]]），或 `func` 抛出的任何异常。

¶5 例 1（标准自带）展示了三种用法：全局 `once_flag` 配普通函数；函数局部静态 `once_flag` 配函数对象；类成员 `once_flag` 配成员函数指针（`std::call_once(verified, &information::verifier, *this)`）——最后一种利用 *INVOKE* 的规则，把 `*this` 作为对象实参。由于 `call_once` 按转发引用接收实参、不复制，这里传 `*this` 不会复制对象。

## 与函数局部静态变量的比较

C++11 起，函数局部静态变量的初始化本身就是线程安全的（[[stmt.dcl]]）：多个线程同时首次经过声明时，只有一个执行初始化，其他线程**等待**它完成；初始化抛出异常时，下一次经过会重试。这与 `call_once` 的语义几乎一样，所以上面的 `get_config` 通常写成：

```cpp
const Config& get_config() {
  static const Config cfg{8080};   // "magic static"
  return cfg;
}
```

何时仍需要 `call_once`：

- 要初始化的不是一个变量，而是一段动作（注册回调、初始化第三方库）；
- `once_flag` 需要是**对象的成员**（每个对象各自惰性初始化一次），而函数局部静态是全局唯一的；
- 需要在初始化中使用调用时才知道的参数。

## 实现视角

!!! impl "libc++ 的 call_once"
    `once_flag` 只有一个 8 字节的状态字：`0` 未调用、`1` 进行中、全 1 表示完成。`call_once` 的头文件内联部分只做一次 **acquire load**：若状态已是"完成"，直接返回——这就是被动执行的全部开销，对应 ¶3 的"返回执行 sync-with 被动执行的返回"（完成时的 release store 与这次 acquire load 配对）。否则调用动态库中的 `__call_once`，它用一把全局互斥量和一个全局条件变量协调所有 `once_flag` 的慢路径：抢到"进行中"的线程执行 `func`，其他线程在条件变量上等待；`func` 抛异常时把状态重置为 0 并唤醒等待者，让下一个线程重试。

## 陷阱

!!! pitfall "在 func 里对同一个 once_flag 再调用 call_once"
    递归调用时，内层调用看到状态为"进行中"，会等待外层执行完成，而外层正在等内层返回——死锁。标准没有为这种情况规定行为。

!!! pitfall "以为异常也算“调用过了”"
    `func` 抛异常后，`once_flag` 回到"未完成"状态，下一次 `call_once` 会再次调用 `func`（可能是**另一个** `func`——`call_once` 不关心你传的是哪个可调用对象，只看 flag）。

## 思考题

!!! question "1. 两个线程分别对同一个 `once_flag` 调用 `call_once(flag, f)` 与 `call_once(flag, g)`，f 和 g 都正常返回。f 和 g 各执行几次？"

<details markdown="1">
<summary>答案</summary>

恰好一个被执行一次。¶2：至多一个返回执行，且有返回执行时其后只能有被动执行。先成为主动执行的那个（f 或 g，未指定哪一个）正常返回后，另一个调用是被动执行，不调用它的可调用对象。
</details>

## 小结

- "一次"指成功一次：异常的主动执行不算，下一个调用者重试。
- 主动执行之间全序且依次同步；返回执行与所有被动执行的返回同步，所以初始化结果对所有调用者可见。
- `once_flag` 的构造是 `constexpr` 但不同步。
- 只需初始化一个变量时，函数局部静态变量更简单。
