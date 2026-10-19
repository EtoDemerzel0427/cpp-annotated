---
title: 核心 UB 目录 · 第 [stmt] 章
summary: 第 8 章明文写出的三条未定义行为：非 void 函数执行到末尾却没有 return、协程在没有 return_void 时执行到函数体末尾、块作用域静态变量在初始化过程中被递归地再次进入。
status: done
related: ub, stmt.return, stmt.return.coroutine, stmt.dcl, dcl.fct.def.coroutine
tags: UB, 附录, 语句, 协程
updated: 2026-10-19
---

!!! tldr
    - 返回类型不是 `void` 的普通函数执行到末尾而没有遇到 `return`，就是未定义行为，不管调用方用不用返回值；`main` 是例外。
    - 编译器会把这条路径当作不可达，`-O2` 下可能直接删掉相应的分支，所以 `-Wreturn-type` 警告不能忽略。
    - 协程执行到函数体末尾等价于 `co_return;`，前提是 promise 类型有 `return_void`；只有 `return_value` 时就是未定义行为。
    - 块作用域的静态变量在初始化过程中又递归地进入同一声明，是未定义行为；本机运行库会检测到并中止程序，其他实现可能死锁。

Annex F 汇总了核心语言中明文写出的未定义行为，总览见 [[ub]]。它的 F.4 节对应第 8 章 [stmt]，共三条，都是控制流走到了不该走到的地方。

下文的运行结果都来自本机 Clang 23（arm64 macOS），编译选项写在各个例子上。

### F.4.1 非 void 函数执行到末尾 {#stmt.return.flow.off}

`[ub:stmt.return.flow.off]` · 正文 [[stmt.return#4]]

```cpp run ub flags="-std=c++2c -O2" cc=clang_trunk
#include <cstdio>

int f(int x) {
  if (x)
    return 1;
}   // x == 0 时 UB

int main(int argc, char**) {
  std::printf("%d\n", f(argc - 1));   // 不带参数运行时实参为 0
}
```

构造函数、析构函数和返回 cv `void` 的普通函数执行到末尾时，等价于 `return;`。其他函数执行到末尾就是未定义行为，但 `main`（等价于返回 0）和协程（见下一条）除外。

这一点和 C 不同。C 只在调用方使用了返回值时才算未定义行为；C++ 只要执行到末尾就是未定义行为，与返回值有没有被使用无关。所以编译器可以认定这条路径永远不会被执行。

本机编译时，Clang 给出警告 `non-void function does not return a value in all control paths [-Wreturn-type]`。用 `-O2` 编译后不带参数运行，程序打印 `1`：Clang 认定 `x == 0` 的路径不会发生，把 `f` 优化成了无条件返回 1。

用 `-O0 -fsanitize=undefined` 编译，UBSan 报告 `execution reached the end of a value-returning function without returning a value` 并终止程序。把 `f` 声明为 `constexpr` 并在常量求值中调用 `f(0)`，编译器会拒绝，诊断是 `control reached end of constexpr function`。

### F.4.2 协程执行到函数体末尾，而 promise 没有 return_void {#stmt.return.coroutine.flow.off}

`[ub:stmt.return.coroutine.flow.off]` · 正文 [[stmt.return.coroutine#3]]

协程的返回操作是对 promise 对象（协程帧里保存结果和状态的对象，见 [[dcl.fct.def.coroutine]]）的调用：`co_return;` 调用 `p.return_void()`，`co_return e;` 调用 `p.return_value(e)`。一个 promise 类型只能有这两个函数中的一个。

如果 `p.return_void()` 能通过重载决议，协程执行到函数体末尾就等价于 `co_return;`。否则，执行到末尾就是未定义行为。所以，返回值的协程忘写 `co_return e;`，就会落到这一条。

```cpp run ub
#include <coroutine>
#include <exception>

struct task {
  struct promise_type {
    const char* s = nullptr;
    task get_return_object() {
      return {std::coroutine_handle<promise_type>::from_promise(*this)};
    }
    std::suspend_always initial_suspend() { return {}; }
    std::suspend_always final_suspend() noexcept { return {}; }
    void unhandled_exception() { std::terminate(); }
    void return_value(const char* v) { s = v; }   // 只有 return_value
  };
  std::coroutine_handle<promise_type> h;
  ~task() { h.destroy(); }
};

task foo() {
  co_await std::suspend_always{};
}   // UB：执行到协程体末尾，而 p.return_void() 不存在

int main() {
  task t = foo();
  while (!t.h.done()) t.h.resume();
  return t.h.promise().s != nullptr;
}
```

本机编译时，Clang 给出警告 `non-void coroutine does not return a value [-Wreturn-type]`。运行时 ASan 和 UBSan 都没有报告，`s` 保持默认的空指针。附录原例没有给 `string_` 成员默认值，最后打印它时会读到一个未初始化的指针，问题更隐蔽。

### F.4.3 块作用域静态变量的初始化被递归地再次进入 {#stmt.dcl.local.static.init.recursive}

`[ub:stmt.dcl.local.static.init.recursive]` · 正文 [[stmt.dcl#3]]

块作用域的静态变量在控制第一次经过它的声明时初始化。如果另一个线程在初始化进行期间也进入这个声明，它必须等待初始化完成，这就是函数内静态变量初始化的线程安全保证。

如果是同一个线程在初始化过程中递归地再次进入这个声明，标准无法给出合理的语义：等待会死锁，不等待又会读到还没初始化好的变量。所以这种情况是未定义行为。

```cpp run ub flags="-std=c++2c -O0" cc=clang_trunk
#include <cstdio>

int foo(int i) {
  static int s = foo(2 * i);   // UB：初始化过程中递归进入同一声明
  return i + 1;
}

int main() { std::printf("%d\n", foo(1)); }
```

本机编译时，Clang 给出 `-Winfinite-recursion` 警告。运行时，libc++abi 的守卫变量（编译器用来记录静态变量是否已初始化的标志）检测到递归初始化，打印 `libc++abi: __cxa_guard_acquire detected recursive initialization: do you have a function-local static variable whose initialization depends on that function?` 后中止程序。这是运行库额外提供的检查，标准并不要求；在其他实现上，同样的代码可能死锁。
