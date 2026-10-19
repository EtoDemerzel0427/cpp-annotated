---
title: 启动与终止
summary: <cstdlib> 中结束程序的函数 exit、quick_exit、_Exit、abort，以及注册回调的 atexit、at_quick_exit：各自销毁哪些对象、调用哪些回调、能否在信号处理函数中使用。
status: done
related: basic.start.term, basic.start.main, except.terminate, exception.terminate, support.signal, basic.stc.static, basic.stc.thread, cstdlib.syn
tags: 标准库, exit, atexit, quick_exit, abort, 程序终止
updated: 2026-10-19
---

!!! tldr
    - `std::exit` 会析构静态对象和当前线程的 `thread_local` 对象，调用 `atexit` 注册的函数，刷新 C 流，但不析构任何局部变量。
    - `std::quick_exit` 不析构任何对象，只按逆序调用 `at_quick_exit` 注册的函数，然后调用 `_Exit`。
    - `std::_Exit` 和 `std::abort` 什么都不清理，它们可以在信号处理函数中调用，`exit` 不行。
    - `atexit` 和 `at_quick_exit` 是两套独立的注册表。
    - 想在退出时析构沿途的局部变量，可以抛出一个在 `main` 中捕获的异常，再从 `main` 返回或调用 `exit`。

## `exit` 不析构局部变量

```cpp run title="exit-no-unwind.cpp" ok
#include <cstdio>
#include <cstdlib>

struct Noisy {
    const char* name;
    ~Noisy() { std::printf("~%s\n", name); }
};

Noisy global{"global"};                  // 静态存储期
thread_local Noisy tl{"thread_local"};   // 线程存储期

void handler() { std::puts("atexit handler"); }

int main() {
    std::atexit(handler);
    (void)tl;                            // 使用 tl，确保它已构造
    Noisy local{"local"};                // 自动存储期
    std::exit(0);                        // ~local 不会运行
}
// 输出：
// ~thread_local
// atexit handler
// ~global
```

`local` 的析构函数没有运行。如果一个 RAII 对象负责刷新文件、释放锁或删除临时文件，在它还活着的时候调用 `exit`，这些工作就都落空了。

[[basic.start.main]] 和 [[basic.start.term]] 规定了程序如何开始、静态对象按什么顺序析构；真正结束程序的那几个函数由库提供，就在本节。¶1 注 1 说明它们都声明在 `<cstdlib>` 中，[[cstdlib.syn]] 把它们都列为独立实现也必须提供的函数。

## 五种结束方式

| 方式 | 局部变量析构 | 静态、线程对象析构 | `atexit` 回调 | `at_quick_exit` 回调 | 刷新 C 流 | 信号安全 |
|---|---|---|---|---|---|---|
| 从 `main` 返回 | `main` 的局部变量 | 是 | 是 | 否 | 是 | 不适用 |
| `std::exit` | 否 | 是 | 是 | 否 | 是 | 否 |
| `std::quick_exit` | 否 | 否 | 否 | 是 | 由实现定义 | 回调都信号安全时是 |
| `std::_Exit` | 否 | 否 | 否 | 否 | 由实现定义 | 是 |
| `std::abort` | 否 | 否 | 否 | 否 | 由实现定义 | 是 |

**信号安全**（signal-safe）的函数可以在信号处理函数中调用，在信号处理函数中调用其他库函数是未定义行为（[[support.signal]]）。

