---
title: call_once
summary: once_flag 与 call_once 怎样保证一段初始化只成功执行一次：抛异常的尝试不算数、各次尝试之间的同步、所有调用者都能看到初始化结果，以及它与函数局部静态变量的取舍。
status: done
covers: *
related: thread.mutex, stmt.dcl, basic.start.dynamic, func.require, intro.races
tags: 标准库, 并发, 初始化, call_once
updated: 2026-10-19
---

!!! tldr
    - `std::call_once(flag, f)` 保证同一个 `once_flag` 上的 `f` 至多成功执行一次；多个线程同时调用时，其余线程等它完成。
    - 只有正常返回才算完成。`f` 抛出异常时异常传给调用者，下一次 `call_once` 会再试一次。
    - 同一 `once_flag` 上的各次执行排成一个全序，成功的那次与之后所有直接返回的调用同步，所以 `f` 写入的数据无需额外加锁就能读取。
    - `once_flag` 的构造函数是 `constexpr`，可以常量初始化；但构造本身不同步。
    - 只初始化一个变量时，函数局部静态变量更简单，它的初始化同样是线程安全的。

## 只初始化一次

```cpp run title="call-once-init.cpp" ok
#include <cassert>
#include <mutex>
#include <thread>
#include <vector>

struct Config { int port = 0; };
Config* cfg = nullptr;
std::once_flag cfg_once;

const Config& get_config() {
  std::call_once(cfg_once, [] { cfg = new Config{8080}; });   // 只有一个线程会执行 lambda
  return *cfg;                                                  // 无需加锁即可读取
}

int main() {
  std::vector<std::jthread> ts;
  for (int i = 0; i < 8; ++i) ts.emplace_back([] { assert(get_config().port == 8080); });
}
```

八个线程同时调用 `get_config`，lambda 只运行一次，其余线程等它运行完再返回，返回后都能看到 `cfg`。手写的检查、加锁、再检查（double-checked locking）要用原子变量和正确的内存序才能做到这一点，`call_once` 把它封装好了。

## once_flag [thread.once.onceflag]

¶1 `once_flag` 是一个不透明的数据结构，`call_once` 用它在不引起数据竞争或死锁的情况下初始化数据。它不可复制、不可移动。

¶3 默认构造函数把内部状态设为尚未调用任何函数。这个构造函数是 `constexpr` 的，所以命名空间作用域的 `once_flag` 是常量初始化的，在任何动态初始化运行之前就已就绪（[[basic.start.static]]）。用来保护别的初始化的东西，自己不能有初始化顺序问题。

¶2 `once_flag` 的构造不同步。如果 `once_flag` 是某个动态创建对象的成员，这个对象本身要先安全地交给其他线程，`call_once` 不负责这一步。

## call_once [thread.once.callonce]

```cpp
template<class Callable, class... Args>
  void call_once(once_flag& flag, Callable&& func, Args&&... args);
```

¶1 `func` 必须能以 `args...` 调用，否则程序非良构。

### 四种执行（¶2）

¶2 标准把每次 `call_once` 调用叫做一次执行，并分成几类：

- 不调用 `func` 的执行是**被动执行**（passive execution）；
- 调用 `func` 的执行是**主动执行**（active execution），它求值 *INVOKE*`(std::forward<Callable>(func), std::forward<Args>(args)...)`（[[func.require]]）；
- 主动执行中，`func` 抛出异常的叫**异常执行**（exceptional），异常传给 `call_once` 的调用者；否则叫**返回执行**（returning）。

对同一个 `once_flag` 上的全部执行，第 2 段规定了三条：

1. 至多一个是返回执行；
2. 如果有返回执行，它是最后一个主动执行；
3. 只有存在返回执行时，才可能有被动执行。

所以"一次"指的是成功一次。异常执行不算数，下一个调用者会再次调用 `func`。第 3 条保证不会有调用在初始化成功之前就被动地返回。

```cpp run title="call-once-retry.cpp" ok
#include <cstdio>
#include <mutex>
#include <stdexcept>

std::once_flag flag;
int attempts = 0;

void init() {
  ++attempts;
  std::printf("active execution #%d\n", attempts);
  if (attempts < 3) throw std::runtime_error("init failed");   // 异常执行
}

int main() {
  for (int i = 0; i < 5; ++i) {
    try {
      std::call_once(flag, init);
      std::puts("returned");
    } catch (const std::exception& e) {
      std::printf("caught: %s\n", e.what());
    }
  }
}
```

