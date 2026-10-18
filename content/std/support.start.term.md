---
title: 启动与终止
summary: <cstdlib> 中结束程序的五个函数——exit、quick_exit、_Exit、abort 与 atexit/at_quick_exit 注册——各自销毁哪些对象、调用哪些回调、是否刷新流、是否信号安全
status: done
related: basic.start.term, basic.start.main, except.terminate, exception.terminate, support.signal, basic.stc.static, basic.stc.thread, cstdlib.syn
tags: 标准库, exit, atexit, quick_exit, abort, 程序终止
updated: 2026-10-18
---

核心语言在 [[basic.start.main]] 和 [[basic.start.term]] 里规定了程序如何开始、静态对象按什么顺序析构；但"按下结束按钮"的那几个函数是库提供的，就在本节。¶1 注 1：它们都声明在 `<cstdlib>` 中，并且全部是 freestanding 的（[[cstdlib.syn]]）。

C++ 有**五种**结束程序的方式，它们清理的范围由多到少：

| 方式 | 自动对象析构 | 线程/静态对象析构 | `atexit` 回调 | `at_quick_exit` 回调 | 刷新 C 流 | 信号安全 |
|---|---|---|---|---|---|---|
| 从 `main` 返回 | 是（`main` 的局部） | 是 | 是 | 否 | 是 | — |
| `std::exit` | **否** | 是 | 是 | 否 | 是 | 否 |
| `std::quick_exit` | 否 | 否 | 否 | 是 | 由实现定义（经 `_Exit`） | 回调都安全时是 |
| `std::_Exit` | 否 | 否 | 否 | 否 | 由实现定义 | 是 |
| `std::abort` | 否 | 否 | 否 | 否 | 由实现定义 | 是 |

另外，`std::terminate`（[[exception.terminate]]）默认调用 `std::abort`。

## `_Exit` 与 `abort`：立刻结束（¶2–¶5）

```cpp
[[noreturn]] void _Exit(int status) noexcept;
[[noreturn]] void abort() noexcept;
```

两者的 *Effects* 都是"具有 C 标准库规定的语义"；*Remarks* 补充了 C++ 的部分：程序终止时**不执行**自动、线程、静态存储期对象的析构函数，也**不调用** `atexit()` 注册的函数（[[basic.start.term]]）；两者都是**信号安全**的（[[support.signal]]），可以在信号处理函数中调用。

二者的区别来自 C：

- `_Exit(status)` 把 `status` 作为**正常**的退出状态返回给宿主环境。是否刷新/关闭打开的流、是否删除临时文件，C 标准规定为由实现定义。
- `abort()` 表示**异常终止**：它发出 `SIGABRT` 信号（若该信号被捕获且处理函数不返回，则 `abort` 不会结束程序），返回给宿主的是由实现定义的"不成功终止"状态；在类 Unix 系统上通常会产生 core dump。

## `atexit`：注册正常终止回调（¶6–¶8）

```cpp
int atexit(c-atexit-handler* f) noexcept;    // extern "C" void()
int atexit(atexit-handler* f) noexcept;      // extern "C++" void()
```

¶6：注册 `f`，在**正常程序终止**时无参调用。两个重载的存在是因为语言链接是函数类型的一部分（见 [[cstdlib.syn]] 的说明）。

- 如果一次 `atexit()` 调用**不 happens before** `exit()` 的调用，它是否成功是**未指明的**。换言之，在另一个线程已经开始 `exit` 时再注册，结果无法预期。
- 注 2：`atexit()` 不会引入数据竞争（[[res.on.data.races]]）——它内部有同步，可以从多个线程并发调用。
- ¶7 *Implementation limits*：实现至少要支持注册 **32** 个函数。
- ¶8 *Returns*：注册成功返回 0，失败返回非零。