从 `main` 返回等价于先离开 `main`、析构它的局部变量，再以返回值调用 `std::exit`（[[basic.start.main#5]]）。所以从 `main` 返回与在 `main` 中调用 `exit` 的主要区别，就是 `main` 自己的局部变量是否被析构。C++26 中，`return` 还会求值 `main` 的后置条件断言。

## `exit`：正常终止（¶9）

```cpp
[[noreturn]] void exit(int status);
```

`exit` 没有声明 `noexcept`，因为它要运行用户的析构函数和回调。它的效果分三步。

¶9.1 先析构当前线程的线程存储期对象，再析构静态存储期对象、调用 `atexit` 注册的函数，二者交错的顺序由 [[basic.start.term]] 规定。自动存储期对象不会因为调用 `exit` 而被析构。注册的函数以异常退出时，调用 `std::terminate`（[[except.terminate]]）。

!!! std
    Objects with automatic storage duration are not destroyed as a result of calling `exit()`.

¶9.2 接着刷新所有还有未写出数据的 C 流（`<cstdio>` 的 `FILE*`），关闭所有 C 流，删除所有由 `tmpfile()` 创建的文件。`std::cout` 默认与 `stdout` 同步，而且它本身在第一步就随静态对象的析构被刷新，所以经由 `exit` 结束时，`std::cout` 的输出不会丢。

¶9.3 最后把控制交还宿主环境。`status` 为 0 或 `EXIT_SUCCESS` 时，返回由实现定义形式的成功终止状态；为 `EXIT_FAILURE` 时返回不成功终止状态；其他值的含义由实现定义。

### 让局部变量也被析构

脚注 166 给出了一个办法：如果 `main` 本身不含自动存储期对象，那么在 `main` 中调用 `exit` 时，所有自动对象都已经析构了。要从深层调用回到这样的 `main`，可以抛出一个在 `main` 中捕获的异常，栈回溯会析构沿途所有局部变量。

```cpp run title="exit-via-exception.cpp" ok
#include <cstdio>
#include <cstdlib>

struct ExitRequest { int status; };
struct Guard { ~Guard() { std::puts("~Guard"); } };

void deep() {
    Guard g;
    throw ExitRequest{3};   // 代替 std::exit(3)：g 会被析构
}

int run() { deep(); return 0; }

int main() {
    try {
        return run();
    } catch (const ExitRequest& e) {
        std::exit(e.status);  // 此时 main 中没有活着的自动对象
    }
}
```

!!! ub "终止过程中再次调用 `exit`"
    C 标准规定，程序多次调用 `exit`，或者既调用 `exit` 又调用 `quick_exit`，行为未定义。典型的情形是在 `atexit` 回调或静态对象的析构函数中调用 `exit`。

!!! pitfall "多线程程序中调用 `exit`"
    `exit` 只析构当前线程的线程存储期对象，其他线程还在运行，可能正在使用即将被析构的静态对象。[[basic.start.term#7]] 的注 3 指出，对静态存储期对象的使用如果不先发生于它的析构，行为未定义。在多线程程序中，要么在 `exit` 之前 join 所有线程，要么改用 `quick_exit`。

## `atexit`：注册正常终止时的回调（¶6–¶8）

```cpp
int atexit(c-atexit-handler* f) noexcept;   // extern "C" 的 void()
int atexit(atexit-handler* f) noexcept;     // extern "C++" 的 void()
```

¶6 `atexit` 注册 `f`，在正常终止时无参调用它。两个重载分别接受 C 语言链接和 C++ 语言链接的函数（见 [[cstdlib.syn]]）。

- 如果一次 `atexit` 调用不先发生于（happens before，[[intro.races]]）`exit` 的调用，例如另一个线程已经开始执行 `exit`，那么这次注册能否成功是未指明的。
- 注 2 说明 `atexit` 不会引入数据竞争，可以从多个线程并发调用。
- ¶7 实现至少要支持注册 32 个函数。¶8 注册成功返回 0，失败返回非零。
- 脚注 165：注册几次就调用几次。

回调与静态对象析构的交错顺序由 [[basic.start.term#6]] 规定。可以把每次 `atexit` 注册看作构造了一个对象，然后与所有静态对象一起按相反的顺序拆除。上面的例子中，`handler` 在 `global` 构造完成之后才注册，所以先于 `~global` 调用。

## `quick_exit`：不析构对象的退出（¶10–¶14）

有时程序必须退出，但其他线程无法安全地停下来，比如它们阻塞在系统调用中。这时析构静态对象反而危险，因为那些线程可能还在用它们。C++11 引入的 `quick_exit` 不析构任何对象，只调用一组专门注册的回调，然后调用 `_Exit`。

```cpp
int at_quick_exit(c-atexit-handler* f) noexcept;
int at_quick_exit(atexit-handler* f) noexcept;
[[noreturn]] void quick_exit(int status) noexcept;
```

¶10 `at_quick_exit` 注册 `f`，在调用 `quick_exit` 时无参调用它。一次注册如果不先发生于所有的 `quick_exit` 调用，能否成功是未指明的。注 5 强调，`at_quick_exit` 的注册与 `atexit` 的注册是分开的，需要两边都执行的函数要分别注册。¶11–¶12 同样至少支持 32 个注册，成功返回 0。

¶13 `quick_exit` 按注册的相反顺序调用这些函数。例外是回调执行期间又注册了新函数的情况：新函数要在注册时已经调用过的那些函数之后调用。

- 不会因为调用 `quick_exit` 而析构任何对象。
- 注册的函数以异常退出时，调用 `std::terminate`。
- 注 6：回调由调用 `quick_exit` 的线程执行，不一定是注册它的线程，所以回调不能依赖线程存储期对象的身份。
- 调用完所有回调之后，`quick_exit` 调用 `_Exit(status)`。

¶14 当所有注册的函数都是信号安全的时，`quick_exit` 也是信号安全的。这让它可以在信号处理函数中使用，`exit` 做不到这一点。

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
    std::fflush(stdout);   // _Exit 不保证刷新 C 流
    std::quick_exit(3);    // 输出 main、quick 2、quick 1，退出码 3
}
```

!!! pitfall "别忘了刷新"
    `quick_exit` 最后调用 `_Exit`，而 `_Exit` 是否刷新流由实现定义，macOS 和 glibc 都不刷新。如果上例中没有 `fflush`，当 stdout 被重定向到文件、处于全缓冲模式时，`puts` 写入的内容会留在缓冲区里，随进程一起消失。

## `_Exit` 与 `abort`：立即结束（¶2–¶5）

```cpp
[[noreturn]] void _Exit(int status) noexcept;
[[noreturn]] void abort() noexcept;
```

¶2、¶4 两者的语义都与 C 标准库相同。¶3、¶5 补充了 C++ 的部分：程序终止时不运行自动、线程、静态存储期对象的析构函数，也不调用 `atexit` 注册的函数；两者都是信号安全的。

两者的区别来自 C：

- `_Exit(status)` 把 `status` 作为正常的退出状态交给宿主环境。是否刷新、关闭打开的流，是否删除临时文件，C 标准规定由实现定义。
- `abort()` 表示异常终止。它发出 `SIGABRT` 信号，返回给宿主的是由实现定义的不成功终止状态，在类 Unix 系统上通常会产生 core dump。如果程序捕获了 `SIGABRT`，并且信号处理函数不返回，`abort` 就不会结束程序。

## 与核心语言的衔接

- `std::terminate` 的默认处理函数调用 `abort`（[[terminate.handler]]）。所以未捕获的异常、从 `noexcept` 函数抛出异常等情形（[[except.terminate]]）在默认情况下最终都走到 `abort`，不析构任何对象。
- {{c++26}} 以 enforce 或 quick-enforce 语义检查的契约断言失败时，程序被契约终止（contract-terminated）。按 [[basic.contract.eval#9]]，这时调用 `std::terminate`、调用 `std::abort` 还是直接结束执行，由实现定义。

## 思考题

!!! question "思考题"
    1. 在一个 `atexit` 回调中调用 `std::atexit(g)` 注册新回调，`g` 会被调用吗？
    2. 能在信号处理函数中调用 `std::exit` 吗？如果不能，该用什么？
    3. 程序在 `main` 中执行 `return 0;`，之后某个静态对象的析构函数抛出了异常，会发生什么？

<details markdown="1">
<summary>答案</summary>

1. 未指明。这次注册发生在 `exit` 调用之后，不先发生于 `exit` 的调用，按 ¶6 它能否成功是未指明的，所以 `g` 是否被调用也未指明。作为对比，`quick_exit` 的 ¶13 明确规定了回调执行期间新注册的函数何时调用。
2. 不能。`exit` 不是信号安全的，它要运行任意的析构函数和回调，还要操作 C 流；按 [[support.signal]]，信号处理函数调用非信号安全的函数是未定义行为。可以改用 `_Exit` 或 `abort`（¶3、¶5），或者在所有 `at_quick_exit` 回调都信号安全的前提下使用 `quick_exit`（¶14）。
3. 调用 `std::terminate`。析构函数默认是 `noexcept` 的（[[except.spec]]），从中抛出异常就会调用 `std::terminate`。即使把析构函数声明为 `noexcept(false)`，[[basic.start.term#4]] 和 [[except.terminate]] 也规定，静态或线程存储期对象的析构以异常退出时调用 `std::terminate`。
</details>
