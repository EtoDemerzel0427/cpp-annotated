---
title: 核心 UB 目录 · 第 [stmt] 章
summary: Annex F.4 的 3 条：非 void 函数流出末尾、协程在没有 return_void 时流出函数体、块作用域静态变量的递归初始化——正文出处、例子与 Clang 23 实测。
status: draft
related: ub, stmt.return, stmt.return.coroutine, stmt.dcl, dcl.fct.def.coroutine
tags: UB, 附录, 语句, 协程
updated: 2026-10-18
---

这一页是 [[ub]] 的一部分，对应 Annex F.4：第 8 章 [stmt] 中的显式 UB。三条都与"控制流走到了不该走到的地方"有关。实测环境同 [[ub.basic]]。

### F.4.1 [ub:stmt.return.flow.off] {#stmt.return.flow.off}

**非 void 函数流出末尾** · 正文 [[stmt.return#4]]

构造函数、析构函数和返回 cv `void` 的非协程函数流出末尾，等价于 `return;`。其他函数——`main` 和协程除外——流出末尾是 UB。

与 C 的区别值得记住：C 只在**调用方使用了返回值**时才是 UB；C++ 里**一旦流出末尾**就是 UB，不管返回值有没有人用。这使得编译器可以把"流出末尾"的路径当作不可达。

```cpp ub run flags="-std=c++2c -O2" cc=clang_trunk
#include <cstdio>

int f(int x) {
  if (x)
    return 1;
}   // x == 0 时 UB

int main(int argc, char**) {
  std::printf("%d\n", f(argc - 1));   // 不带参数运行时 argc - 1 == 0
}
```

**实测**：

- 编译期：`warning: non-void function does not return a value in all control paths [-Wreturn-type]`。
- `-O2`：打印 `1`。Clang 推断"x 为 0 的路径是 UB，故不可能发生"，把 `f` 优化成了无条件 `return 1`。
- `-O0 -fsanitize=undefined`：UBSan 的 `return` 检查报 `execution reached the end of a value-returning function without returning a value` 并终止。
- **常量求值**：`constexpr int v = f(0);` 被拒，`control reached end of constexpr function`。

### F.4.2 [ub:stmt.return.coroutine.flow.off] {#stmt.return.coroutine.flow.off}

**协程流出函数体末尾，而 promise 没有 return_void** · 正文 [[stmt.return.coroutine#3]]

协程的"返回"是对 promise 对象的调用：`co_return;` 调 `p.return_void()`，`co_return e;` 调 `p.return_value(e)`。流出函数体末尾等价于 `co_return;`——前提是 `p.return_void()` 能通过重载决议；否则流出末尾就是 UB。一个 promise 类型只能有二者之一（[[dcl.fct.def.coroutine]]），所以"返回值的协程"忘写 `co_return` 就会落到这里。

```cpp ub
#include <coroutine>
#include <exception>

struct task {
  struct promise_type {
    const char* s = nullptr;
    task get_return_object() { return {std::coroutine_handle<promise_type>::from_promise(*this)}; }
    std::suspend_always initial_suspend() { return {}; }
    std::suspend_always final_suspend() noexcept { return {}; }
    void unhandled_exception() { std::terminate(); }
    void return_value(const char* v) { s = v; }   // 只有 return_value，没有 return_void
  };
  std::coroutine_handle<promise_type> h;
  ~task() { h.destroy(); }
};

task foo() {
  co_await std::suspend_always{};
}   // UB：流出协程体末尾，而 p.return_void() 不存在

int main() {
  task t = foo();
  while (!t.h.done()) t.h.resume();
  return t.h.promise().s != nullptr;
}
```

（附录原例更长，用 `std::cout` 打印 `return_val()`；这里保留了其核心结构。）

**实测**：编译期 `warning: non-void coroutine does not return a value [-Wreturn-type]`；运行时无 sanitizer 报告，`s` 保持默认的空指针。附录原例打印 `string_` 时会读到一个未初始化的指针成员，问题会更隐蔽。

### F.4.3 [ub:stmt.dcl.local.static.init.recursive] {#stmt.dcl.local.static.init.recursive}

**块作用域静态变量的初始化递归重入** · 正文 [[stmt.dcl#3]]

块作用域静态变量在控制流第一次经过声明时初始化；并发进入的线程要等待（这就是"magic statics"的线程安全保证）。但**同一线程**递归地重新进入正在初始化的声明，标准没法给它任何合理的语义，于是 UB。

```cpp ub run flags="-std=c++2c -O0" cc=clang_trunk
#include <cstdio>

int foo(int i) {
  static int s = foo(2 * i);   // UB：初始化过程中递归进入同一声明
  return i + 1;
}

int main() { std::printf("%d\n", foo(1)); }
```

**实测**：本机 libc++abi 的守卫变量实现会检测到这种情况并中止程序：`libc++abi: __cxa_guard_acquire detected recursive initialization: do you have a function-local static variable whose initialization depends on that function?`。这是运行库的善意，不是标准的要求；其他实现上同样的代码可能死锁。
