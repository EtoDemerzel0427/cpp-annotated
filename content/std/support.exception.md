---
title: 异常处理支持
summary: <exception> 的基石——std::exception 与 what() 的生命期约定、bad_exception、terminate_handler 的 Required/Default behavior、set_terminate/get_terminate/terminate 的精确语义，以及 uncaught_exceptions 与"事务式"析构函数
status: done
covers: support.exception.general, exception.syn, exception, bad.exception, exception.terminate, terminate.handler, set.terminate, get.terminate, terminate, uncaught.exceptions
papers: N4152
related: except, except.throw, except.handle, except.terminate, except.spec, propagation, support.start.term, alloc.errors, support.rtti
tags: 标准库, 异常, terminate, uncaught_exceptions
updated: 2026-10-18
---

第 14 章 [[except]] 规定了异常的核心语言机制：`throw` 怎样创建异常对象，handler 怎样匹配，栈怎样回溯，什么时候调用 `std::terminate`。但那些机制需要一些**库**的配合：一个约定俗成的异常基类、一个可定制的"终止"入口、一个查询"现在有几个异常在飞"的函数、以及在 handler 之外持有异常的手段。这些都在 `<exception>` 里。

¶1（[support.exception.general]）：`<exception>` 定义了若干与 C++ 程序中异常处理相关的类型和函数。

| 组件 | 用途 | 页面 |
|---|---|---|
| `exception`、`bad_exception` | 标准异常基类；`current_exception` 复制失败时的替代品 | 本页 |
| `terminate_handler`、`set_terminate`、`get_terminate`、`terminate` | 异常处理无法继续时的终止入口 | 本页 |
| `uncaught_exceptions` | 当前线程中未捕获异常的个数 | 本页 |
| `exception_ptr`、`current_exception`、`rethrow_exception`、`make_exception_ptr`、`exception_ptr_cast` | 在 handler 之外持有、传递、重抛异常 | [[propagation]] |
| `nested_exception`、`throw_with_nested`、`rethrow_if_nested` | 异常链 | [[propagation]] |

整个头文件是 freestanding 的（[exception.syn]）。

## `std::exception`（[exception]）

```cpp
class exception {
public:
  constexpr exception() noexcept;
  constexpr exception(const exception&) noexcept;
  constexpr exception& operator=(const exception&) noexcept;
  constexpr virtual ~exception();
  constexpr virtual const char* what() const noexcept;
};
```

¶1：`exception` 是 C++ 标准库组件**以及某些表达式**为报告运行期错误而抛出的对象类型的**基类**。"某些表达式"指的是核心语言直接抛出的异常：`new` 失败（`bad_alloc`，[[expr.new]]）、`dynamic_cast` 失败（`bad_cast`，[[expr.dynamic.cast]]）、`typeid` 空指针（`bad_typeid`，[[expr.typeid]]）。

注意：**核心语言并不要求被抛出的对象派生自 `std::exception`**——`throw 42;` 完全合法。`std::exception` 只是标准库的约定。

### 派生类的统一契约（¶2）

除非另有明确说明，每个派生自 `exception` 的标准库类 `T` 都具有以下公开成员函数，且都具有**非抛出**的异常说明：

- ¶2.1 默认构造函数（除非类概要列出了其他构造函数）；
- ¶2.2 复制构造函数；
- ¶2.3 复制赋值运算符。

复制构造和复制赋值满足后置条件：若 `lhs` 和 `rhs` 的动态类型都是 `T`，且 `lhs` 是 `rhs` 的副本，则 `strcmp(lhs.what(), rhs.what()) == 0`。每个这样的 `T` 的 `what()` 都满足 `exception::what()` 的约束。

这条"复制不抛异常"的要求有深刻的原因：异常对象在抛出、捕获、`current_exception` 时可能被复制（[[except.throw]]），如果复制本身抛出异常，就会陷入"处理异常时又抛异常"的局面，按 [[except.terminate]] 导致 `std::terminate`。这也解释了为什么 `std::runtime_error` 这类携带字符串的异常，在实现中不能用 `std::string` 存储消息（`std::string` 的复制可能抛 `bad_alloc`）——libc++ 和 libstdc++ 都使用**引用计数的不可变字符串**，复制只增加计数。

### `what()` 的约定（¶3–¶6）

- ¶3：动态类型都是 `exception` 时，复制后的 `what()` 内容相同。
- ¶5 *Returns*：一个**由实现定义的** NTBS；在常量求值中，它使用普通字面量编码（[[lex.ccon]]）。
- ¶6 *Remarks*：消息可以是适合转换为 `wstring` 显示的空终止多字节字符串。**返回值保持有效，直到获取它的异常对象被销毁，或者该异常对象的非 `const` 成员函数被调用。**

¶6 的后半句是一个容易被忽略的生命期约定：

