---
title: 特殊函数
summary: 异常机制使用的几个库函数概览（terminate、uncaught_exceptions、current_exception、nested_exception）；std::terminate 被调用的全部场景；各场景下栈是否回溯：找不到 handler 时由实现定义、noexcept 边界处可部分回溯、其余情形不得回溯
status: done
covers: except.special.general, except.terminate
related: except.throw, except.handle, except.spec, exception.terminate, uncaught.exceptions, propagation, except.nested, basic.start.dynamic, basic.start.term, basic.contract.eval, thread.thread.destr
tags: 异常, terminate
updated: 2026-10-18
---

本节是第 14 章与库（[[support.exception]]）的接口：它说明异常机制依赖哪几个库函数，并集中列出 **`std::terminate` 会被调用的所有场景**，以及在这些场景下**栈是否回溯**——后者是本节唯一真正规范性的内容，也是实现"零开销异常"的关键自由度。

## 概述（[except.special.general]）

[[except.special.general#1]] 介绍四个库设施：

| 设施 | 用途 | 定义处 |
|---|---|---|
| `std::terminate` | 异常机制处理"与异常机制本身有关的错误"的出口 | [[exception.terminate]] |
| `std::uncaught_exceptions()` | 当前线程中**未捕获**的异常个数（定义见 [[except.throw#6]]） | [[uncaught.exceptions]] |
| `std::current_exception()` | 获取当前处理的异常（[[except.handle#10]]）的 `exception_ptr` | [[propagation]] |
| `std::nested_exception` | 在抛出新异常时捕获并保存当前处理的异常，形成异常链 | [[except.nested]] |

`std::nested_exception` 的典型用法是"异常翻译但不丢失原因"：

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

输出：

```text
cannot load config
  file not found
```

## `std::terminate` 的触发场景（[except.terminate] ¶1）

¶1 有些错误无法恢复，例如异常没有被处理、`std::thread` 对象在其线程仍在执行时被销毁。此时调用 `std::terminate`（[[exception.terminate]]）。注 1 列出了全部情形（注是非规范性的汇总，规范性规则在各自引用的条款中）：

| 项 | 场景 | 出处 |
|---|---|---|
| 1.1 | 异常机制在异常对象初始化完成**之后**、handler 激活**之前**调用的函数以异常退出（例如回溯中的析构函数、handler 参数的拷贝构造） | [[except.throw#9]] |
| 1.2 | 找不到 handler | [[except.handle#8]] |
| 1.3 | handler 搜索离开具有非抛出异常说明的函数的函数体——包括从函数契约断言的求值中调用的**契约违约处理函数**以异常退出 {{c++26}} | [[except.handle#7]]，[[basic.contract.eval]] |
| 1.4 | 栈回溯中销毁对象时以异常终止 | [[except.throw#9]] 注 7 |
| 1.5 | 静态/线程存储期**非块变量**的初始化以异常退出 | [[basic.start.dynamic]] |
| 1.6 | 静态/线程存储期对象的析构以异常退出 | [[basic.start.term]] |
| 1.7 | 用 `std::atexit` / `std::at_quick_exit` 注册的函数以异常退出 | [[support.start.term]] |
| 1.8 | 不带操作数的 `throw;` 在没有正在处理的异常时执行 | [[expr.throw#3]] |
| 1.9 | 对没有捕获任何异常的对象调用 `std::nested_exception::rethrow_nested` | [[except.nested]] |
| 1.10 | 线程的初始函数以异常退出 | [[thread.thread.constr]] |
| 1.11 | 执行策略规定如此时，并行算法的元素访问函数以异常退出 | [[algorithms.parallel.exceptions]] |
| 1.12 | 对仍可 join 的 `std::thread` 调用析构函数或移动赋值 | [[thread.thread.destr]]，[[thread.thread.assign]] |
| 1.13 | 条件变量的 `wait`/`wait_until`/`wait_for` 不能满足其后置条件 | [[thread.condition.condvar]] |
| 1.14 | 请求停止时（`stop_source`/`inplace_stop_source`），或构造 `stop_callback`/`inplace_stop_callback` 时，回调以异常退出 | [[stopsource.mem]] 等 |
| 1.15 | 销毁仍处于运行状态的 `run_loop` {{c++26}} | [[exec.run.loop]] |
| 1.16 | 对 `with_awaitable_senders<T>` 对象调用 `unhandled_stopped`，而其 continuation 的 promise 没有 `unhandled_stopped` 成员 {{c++26}} | [[exec.with.awaitable.senders]] |
| 1.17 | 销毁状态不是 joined/unused/unused-and-closed 的 `simple_counting_scope`/`counting_scope` {{c++26}} | [[exec.simple.counting.ctor]] |
| 1.18 | `get_parallel_scheduler` 的替换后端查询返回空指针 {{c++26}} | [[exec.par.scheduler]] |
| 1.19 | 从不支持 `set_error_t(exception_ptr)` 完成的 `std::execution::task` 协程中抛出异常 | [[exec.task]] |

前 10 项是语言层面的"异常机制自身出错"；后面的是库组件选择以 terminate 作为"无法报告的错误"的处理方式（1.15–1.19 来自 C++26 的 `std::execution`）。

几个代表性的例子：

```cpp run title="terminate-rethrow-nothing.cpp" ok
#include <cstdio>
#include <cstdlib>
#include <exception>

int main() {
    std::set_terminate([] { std::fputs("terminate: throw; with no exception\n", stderr); std::abort(); });
    throw;      // 1.8：没有正在处理的异常
}
```

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

### terminate 处理函数

`std::terminate()` 调用当前的 **terminate 处理函数**（[[terminate]]）；默认处理函数调用 `std::abort()`（[[terminate.handler]]）。用 `std::set_terminate` 可以替换它，但处理函数**必须**终止程序而不返回调用方——它可以记录日志、打印回溯，然后 `abort`/`_Exit`。

由于异常导致的 terminate 中有一个"隐式 handler"处于活动状态（[[except.handle#9]]），处理函数里可以用 `std::current_exception()` 取得导致终止的异常，见 [[except.handle]] 的例子。

## 栈是否回溯（¶2）

¶2 是本节的规范性核心，按场景给出了三种不同的规则：

!!! std
    In the situation where no matching handler is found, it is implementation-defined whether or not the stack is unwound before `std::terminate` is invoked.

    找不到匹配的 handler 时，在调用 `std::terminate` 之前是否回溯栈由实现定义。

| 场景 | 栈回溯 |
|---|---|
| 找不到匹配的 handler（1.2） | {{impl}}：回溯或不回溯 |
| handler 搜索离开非抛出函数（1.3） | {{impl}}：回溯、**部分回溯**或完全不回溯 |
| 所有其他情形 | **不得**回溯 |

最后一句额外禁止一种"聪明"的优化：实现**不得**因为判定回溯最终会导致 `std::terminate`，就**提前结束**栈回溯。也就是说，一旦开始回溯（例如已经找到了一个 handler），就必须老老实实把沿途的析构都做完——即使实现能预见到某个析构函数会抛出从而 terminate。

### 为什么允许不回溯？

- **调试**：找不到 handler 时不回溯，core dump 里的栈就是抛出点的栈，可以直接看到"是谁抛的"。回溯之后栈已经被清空，只剩 `main`。
- **两阶段实现**：Itanium ABI 先做一遍只读的"搜索"阶段（不修改栈），找到 handler 后才开始"清理"阶段。搜索失败时自然停在原地（见 [[toolchain/exception-implementation]]）。

### 为什么 noexcept 允许"部分回溯"？

这是为了让 `noexcept` 能带来真实的优化。在两阶段实现中，`noexcept` 函数在 LSDA 里表现为一个"捕获一切并调用 terminate"的 handler：搜索阶段**找到**了它，于是清理阶段会回溯到这个函数为止——这一段是"回溯"了的；但 `noexcept` 函数**自身**的局部对象不必析构，编译器也就不必为它们生成清理代码。本机验证：

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

本机输出（Clang 23，`-O0` 与 `-O2` 相同）：

```text
~g-local
terminate
```

`g` 的局部对象被析构（`g` 不是 `noexcept`，回溯经过它），`f` 与 `main` 的局部对象都没有被析构——这正是"部分回溯"。

## 陷阱

!!! pitfall "依赖 terminate 之前的析构"
    不论是找不到 handler 还是 noexcept 违约，标准都不保证析构函数运行。日志缓冲区、临时文件、锁文件的清理不能依赖 RAII + 未捕获异常。在 `main` 和线程入口加 `catch (...)` 是唯一可移植的办法。

!!! pitfall "terminate 处理函数返回"
    处理函数返回是 UB（违反 [[terminate.handler]] 的"必需行为"）。处理函数最后必须调用 `std::abort`、`std::_Exit` 之类不返回的函数。

## 思考题

!!! question "思考题 1"
    为什么"handler 搜索离开 noexcept 函数"可以部分回溯，而"找不到 handler"却只能"回溯或不回溯"二选一？

<details markdown="1">
<summary>答案</summary>

找不到 handler 时，实现要么在搜索阶段就失败（不回溯），要么像单阶段实现那样一路回溯到栈底再发现没有 handler（完全回溯）；"回溯到一半停下"没有对应的自然实现，也没有好处。

noexcept 的情形不同：边界在调用栈的**中间**。两阶段实现把 noexcept 函数当作一个 handler，清理阶段自然只回溯到它为止；而 noexcept 函数自己的帧不必清理。允许"部分回溯"恰好描述了这种最高效的实现，同时也允许单阶段实现完全回溯或完全不回溯。
</details>

!!! question "思考题 2"
    静态对象的构造函数抛出异常（1.5）时，标准允许回溯栈吗？

<details markdown="1">
<summary>答案</summary>

不允许。1.5 不属于 ¶2 列出的两种例外，落入"所有其他情形"：调用 `std::terminate` 之前栈**不得**回溯。（实际上这里也没有多少栈：调用来自运行时启动代码。但在初始化函数内部的局部对象确实不会被析构。）
</details>

## 小结

!!! summary
    - 异常机制依赖 `std::terminate`、`uncaught_exceptions`、`current_exception`、`nested_exception` 四个库设施。
    - `std::terminate` 有 19 种触发场景，核心是"两个异常同时传播"、"找不到 handler"、"穿过 noexcept 边界"、"静态对象的初始化/析构抛出"和"`throw;` 时没有异常"。
    - 栈回溯：找不到 handler ⇒ 实现定义；noexcept 边界 ⇒ 实现定义且可部分回溯；其他 ⇒ 不得回溯；一旦回溯不得提前结束。