回调与静态对象析构的**交错顺序**由 [[basic.start.term#6]] 规定：把每次 `atexit` 注册视为"构造了一个对象"，然后与所有静态对象一起按逆序拆除。脚注 165：注册几次就调用几次，同一函数注册两次会被调用两次。

## `exit`：正常终止（¶9）

```cpp
[[noreturn]] void exit(int status);
```

注意 `exit` **没有** `noexcept`——它会运行用户的析构函数和回调。它的效果分三步：

¶9.1 **销毁对象、调用回调**：先销毁**当前线程**的线程存储期对象；再销毁静态存储期对象并调用 `atexit` 注册的函数，二者的相对顺序见 [[basic.start.term]]。**自动存储期对象不会因调用 `exit()` 而被销毁**。如果某个注册的函数以异常退出，调用 `std::terminate`（[[except.terminate]]）。

¶9.2 **刷新并关闭 C 流**：刷新所有有未写出缓冲数据的打开的 C 流（`<cstdio>` 的 `FILE*`），关闭所有 C 流，删除所有 `tmpfile()` 创建的文件。C++ 的 `std::cout` 与 C 的 `stdout` 默认同步（`sync_with_stdio(true)`），所以经由 `exit` 结束时 `std::cout` 的输出也不会丢；而 `std::cout` 本身是由 `ios_base::Init` 管理的静态对象，在 ¶9.1 中被刷新。

¶9.3 **返回宿主环境**：`status` 为 0 或 `EXIT_SUCCESS` 时返回由实现定义形式的"成功终止"；为 `EXIT_FAILURE` 时返回"不成功终止"；其他值的含义由实现定义。

!!! std
    Objects with automatic storage duration are not destroyed as a result of calling `exit()`.

    自动存储期对象不会因调用 `exit()` 而被销毁。

这是 `exit` 最大的陷阱：它从调用点**直接**离开，不进行栈回溯。所有活着的局部对象——`main` 里的、调用栈上每一层的——都**不会**被析构。如果你的 RAII 对象负责刷新文件、释放锁、删除临时文件，`exit` 会让这些工作全部落空。

```cpp run title="exit-no-unwind.cpp" ok
#include <cstdio>
#include <cstdlib>

struct Noisy {
    const char* name;
    ~Noisy() { std::printf("~%s\n", name); }
};

Noisy global{"global"};                    // 静态存储期
thread_local Noisy tl{"thread_local"};     // 线程存储期

void handler() { std::puts("atexit handler"); }

int main() {
    std::atexit(handler);
    (void)tl;                              // odr-use，确保 tl 已被构造
    Noisy local{"local"};                  // 自动存储期
    std::exit(0);                          // ~local 不会运行
}
// 输出：
// ~thread_local
// atexit handler       （在 global 构造之后注册，所以先于 ~global 调用）
// ~global
```

脚注 166 给出了一种"让局部对象也被析构"的惯用法：如果 `main` **本身不含**自动存储期对象，并且在 `main` 里调用 `exit()`，那么所有自动对象自然都已销毁。可以通过**抛出一个在 `main` 中捕获的异常**把控制直接传回这样的 `main`：异常传播过程中的栈回溯会析构沿途所有局部对象。

```cpp run title="exit-via-exception.cpp" ok
#include <cstdio>
#include <cstdlib>

struct ExitRequest { int status; };
struct Guard { ~Guard() { std::puts("~Guard: 清理完成"); } };

void deep() {
    Guard g;
    throw ExitRequest{3};          // 代替 std::exit(3)：沿途局部对象被正常析构
}

int run() { deep(); return 0; }

int main() {
    try {
        return run();
    } catch (const ExitRequest& e) {
        std::exit(e.status);       // 此时 main 中已没有活着的自动对象
    }
}
```

!!! ub "在终止过程中再次调用 `exit`"
    C 标准规定：程序多次调用 `exit`，或者在调用 `exit` 之外又调用 `quick_exit`，行为未定义。典型场景是在 `atexit` 回调或静态对象的析构函数里调用 `exit`。C++ 的 `exit` 有自己的 *Effects*，但并没有为这种情形赋予语义，实践中同样不可依赖。

!!! pitfall "多线程程序中调用 `exit`"
    ¶9.1 只销毁**当前线程**的线程存储期对象。其他线程仍在运行，它们可能正在使用即将被析构的静态对象——按 [[basic.start.term#7]]，这是未定义行为。在多线程程序里，要么在 `exit` 之前 join 所有线程，要么改用 `quick_exit`。

## `at_quick_exit` 与 `quick_exit`：快速但可控的退出（¶10–¶14）

C++11 引入 `quick_exit`，解决的就是上面那个多线程问题：有时程序需要退出，但其他线程无法被安全地停止（例如阻塞在系统调用中），此时**析构静态对象反而危险**。`quick_exit` 不析构任何对象，只调用一组专门注册的回调，再调用 `_Exit`。

```cpp
int at_quick_exit(c-atexit-handler* f) noexcept;
int at_quick_exit(atexit-handler* f) noexcept;
[[noreturn]] void quick_exit(int status) noexcept;
```

`at_quick_exit`（¶10–¶12）：

- 注册 `f`，在调用 `quick_exit` 时无参调用。若一次 `at_quick_exit()` 调用不 happens before **所有** `quick_exit` 的调用，它是否成功是未指明的。
- 注 3：不引入数据竞争。注 4：如果从多个线程调用 `at_quick_exit`，注册顺序可能不确定。
- 注 5：**`at_quick_exit` 的注册与 `atexit` 的注册是分开的**，需要两边都执行的函数必须分别注册。
- 至少支持 32 个注册；成功返回 0。

`quick_exit`（¶13–¶14）：

- 按注册的**逆序**调用 `at_quick_exit` 注册的函数；例外是：若函数 F 注册时，某些先前注册的函数已经被调用了（即在回调执行期间注册了新回调），F 要在这些已调用的函数**之后**调用。
- **不得**因调用 `quick_exit` 而销毁任何对象。
- 若注册的函数以异常退出，调用 `std::terminate`。（`quick_exit` 本身是 `noexcept`。）
- 注 6：回调由**调用 `quick_exit` 的线程**执行，它可能不是注册回调的那个线程，所以回调不能依赖线程存储期对象的身份。
- 调用完回调之后，`quick_exit` **必须**调用 `_Exit(status)`。
- ¶14：当所有注册的函数都是信号安全的时，`quick_exit` 也是信号安全的。这让它可以在信号处理函数里使用——这是 `exit` 做不到的。

```cpp run title="quick-exit.cpp" ok
#include <cstdio>
#include <cstdlib>

struct Noisy { ~Noisy() { std::puts("~Noisy（不会打印）"); } };
Noisy global;

void q1() { std::puts("quick 1"); std::fflush(stdout); }
void q2() { std::puts("quick 2"); std::fflush(stdout); }
void a1() { std::puts("atexit（不会打印）"); }

int main() {
    std::atexit(a1);
    std::at_quick_exit(q1);
    std::at_quick_exit(q2);
    std::puts("main");
    std::fflush(stdout);   // quick_exit 最终调用 _Exit，不保证刷新 C 流
    std::quick_exit(3);    // 输出 main、quick 2、quick 1，退出码 3
}
```

!!! pitfall "别忘了刷新"
    `quick_exit` 以 `_Exit` 收尾，而 `_Exit` 是否刷新流是由实现定义的——在 macOS 和 glibc 上都**不刷新**。如果上例的回调里没有 `fflush`，`puts` 写入的内容会停留在 `stdout` 的缓冲区中，随进程一起消失。

## 与核心语言的衔接

- **从 `main` 返回**等价于以返回值调用 `std::exit`（[[basic.start.main#5]]），但在此之前 `main` 的局部对象已经随作用域结束被析构。这就是"从 `main` 返回"和"在 `main` 里调用 `exit`"的唯一区别。
- **`std::terminate`** 的默认处理函数调用 `abort`（[[terminate.handler]]）。所以未捕获的异常、`noexcept` 函数抛出异常等情形（[[except.terminate]]）最终都走到 `abort`——不析构任何对象。
- **契约违反**：契约断言以 *enforce* 或 *quick-enforce* 语义检查失败时程序被"契约终止"（[[basic.contract.eval#9]]），其方式由实现定义：调用 `std::terminate`、调用 `std::abort`，或直接终止执行。

## 思考题

!!! question "思考题"
    1. 在一个 `atexit` 回调中调用 `std::atexit(g)` 注册新回调，`g` 会被调用吗？
    2. 能在信号处理函数里调用 `std::exit` 吗？如果不能，该用什么？
    3. 程序在 `main` 中执行 `return 0;`，但某个静态对象的析构函数抛出了异常，会发生什么？

<details markdown="1">
<summary>展开查看答案与解析</summary>

1. ¶6 只说"不 happens before `exit()` 调用的 `atexit()` 调用是否成功是未指明的"。回调中的注册显然发生在 `exit()` 调用之后，因此能否成功、`g` 是否被调用，都是未指明的。对比 `quick_exit` 的 ¶13：它明确规定了回调执行期间新注册的函数的调用顺序。
2. 不能。`exit` 不是信号安全的（它要运行任意的析构函数、回调并操作 C 流的锁），而 [[support.signal]] 规定信号处理函数调用非信号安全的函数是未定义行为。可以调用 `_Exit` 或 `abort`（¶3、¶5：信号安全）；或者调用 `quick_exit`，前提是所有通过 `at_quick_exit` 注册的函数都是信号安全的（¶14）。
3. 静态对象的析构函数默认是 `noexcept` 的（[[except.spec]]），从中抛出异常会调用 `std::terminate`（[[except.terminate]]）。即使把析构函数声明为 `noexcept(false)`，[[except.terminate]] 也规定：静态存储期对象的析构以异常退出时调用 `std::terminate`。
</details>

## 小结

!!! summary
    - `exit`：销毁本线程的线程存储期对象、静态对象，调用 `atexit` 回调，刷新 C 流；**不销毁自动对象**；回调抛异常则 `terminate`。
    - `quick_exit`：只按逆序调用 `at_quick_exit` 回调，然后 `_Exit`；不销毁任何对象；回调全安全时信号安全。
    - `_Exit`、`abort`：什么都不清理，信号安全；`abort` 表示异常终止。
    - `atexit` 与 `at_quick_exit` 是两套独立的注册表，各自至少支持 32 个函数。
    - 想要"退出并析构局部对象"，就抛一个在 `main` 中捕获的异常。