前两次是异常执行，第三次是返回执行，最后两次是被动执行，不再打印 `active execution`。

### 同步（¶3）

!!! std
    For any given `once_flag`: all active executions occur in a total order; completion of an active execution synchronizes with the start of the next one in this total order; and the returning execution synchronizes with the return from all passive executions.

¶3 这三句话分别保证了三件事：

1. 主动执行排成全序，不会并发。同一时刻至多一个线程在执行 `func`，所以 `func` 里可以直接写普通变量。
2. 一次主动执行的完成与下一次主动执行的开始[[g:synchronizes-with|同步]]。失败的尝试留下的副作用，下一次尝试都能看到，可以据此清理或继续。
3. 返回执行与所有被动执行的返回同步。被动执行的线程从 `call_once` 返回后，读取 `func` 写入的数据不构成数据竞争。上面 `get_config` 里的 `return *cfg;` 依靠的就是这一句。

¶4 `call_once` 在需要时抛 `system_error`（[[thread.req]]），也会传出 `func` 抛出的异常。

### 绑定成员函数（¶5）

¶5 标准的例子展示了三种 `once_flag`：全局的、函数局部静态的、类成员的。最后一种利用 *INVOKE* 调用成员函数：

```cpp run ok
#include <mutex>

class information {
  std::once_flag verified;
  void verifier() {}
public:
  void verify() { std::call_once(verified, &information::verifier, *this); }
};

int main() {
  information a, b;
  a.verify(); a.verify();   // a.verifier 只运行一次
  b.verify();               // b 有自己的 flag
}
```

`call_once` 按转发引用接收参数，`*this` 是左值，传进去的是引用，对象不会被复制。

## 与函数局部静态变量比较

C++11 起，函数局部静态变量的初始化本身是线程安全的（[[stmt.dcl]]）：多个线程同时首次经过声明时，只有一个执行初始化，其他线程等它完成；初始化抛出异常时，下一次经过会重试。这与 `call_once` 的语义一致，所以 `get_config` 通常写成：

```cpp
const Config& get_config() {
  static const Config cfg{8080};
  return cfg;
}
```

下面几种情况仍然需要 `call_once`：

- 要执行的是一段动作，而不是初始化一个变量，比如注册回调、初始化第三方库；
- 每个对象各自需要惰性初始化一次，`once_flag` 要做成成员，而函数局部静态变量全程序只有一份；
- 初始化需要调用时才知道的参数。

!!! impl "libc++ 的实现"
    libc++ 的 `once_flag` 只有一个整数状态：0 表示未调用，1 表示正在执行，全 1 表示已完成。`call_once` 在头文件里先做一次 acquire 读取，如果状态已是完成就直接返回，被动执行的开销只有这一次读取。

    否则进入库里的 `__call_once`：它用一把全局互斥量和一个全局条件变量协调所有 `once_flag` 的慢路径。把状态改成正在执行的线程调用 `func`，其他线程在条件变量上等待；`func` 抛出异常时状态被重置为 0，并唤醒等待者。完成时对状态的 release 写入与快速路径的 acquire 读取配对，实现了 ¶3 的最后一句。

## 常见误解

!!! pitfall "`func` 里可以对同一个 `once_flag` 再调用 `call_once`"
    内层调用会看到状态是正在执行，于是等待外层执行完成，而外层在等内层返回。标准没有为这种情况另作规定，实际实现中就是死锁。

!!! pitfall "抛出异常也算调用过了"
    `func` 抛出异常后，`once_flag` 仍然处于未完成状态，下一次 `call_once` 会再次调用。而且下一次调用的可能是另一个可调用对象：`call_once` 只看 flag，不关心传进来的是哪个函数。

## 思考题

!!! question "思考题"
    两个线程对同一个 `once_flag` 分别调用 `call_once(flag, f)` 和 `call_once(flag, g)`，f 和 g 都正常返回。f 和 g 各执行几次？

<details markdown="1">
<summary>答案</summary>

其中恰好一个执行一次，另一个不执行。按第 2 段，至多一个返回执行，而且有了返回执行之后只能有被动执行。先成为主动执行的那个调用正常返回后，另一个调用就是被动执行。哪一个先执行未指定。
</details>
