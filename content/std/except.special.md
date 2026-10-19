---
title: 特殊函数
summary: 异常机制依赖的几个库设施（terminate、uncaught_exceptions、current_exception、nested_exception）；std::terminate 在哪些情形下被调用；调用之前栈是否回溯：找不到 handler 时由实现定义，穿过 noexcept 函数时可以部分回溯，其余情形不得回溯。
status: done
covers: except.special.general, except.terminate
related: except.throw, except.handle, except.spec, exception.terminate, uncaught.exceptions, propagation, except.nested, basic.start.dynamic, basic.start.term, basic.contract.eval, thread.thread.destr
tags: 异常, terminate
updated: 2026-10-19
---

!!! tldr
    - 异常机制本身出错时（例如找不到 handler、回溯中析构函数又抛出），程序调用 `std::terminate`，默认的处理函数调用 `std::abort`。
    - 找不到 handler 时，调用 `std::terminate` 之前是否回溯栈由实现定义；主流实现不回溯，析构函数不会运行。
    - 异常离开 `noexcept` 函数时，栈可以回溯、部分回溯或不回溯，这是 `noexcept` 能带来优化的原因。
    - 其余情形都不得回溯；回溯一旦开始，也不能因为预见到终止而提前结束。
    - `std::uncaught_exceptions`、`std::current_exception`、`std::nested_exception` 让程序查询和保存正在传播的异常。

## 异常机制用到的库设施（[except.special.general]）