```cpp run title="what-lifetime.cpp" ub
#include <cstdio>
#include <stdexcept>

const char* get_message() {
    try {
        throw std::runtime_error("boom");
    } catch (const std::exception& e) {
        return e.what();           // 指针指向异常对象内部的存储
    }                              // handler 退出：异常对象被销毁（[except.throw]）
}

int main() {
    std::puts(get_message());      // UB: what() 的返回值已经失效
}
```

!!! note "`constexpr` 的异常类 {{c++26}}"
    C++26 允许在常量求值中抛出和捕获异常，于是 `exception` 的所有成员都成为 `constexpr`，¶5 也因此专门规定常量求值中 `what()` 的编码。截至本文编写时，Clang 尚不支持在常量求值中执行 *throw-expression*（`constexpr` 函数中的 `throw` 被求值时，表达式不是常量表达式），libc++ 也尚未把这些成员标为 `constexpr`。

## `bad_exception`（[bad.exception]）

¶1：`bad_exception` 是这样一种对象的类型：当前活动的异常对象**复制失败**时，`current_exception`（[[propagation]]）返回的 `exception_ptr` 所指向的对象。¶2：`what()` 返回由实现定义的 NTBS。

!!! history "动态异常说明的遗物"
    在 C++17 之前，`bad_exception` 主要用于动态异常说明 `throw(A, B)`：函数抛出未列出的异常时会调用 `std::unexpected()`，若异常说明中包含 `std::bad_exception`，未预期的异常会被替换成 `bad_exception`。动态异常说明在 C++11 被弃用，C++17 移除（只保留 `throw()` 作为 `noexcept` 的同义词，C++20 也移除了），`std::unexpected` 随之消失。今天 `bad_exception` 只剩 `current_exception` 这一个用途。

## 异常终止（[exception.terminate]）

### `terminate_handler`（[terminate.handler]）

```cpp
using terminate_handler = void (*)();
```

¶1：由 `terminate` 在**终止异常处理**时调用的**处理函数**（[[g:terminate-handler]]）的类型。

¶2 *Required behavior*：`terminate_handler` **必须终止程序的执行，不返回调用者**。

¶3 *Default behavior*：实现的默认 `terminate_handler` 调用 `abort()`。

所以默认情况下，未捕获的异常最终调用 `std::abort`——不析构任何对象，不调用 `atexit` 回调，不刷新 C 流（[[support.start.term]]）。如果自定义 handler 返回了，就违反了 *Required behavior*，行为未定义（[[res.on.functions]]）。

### `set_terminate` 与 `get_terminate`（[set.terminate]、[get.terminate]）

```cpp
terminate_handler set_terminate(terminate_handler f) noexcept;
terminate_handler get_terminate() noexcept;
```

- `set_terminate`：把 `f` 设为当前的终止处理函数（¶1），返回**之前的** handler（¶2）。¶3 *Remarks*：**空指针值是否表示默认 handler 是未指明的**。
- `get_terminate`：返回当前的 `terminate_handler`。注 1：可能是空指针值。

对比 [[alloc.errors]] 的 `new_handler`：初始 new_handler 明确是空指针（因为"没有 handler"有确定的语义：直接抛 `bad_alloc`）；而 terminate_handler 不能"没有"，所以初始值是一个调用 `abort` 的默认函数，用空指针去设置它的效果则是未指明的。libc++ 的初始 handler 是一个非空的函数指针（下例中 `old == nullptr` 为假）。

### `terminate`（[terminate]）

```cpp
[[noreturn]] void terminate() noexcept;
```

¶1 *Effects*：调用一个 `terminate_handler`。如果在调用 `set_terminate` 期间有异常处于活动状态，调用哪个 handler 是**未指明的**；否则调用**当前的** handler。注 1：在此语境下，默认 handler 总是被视为一个可调用的 handler。

¶2 *Remarks*：当异常处理因某些原因必须放弃时，由**实现**调用（[[except.terminate]] 列出了全部场景）；也可以由程序**直接**调用。

