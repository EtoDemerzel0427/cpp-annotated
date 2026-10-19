---
title: 异常处理支持
summary: 头文件 <exception> 的基础部分：标准异常基类 std::exception 与 what() 返回值的有效期，bad_exception，异常处理无法继续时的 terminate 与 terminate_handler，以及用 uncaught_exceptions 写事务式析构函数。
status: done
covers: support.exception.general, exception.syn, exception, bad.exception, exception.terminate, terminate.handler, set.terminate, get.terminate, terminate, uncaught.exceptions
papers: N4152
related: except, except.throw, except.handle, except.terminate, except.spec, propagation, support.start.term, alloc.errors, support.rtti
tags: 标准库, 异常, terminate, uncaught_exceptions
updated: 2026-10-19
---

!!! tldr
    - `std::exception` 是标准库异常的公共基类，但语言并不要求被抛出的对象派生自它，`throw 42;` 完全合法。
    - 标准异常类的复制操作都不抛异常；`what()` 返回的指针在异常对象销毁后失效。
    - 异常处理无法继续时，实现调用 `std::terminate`，它调用当前的 terminate_handler，默认的 handler 调用 `abort()`。自定义 handler 不得返回。
    - 因未捕获的异常进入 `terminate` 时，handler 里的 `std::current_exception()` 能拿到那个异常，可以打印它。
    - `uncaught_exceptions()` 返回当前线程里已抛出、尚未被捕获的异常个数。事务式析构函数应当比较构造时和析构时的计数，而不是检查是否大于 0。

`<exception>` 定义与异常处理有关的类型和函数（[support.exception.general]）。第 14 章 [[except]] 规定了异常的语言机制，这里是配合它的库设施。整个头文件是 freestanding 的。

| 组件 | 用途 | 详见 |
|---|---|---|
| `exception`、`bad_exception` | 标准异常基类；`current_exception` 复制失败时的替代 | 本页 |
| `terminate_handler`、`set_terminate`、`get_terminate`、`terminate` | 异常处理无法继续时的出口 | 本页 |
| `uncaught_exceptions` | 当前线程里未捕获的异常个数 | 本页 |
| `exception_ptr`、`current_exception`、`rethrow_exception`、`make_exception_ptr`、`exception_ptr_cast` | 在 handler 之外持有、传递、重抛异常 | [[propagation]] |
| `nested_exception`、`throw_with_nested`、`rethrow_if_nested` | 异常链 | [[propagation]] |

## `std::exception` [exception]

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

¶1 `exception` 是标准库组件和某些表达式报告运行时错误时所抛对象的基类。某些表达式指语言本身抛出的异常：`dynamic_cast` 失败抛 `bad_cast`（[[expr.dynamic.cast]]），`typeid` 遇到空指针抛 `bad_typeid`（[[expr.typeid]]），数组长度非法时 `new` 抛 `bad_array_new_length`（[[expr.new]]）。

### 复制不抛异常（¶2–¶3）

¶2 除非另有说明，每个派生自 `exception` 的标准库类都有公开的默认构造函数（除非概要列出了别的构造函数）、复制构造函数和复制赋值运算符，三者都不抛异常。复制之后，两个动态类型相同的对象的 `what()` 用 `strcmp` 比较相等。第 3 段对 `exception` 本身规定了同样的后置条件。

不抛异常的原因在于异常对象可能被复制，比如 `current_exception` 可以复制当前异常（[[propagation]]）。复制时再抛出异常，就会落入处理异常时又出异常的局面。所以 `std::runtime_error` 这类携带消息的异常不能用 `std::string` 保存消息，因为 `std::string` 的复制可能抛 `bad_alloc`。libc++ 和 libstdc++ 都用引用计数的不可变字符串，复制只增加计数。

### `what()` 的返回值何时失效（¶5–¶6）

```cpp run title="what-lifetime.cpp" ub
#include <cstdio>
#include <stdexcept>

const char* message() {
  try {
    throw std::runtime_error("boom");
  } catch (const std::exception& e) {
    return e.what();   // 指向异常对象内部
  }                    // 离开 handler：异常对象被销毁
}

int main() {
  std::puts(message());   // UB：指针已经失效
}
```

¶6 `what()` 的返回值一直有效，直到取得它的异常对象被销毁，或者调用了该对象的非 const 成员函数。上例中 handler 退出时异常对象被销毁（[[except.throw]]），返回的指针随之失效。本机用 AddressSanitizer 运行，报告 heap-use-after-free。

¶5 `what()` 返回由实现定义的空终止字节串，在常量求值中使用普通字面量编码（[[lex.ccon]]）。第 6 段还说明它可以是适合转换为 `wstring` 显示的多字节字符串。

!!! note "`constexpr` 的异常类 {{c++26}}"
    C++26 允许在常量求值中抛出和捕获异常，`exception` 的成员因此都成了 `constexpr`，第 5 段也因此要规定常量求值中的编码。本机 Clang 23 还不支持在常量求值中执行 *throw-expression*，libc++ 也还没有把这些成员标为 `constexpr`。

## `bad_exception` [bad.exception]

¶1 `current_exception()` 复制当前异常对象失败时，返回的 `exception_ptr` 可以指向一个 `bad_exception` 对象（详见 [[propagation]]）。第 2 段规定它的 `what()` 返回由实现定义的字符串。

!!! history "动态异常说明的遗物"
    `bad_exception` 原本服务于动态异常说明 `throw(A, B)`：函数抛出了列表之外的异常时调用 `std::unexpected()`，如果列表里有 `std::bad_exception`，意外的异常会被替换成它。动态异常说明在 C++11 弃用、C++17 移除，`std::unexpected` 也随之消失。现在 `bad_exception` 只剩 `current_exception` 这一个用途。