[[except.special.general#1]] 列出了四个与异常机制配合的库设施：

| 设施 | 用途 | 定义处 |
|---|---|---|
| `std::terminate` | 异常机制本身出错时的出口 | [[exception.terminate]] |
| `std::uncaught_exceptions()` | 当前线程中已抛出、尚未被 handler 接住的异常个数 | [[uncaught.exceptions]] |
| `std::current_exception()` | 取得当前处理的异常（[[except.handle#10]]），返回 `exception_ptr` | [[propagation]] |
| `std::nested_exception` | 抛出新异常时保存当前处理的异常，形成异常链 | [[except.nested]] |

`std::uncaught_exceptions()` 的典型用法是让析构函数分辨自己是正常离开作用域，还是在栈回溯中被调用：

```cpp run title="uncaught.cpp" ok
#include <cstdio>
#include <exception>

struct Tx {
    int n = std::uncaught_exceptions();
    ~Tx() { std::puts(std::uncaught_exceptions() > n ? "rollback" : "commit"); }
};

int main() {
    { Tx t; }                                 // commit
    try { Tx t; throw 1; } catch (int) {}     // rollback
}
```

`std::nested_exception` 用于把底层异常翻译成高层异常，同时不丢失原因：

```cpp run title="nested.cpp" ok
#include <cstdio>
#include <exception>
#include <stdexcept>

void open_config() { throw std::runtime_error("file not found"); }

void load() {
    try { open_config(); }
    catch (...) {
        std::throw_with_nested(std::logic_error("cannot load config"));
    }
}

void print(const std::exception& e, int depth = 0) {
    std::printf("%*s%s\n", depth * 2, "", e.what());
    try { std::rethrow_if_nested(e); }
    catch (const std::exception& inner) { print(inner, depth + 1); }
}

int main() {
    try { load(); } catch (const std::exception& e) { print(e); }
}
```

输出是两行：`cannot load config`，以及缩进的 `file not found`。

## 何时调用 std::terminate（[except.terminate] ¶1）

```cpp run title="terminate-rethrow-nothing.cpp" ok
#include <cstdio>
#include <cstdlib>
#include <exception>

int main() {
    std::set_terminate([] { std::fputs("terminate: throw; with no exception\n", stderr); std::abort(); });
    throw;      // 没有正在处理的异常，调用 std::terminate
}
```

¶1 有些错误无法恢复，比如异常没有被处理，或者 `std::thread` 对象在其线程仍在运行时被销毁。这时程序调用 `std::terminate`。注 1 汇总了所有这样的情形，规范性的规则写在各自引用的条款里。

前 10 项属于语言和异常机制本身：

| 项 | 情形 | 出处 |
|---|---|---|
| 1.1 | 异常对象初始化完成之后、handler 激活之前，异常机制调用的函数以异常退出，例如回溯中的析构函数、handler 参数的拷贝构造函数 | [[except.throw]] |
| 1.2 | 找不到 handler | [[except.handle#8]] |
| 1.3 | handler 搜索离开了非抛出函数的函数体；{{c++26}} 包括为这个函数的契约断言调用的契约违反处理函数以异常退出 | [[except.handle#7]]、[[basic.contract.eval]] |
| 1.4 | 栈回溯中销毁对象时抛出异常 | [[except.throw]] |
| 1.5 | 静态或线程存储期的非块变量初始化时抛出 | [[basic.start.dynamic]] |
| 1.6 | 静态或线程存储期对象析构时抛出 | [[basic.start.term]] |
| 1.7 | 用 `std::atexit`、`std::at_quick_exit` 注册的函数抛出 | [[support.start.term]] |
| 1.8 | 没有正在处理的异常时执行 `throw;` | [[expr.throw]] |
| 1.9 | 对没有保存任何异常的 `std::nested_exception` 调用 `rethrow_nested` | [[except.nested]] |
| 1.10 | 线程的初始函数抛出 | [[thread.thread.constr]] |

其余各项是库组件选择用终止来处理无法报告的错误：

| 项 | 情形 | 出处 |
|---|---|---|
| 1.11 | 执行策略规定如此时，并行算法的元素访问函数抛出 | [[algorithms.parallel.exceptions]] |
| 1.12 | 对仍可 join 的 `std::thread` 调用析构函数或移动赋值 | [[thread.thread.destr]]、[[thread.thread.assign]] |
| 1.13 | 条件变量的 `wait`、`wait_until`、`wait_for` 无法满足后置条件 | [[thread.condition.condvar]] |
| 1.14 | 请求停止或构造 `stop_callback` 时，回调抛出 | [[stopsource.mem]] 等 |
| 1.15–1.19 | {{c++26}} `std::execution` 的几种错误状态，例如销毁仍在运行的 `run_loop`，销毁尚未 join 的 `counting_scope`，从不支持 `exception_ptr` 错误完成的 `std::execution::task` 协程中抛出 | [[exec.run.loop]]、[[exec.simple.counting.ctor]]、[[exec.task]] 等 |

```cpp run title="terminate-thread.cpp" ok
#include <cstdio>
#include <cstdlib>
#include <exception>
#include <thread>

int main() {
    std::set_terminate([] { std::fputs("terminate: joinable thread destroyed\n", stderr); std::abort(); });
    std::thread t([] {});
}   // 1.12：t 仍可 join，析构函数调用 std::terminate
```

`std::terminate()` 调用当前的 terminate 处理函数（[[g:terminate-handler]]），默认的处理函数调用 `std::abort()`（[[terminate.handler]]）。`std::set_terminate` 可以替换它，但新的处理函数必须结束程序，不能返回。它可以记录日志、打印调用栈，最后调用 `std::abort` 或 `std::_Exit`。因异常而终止时，处理函数里可以用 `std::current_exception()` 取得那个异常，例子见 [[except.handle]]。

## 调用之前栈是否回溯（¶2）

```cpp run title="noexcept-partial-unwind.cpp" impl
#include <cstdio>
#include <cstdlib>
#include <exception>

struct D {
    const char* n;
    ~D() { std::printf("~%s\n", n); std::fflush(stdout); }
};

void g() { D d{"g-local"}; throw 1; }
void f() noexcept { D d{"f-local"}; g(); }

int main() {
    std::set_terminate([] { std::puts("terminate"); std::fflush(stdout); std::_Exit(0); });
    D m{"main-local"};
    f();
}
```

本机（Clang 23，`-O0` 和 `-O2` 相同）的输出是 `~g-local` 和 `terminate`。`g` 的局部对象析构了，`f` 和 `main` 的没有。异常传播时，沿调用链逐层析构自动对象的过程叫**栈回溯**（[[g:stack-unwinding]]），这里只回溯了一部分。¶2 按情形规定了回溯的程度：

| 情形 | 调用 `std::terminate` 之前 |
|---|---|
| 找不到匹配的 handler（1.2） | {{impl}} 回溯或不回溯 |
| handler 搜索离开非抛出函数（1.3） | {{impl}} 回溯、部分回溯或完全不回溯 |
| 其他所有情形 | 不得回溯 |

!!! std
    In all other situations, the stack shall not be unwound before the function `std::terminate` is invoked.

¶2 最后一句还禁止一种优化：实现不能因为判断出回溯最终会导致 `std::terminate`，就提前结束回溯。一旦找到了 handler、开始回溯，就必须把沿途的析构都做完，即使实现能预见到其中某个析构函数会抛出。

### 为什么允许不回溯

找不到 handler 时不回溯，core dump 里的调用栈就停在抛出点，可以直接看到是谁抛出的。回溯之后栈已经清空，只剩下 `main`。

这也符合 Itanium ABI 的两阶段实现：先做一遍只读的搜索，不修改栈；找到 handler 之后才进入清理阶段，真正析构对象。搜索失败时自然停在原地（见 [[toolchain/exception-implementation]]）。

### 为什么 noexcept 允许部分回溯

在两阶段实现中，`noexcept` 函数在异常表里表现为一个捕获一切、调用 `std::terminate` 的 handler。搜索阶段找到了它，清理阶段就回溯到这个函数为止，上例中 `g` 的局部对象因此被析构。但 `noexcept` 函数自己的局部对象不必析构，编译器也就不必为它们生成清理代码。允许部分回溯，正好描述了这种最高效的实现。

## 常见误解

!!! pitfall "终止之前析构函数总会运行"
    无论是找不到 handler，还是穿过 `noexcept` 函数，标准都不保证析构函数运行。刷新日志缓冲区、删除临时文件、释放锁文件，不能依赖未捕获异常加 RAII。可移植的做法是在 `main` 和每个线程入口加 `catch (...)`。

!!! pitfall "terminate 处理函数可以返回"
    处理函数返回是 UB，它违反了 [[terminate.handler]] 规定的必需行为。处理函数最后必须调用 `std::abort`、`std::_Exit` 这类不返回的函数。

## 思考题

!!! question "思考题 1"
    为什么穿过 `noexcept` 函数时可以部分回溯，找不到 handler 时却只能完全回溯或完全不回溯？

<details markdown="1">
<summary>答案</summary>

找不到 handler 时，实现要么在搜索阶段就失败，于是不回溯；要么像单阶段实现那样一路回溯到栈底才发现没有 handler，于是完全回溯。回溯到一半停下来，没有对应的自然实现，也没有好处。

`noexcept` 的边界在调用栈的中间。两阶段实现把 `noexcept` 函数当作 handler，清理阶段只回溯到它为止，而它自己的帧不必清理。部分回溯正好允许这种实现，同时也允许其他实现完全回溯或完全不回溯。
</details>

!!! question "思考题 2"
    静态对象的构造函数抛出异常（1.5）时，标准允许回溯栈吗？

<details markdown="1">
<summary>答案</summary>

不允许。1.5 不属于 ¶2 列出的两种例外，属于其他所有情形，调用 `std::terminate` 之前栈不得回溯。这里的调用来自运行时的启动代码，栈本来就不深，但初始化过程中各层函数的局部对象确实不会被析构。
</details>