[[except.terminate]] 规定的触发场景包括：异常未被捕获、`noexcept` 函数以异常退出、栈回溯期间析构函数抛出异常、静态对象初始化或析构抛出异常、`atexit` 回调抛出异常、`std::thread` 在可 join 状态下被析构……此外，[[except.terminate#2]] 规定：未找到匹配 handler 时，调用 `terminate` 之前栈是否回溯是**由实现定义**的；handler 搜索离开一个 `noexcept` 函数的函数体时，栈是完整回溯、部分回溯还是完全不回溯，也是由实现定义的。

一个常见的需求是在程序因未捕获异常而终止时**打印异常信息**：

```cpp run title="terminate-handler.cpp"
#include <cstdio>
#include <cstdlib>
#include <exception>
#include <stdexcept>

[[noreturn]] void my_handler() {
    // 若因未捕获的异常而终止，该异常此时是"当前处理的异常"（[except.handle]：隐式 handler 处于活动状态）
    if (std::exception_ptr p = std::current_exception()) {
        try { std::rethrow_exception(p); }
        catch (const std::exception& e) { std::fprintf(stderr, "uncaught exception: %s\n", e.what()); }
        catch (...)                     { std::fprintf(stderr, "uncaught non-std exception\n"); }
    } else {
        std::fprintf(stderr, "terminate called without an active exception\n");
    }
    std::abort();                       // Required behavior：不得返回
}

int main() {
    std::terminate_handler old = std::set_terminate(my_handler);
    std::fprintf(stderr, "previous handler is null: %d\n", old == nullptr);   // libc++：0
    throw std::runtime_error("boom");   // 未捕获 → std::terminate → my_handler，进程以 SIGABRT 结束
}
```

这依赖 [[except.handle]] 中的一条规定：因抛出而进入 `std::terminate` 时，一个**隐式 handler** 被视为活动的，所以 `current_exception()` 能拿到那个未捕获的异常。libc++abi 的默认 handler 也是这样做的：它打印 `libc++abi: terminating due to uncaught exception of type ...: what()` 后调用 `abort`。

## `uncaught_exceptions`（[uncaught.exceptions]）{{c++17}}

```cpp
int uncaught_exceptions() noexcept;
```

¶1 *Returns*：**当前线程**中**未捕获的异常**（[[g:uncaught-exception]]，[[except.throw]]）的个数。"未捕获"指从异常对象初始化完成，到某个 handler 激活完成之间的状态——简单说，就是"已经抛出、正在栈回溯、还没进入 catch"的异常。

¶2 *Remarks*：当 `uncaught_exceptions() > 0` 时，抛出异常**可能**导致调用 `std::terminate`。典型情形：栈回溯期间某个析构函数抛出异常并逃出析构函数。"可能"是因为如果新异常在析构函数**内部**被捕获，就不会出问题。

它的主要用途是写**事务式析构函数**：析构函数需要区分"正常离开作用域"（提交）和"因异常栈回溯而离开"（回滚）。

```cpp run title="uncaught-exceptions.cpp" ok
#include <cstdio>
#include <exception>
#include <stdexcept>

class Transaction {
    int entry_ = std::uncaught_exceptions();   // 构造时记录
public:
    ~Transaction() {
        if (std::uncaught_exceptions() > entry_) std::puts("rollback（因异常而析构）");
        else                                      std::puts("commit（正常析构）");
    }
};

struct Logger {
    ~Logger() {
        try { Transaction t; } catch (...) {}  // 在栈回溯期间创建并正常结束：entry_ == 1，析构时也是 1
    }
};

int main() {
    { Transaction t; }                                                    // commit
    try { Transaction t; throw std::runtime_error("x"); } catch (...) {}  // rollback
    try { Logger l; throw 42; } catch (...) {}                            // commit
}
```

第三种情形说明了为什么要**比较计数**而不是检查"是否大于 0"：`Logger` 的析构函数在栈回溯期间运行，此时 `uncaught_exceptions() == 1`，但其中的 `Transaction` 是正常结束的，应当提交。

!!! history "从 `uncaught_exception()` 到 `uncaught_exceptions()`"
    C++98 提供的是单数形式 `bool uncaught_exception()`，只能回答"是否有未捕获的异常"，于是上例第三种情形会被误判为回滚。[[N4152]] 引入了返回计数的 `uncaught_exceptions()`（C++17），单数形式在 C++17 被弃用、C++20 被移除。libc++ 仍保留着带弃用标记的旧函数。这一机制是 Andrei Alexandrescu 的 `SCOPE_FAIL`/`SCOPE_SUCCESS` 惯用法的基础。

!!! pitfall "协程与 `uncaught_exceptions`"
    计数是**每线程**的，并且是在对象**构造时**快照的。如果对象生活在协程帧中，协程在一个线程上挂起、在另一个线程上恢复，或者在异常栈回溯过程中被挂起又恢复，构造时记录的 `entry_` 与析构时的计数之间就失去了可比性。

## 小结

!!! summary
    - `exception` 是标准库约定的基类，核心语言不要求抛出对象派生自它；派生类的复制操作都不抛异常。
    - `what()` 的指针在异常对象销毁或调用非 `const` 成员后失效。
    - `bad_exception` 现在只用于 `current_exception` 复制失败。
    - `terminate_handler` 必须不返回；默认调用 `abort`；`set_terminate(nullptr)` 的效果未指明。
    - 因未捕获异常进入 `terminate` 时有隐式活动 handler，`current_exception()` 可拿到该异常。
    - `uncaught_exceptions()` 返回当前线程未捕获异常的个数；事务式析构函数应**比较**构造时与析构时的计数。