## 异常处理无法继续时 [exception.terminate]

```cpp run title="terminate-handler.cpp"
#include <cstdio>
#include <cstdlib>
#include <exception>
#include <stdexcept>

[[noreturn]] void report_and_abort() {
  // 因未捕获的异常进入 terminate 时，current_exception() 能拿到它
  if (std::exception_ptr p = std::current_exception()) {
    try {
      std::rethrow_exception(p);
    } catch (const std::exception& e) {
      std::fprintf(stderr, "uncaught: %s\n", e.what());
    } catch (...) {
      std::fprintf(stderr, "uncaught non-std exception\n");
    }
  }
  std::abort();   // 不得返回
}

int main() {
  std::set_terminate(report_and_abort);
  throw std::runtime_error("boom");   // 没有 handler：调用 std::terminate
}
```

程序打印 `uncaught: boom`，然后以 SIGABRT 结束。异常没有被捕获、`noexcept` 函数里逃出了异常、栈回溯期间析构函数又抛出异常，这些情况下异常处理无法继续，实现会调用 `std::terminate`（完整列表见 [[except.terminate]]）。`terminate` 再调用一个可以由程序指定的 handler。

handler 能拿到异常，是因为 [[except.handle]] 规定：因抛出异常而进入 `std::terminate` 时，视为有一个隐式的 handler 处于活动状态，那个异常就是当前处理的异常。libc++abi 的默认 handler 也是这样做的，它打印 `libc++abi: terminating due to uncaught exception of type ...` 之后调用 `abort`。

### `terminate_handler`（[terminate.handler]）

¶1 `terminate_handler` 是 `void (*)()`，即 `terminate` 结束异常处理时调用的**处理函数**（[[g:terminate-handler]]）的类型。

¶2 Required behavior：它必须终止程序，不返回调用者。自定义 handler 返回了，行为未定义（[[res.on.functions]]）。

¶3 Default behavior：默认的 handler 调用 `abort()`。`abort` 不析构任何对象，不运行 `atexit` 注册的函数，也不刷新 C 流（[[support.start.term]]）。

### `set_terminate`、`get_terminate`（[set.terminate]、[get.terminate]）

```cpp
terminate_handler set_terminate(terminate_handler f) noexcept;
terminate_handler get_terminate() noexcept;
```

`set_terminate` 把 `f` 设为当前 handler（¶1），返回之前的 handler（¶2）。第 3 段规定，空指针是否表示默认 handler 是未指定的。`get_terminate` 返回当前 handler，注 1 提醒它可能是空指针。

可以对照 [[alloc.errors]] 的 new_handler。没有 new_handler 有明确的含义（直接抛 `bad_alloc`），所以它的初始值就是空指针。terminate 总得调用某个 handler，所以初始值是一个调用 `abort` 的默认函数；本机 libc++ 中 `set_terminate` 第一次返回的就是一个非空指针。

### `terminate`（[terminate]）

```cpp
[[noreturn]] void terminate() noexcept;
```

¶1 调用一个 terminate_handler。通常是当前的 handler；如果调用 `set_terminate` 时正有异常处于活动状态，调用哪个 handler 是未指定的。注 1 说明，这里默认 handler 总是被视为可调用的。

¶2 实现在异常处理必须放弃时调用它（[[except.terminate]]），程序也可以直接调用。找不到匹配的 handler 时，调用 `terminate` 之前栈是否回溯由实现定义（[[except.terminate#2]]）。

## `uncaught_exceptions` [uncaught.exceptions] {{c++17}}

```cpp run title="uncaught-exceptions.cpp" ok
#include <cstdio>
#include <exception>

class Transaction {
  int entry_ = std::uncaught_exceptions();   // 构造时记录
public:
  ~Transaction() {
    if (std::uncaught_exceptions() > entry_) std::puts("rollback");
    else                                      std::puts("commit");
  }
};

struct Logger {
  ~Logger() { Transaction t; }   // 在栈回溯期间运行
};

int main() {
  { Transaction t; }                              // commit
  try { Transaction t; throw 1; } catch (...) {}  // rollback
  try { Logger l; throw 2; } catch (...) {}       // commit
}
```

事务对象希望在析构时知道自己是正常离开作用域（提交），还是因为异常的栈回溯而被析构（回滚）。

¶1 `uncaught_exceptions()` 返回当前线程中**未捕获的异常**（[[g:uncaught-exception]]）的个数。一个异常从异常对象初始化完成起，到某个 handler 激活为止，处于未捕获状态（[[except.throw]]），也就是已经抛出、正在栈回溯、还没进入 `catch` 的那段时间。

第三种情形说明了为什么要比较计数。`Logger` 的析构函数在栈回溯期间运行，这时计数是 1；但里面的 `Transaction` 构造时计数也是 1，它是正常结束的，应当提交。只检查计数是否大于 0 会误判为回滚。

¶2 计数大于 0 时，再抛出异常可能导致调用 `std::terminate`，比如栈回溯中的析构函数抛出的异常逃出了析构函数。说可能，是因为在析构函数内部捕获掉就没有问题。

!!! history "从 `uncaught_exception()` 到 `uncaught_exceptions()`"
    C++98 只有单数形式的 `bool uncaught_exception()`，只能回答有没有未捕获的异常，上例第三种情形正好会误判。[[N4152]] 引入了返回计数的版本（C++17），单数形式在 C++17 弃用、C++20 移除。本机 libc++ 在 `-std=c++2c` 下已经没有 `std::uncaught_exception`。

!!! pitfall "协程里的计数"
    计数是每个线程各自的，事务对象在构造时记下快照。如果对象位于协程帧中，而协程在一个线程挂起、在另一个线程恢复，或者在栈回溯过程中被挂起再恢复，构造时和析构时的计数就失去了可比性。
