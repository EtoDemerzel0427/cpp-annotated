---
title: co_await
summary: co_await 表达式怎样从操作数得到 awaiter，再按 await_ready、await_suspend、await_resume 的结果决定是否挂起、把控制交给谁、得到什么值，以及它可以写在哪里。
status: draft
since: c++20
papers: P0912R5, P0913R1
related: dcl.fct.def.coroutine, expr.yield, stmt.return.coroutine, coroutine.handle, support.coroutine, over.match.oper, class.temporary
tags: 协程, co_await, awaiter, 对称转移
updated: 2026-10-19
---

!!! tldr
    - `co_await e` 先把 `e` 变成一个 awaiter 对象：promise 有 `await_transform` 就先调用它，再看有没有 `operator co_await`。
    - 之后依次调用 awaiter 的三个成员：`await_ready()` 为真就不挂起；否则调用 `await_suspend(h)`，它的返回类型（`void`、`bool`、`coroutine_handle`）决定控制交给谁；恢复后 `await_resume()` 的结果就是整个表达式的值。
    - 协程在调用 `await_suspend` 之前就已算作挂起，所以 `await_suspend` 可以把句柄交给别的线程去恢复。
    - `await_suspend` 返回另一个协程的句柄时，那个协程被直接恢复（对称转移），实现可以做成尾调用，长链等待不会耗尽栈。
    - `co_await` 不能出现在 `catch` 块、默认实参、静态局部变量的初始化器和契约谓词里。

{{c++20}} 函数体里只要出现 `co_await`、`co_yield` 或 `co_return`，这个函数就是**协程**（[[g:coroutine]]），见 [[dcl.fct.def.coroutine]]。协程可以在执行中途暂停，把控制交还给调用者，之后再从暂停的地方继续。是否是协程是函数定义的属性，调用者从声明上看不出来。

每个协程都关联一个 **promise 对象**（[[g:promise-object]]），它的类型由协程的返回类型决定，用来定制协程的行为。暂停的协程用 `std::coroutine_handle` 指代，对句柄调用 `resume()` 就能让它继续执行（[[coroutine.handle]]）。

`co_await` 是让协程暂停的那个表达式。它的行为几乎完全由库代码决定：标准只规定一个固定的流程，在流程中的几个位置调用用户提供的函数。

## 一个最小的例子

```cpp run ok
#include <coroutine>
#include <cstdio>

struct task {
  struct promise_type {
    task get_return_object() { return {}; }
    std::suspend_never initial_suspend() noexcept { return {}; }
    std::suspend_never final_suspend() noexcept { return {}; }
    void return_void() {}
    void unhandled_exception() {}
  };
};

struct ready {
  int v;
  bool await_ready() const noexcept { return true; }       // 已就绪：不挂起
  void await_suspend(std::coroutine_handle<>) noexcept {}  // 不会被调用
  int await_resume() const noexcept { return v; }          // co_await 的结果
};

struct maybe {
  bool await_ready() const noexcept { return false; }
  bool await_suspend(std::coroutine_handle<>) noexcept {
    return false;                                           // 改主意：立即恢复
  }
  const char* await_resume() const noexcept { return "resumed immediately"; }
};

task co() {
  int x = co_await ready{42};
  std::printf("%d\n", x);
  std::printf("%s\n", co_await maybe{});
}

int main() { co(); }
```

程序输出 `42` 和 `resumed immediately`。`task::promise_type` 是协程 `co` 的 promise 类型；`ready` 和 `maybe` 是 **awaiter**，也就是提供了 `await_ready`、`await_suspend`、`await_resume` 三个成员的对象。标准库的 `std::suspend_always` 和 `std::suspend_never` 是两个最简单的 awaiter：`await_ready` 分别返回 `false` 和 `true`，另外两个函数什么都不做。

¶1 *await-expression* 的文法是 `co_await cast-expression`，所以 `co_await` 与其他一元运算符优先级相同：`co_await a + b` 是 `(co_await a) + b`。

## 从操作数得到 awaiter（¶3.1–¶3.4）

`co_await x` 里的 `x` 不一定本身就是 awaiter。¶3 规定了一串辅助实体，按顺序如下：

1. ¶3.1 *p* 是外围协程的 promise 对象，`P` 是它的类型。
2. ¶3.2 在 `P` 的作用域里查找名字 `await_transform`。只要找到任何声明，*a* 就是 `p.await_transform(x)`；否则 *a* 就是 `x`。
3. ¶3.3 以 *a* 为实参，像其他可重载的一元运算符一样对 `operator co_await` 做重载决议（[[over.match.oper]]）。有歧义则非良构；没有可行函数，*o* 就是 *a*；否则 *o* 是对所选函数的调用。
4. ¶3.4 如果 *o* 是 prvalue，就做临时量实质化。*e* 是指代这个结果的左值，也就是 awaiter。之后的三次调用都作用在同一个对象 *e* 上。

```cpp run ok
#include <coroutine>
#include <cstdio>

struct awaiter_int {
  int v;
  bool await_ready() const noexcept { return true; }
  void await_suspend(std::coroutine_handle<>) noexcept {}
  int await_resume() const noexcept { return v; }
};

struct Seconds { int n; };
awaiter_int operator co_await(Seconds s) { return {s.n * 1000}; }   // 第 3 步

struct task {
  struct promise_type {
    task get_return_object() { return {}; }
    std::suspend_never initial_suspend() noexcept { return {}; }
    std::suspend_never final_suspend() noexcept { return {}; }
    void return_void() {}
    void unhandled_exception() {}
    Seconds await_transform(int n) { return {n}; }                  // 第 2 步
  };
};

task co() {
  int ms = co_await 3;   // a = p.await_transform(3)   → Seconds{3}
                         // o = operator co_await(a)    → awaiter_int{3000}
  std::printf("%d\n", ms);
}

int main() { co(); }
```

第 2 步做的是名字查找，不是检查能否调用。promise 声明了 `await_transform`，所有用户写的 `co_await x` 都会改写成 `p.await_transform(x)`；没有能接受 `x` 的重载时直接编译失败，不会退回到不变换。在上例中写 `co_await Seconds{1}` 就会失败，因为唯一的 `await_transform` 只接受 `int`。promise 类型可以借此用白名单控制协程体里能等待什么。C++23 的 `std::generator` 把 `await_transform` 声明为 deleted（[[coro.generator.promise]]），于是生成器里不能写 `co_await`。

`co_yield`、初始挂起和最终挂起隐式产生的 `co_await` 不经过第 2 步。它们的操作数是 `p.yield_value(v)`、`p.initial_suspend()`、`p.final_suspend()`，本来就由 promise 自己控制。

第 4 步说明 awaiter 是一个真实存在的临时对象。它在包含 `co_await` 的完整表达式结束时销毁，而这个完整表达式跨越了挂起，所以协程挂起期间 awaiter 一直存活，和跨越挂起的局部变量一样保存在协程状态（[[g:coroutine-state]]）里。awaiter 因此可以在 `await_suspend` 里把 `this` 交给别人，比如让 I/O 完成时把结果写进自己的成员，再由 `await_resume` 读出来。

## 三个成员函数与求值顺序（¶3.5–¶5）

¶3.5–¶3.8 定义了要调用的表达式：*h* 是指代外围协程的 `std::coroutine_handle<P>`；*await-ready* 是 `e.await_ready()`，按语境转换为 `bool`；*await-suspend* 是 `e.await_suspend(h)`，类型必须是 `void`、`bool` 或某个 `std::coroutine_handle<Z>`；*await-resume* 是 `e.await_resume()`。

三者都写成成员函数调用，没有非成员形式。`await_suspend` 的形参通常写成 `std::coroutine_handle<>`，由 `coroutine_handle<P>` 隐式转换而来；也可以写成 `coroutine_handle<P>`，以便访问 promise。

¶4 整个 `co_await` 表达式的类型和值类别与 `await_resume()` 相同：返回 `int` 就是 `int` prvalue，返回 `T&` 就是左值，返回 `void` 就是 `void` 表达式。

¶5 求值时先求 *o*，再求 `await_ready()`。整个流程可以写成下面的伪代码（标准里没有这段代码）：

```text
if (!e.await_ready()) {
    <协程算作已挂起>
    按 await_suspend(h) 的返回类型：
      coroutine_handle  → 调用它，然后对返回的句柄调用 .resume()
      bool              → 调用它；返回 false 则立即恢复当前协程
      void              → 调用它，然后返回调用者或恢复者
    <恢复后从这里继续>
}
result = e.await_resume();
```

### 挂起（¶5.1）

¶5.1 `await_ready()` 为 `false` 时，协程算作已挂起，而且这发生在调用 `await_suspend` 之前。所以在 `await_suspend` 内部，另一个线程就可以通过 `h` 恢复这个协程，不会违反恢复未挂起协程是 UB 的规则（[[dcl.fct.def.coroutine#8]]）。

接下来按 `await_suspend` 的返回类型分三种情况：

- ¶5.1.1 返回 `std::coroutine_handle<Z>`：调用它，再对返回的句柄调用 `.resume()`。这叫**对称转移**（symmetric transfer），见下一节。注 1 指出，这样可以接连恢复任意多个协程，最终控制回到当前协程的调用者或恢复者。
- ¶5.1.2 返回 `bool`：调用它，结果为 `false` 时当前协程立即恢复，接着执行 `await_resume`；为 `true` 时保持挂起。用途是 `await_suspend` 发现操作已经完成、来不及注册回调时返回 `false`，省掉一次挂起和恢复。
- ¶5.1.3 返回 `void`：调用它，然后控制返回当前协程的调用者或恢复者，不退出任何作用域，局部变量也不析构。返回之前的那一点叫做**挂起点**（[[g:suspend-point]]）。

¶5.1.3 还规定，如果 `await_suspend` 以异常退出，异常被捕获，协程恢复，然后异常立即重新抛出。效果是异常好像从 `co_await` 表达式本身抛出，可以被协程体里包住它的 `try` 捕获：

```cpp run ok
#include <coroutine>
#include <cstdio>
#include <stdexcept>

struct task { struct promise_type {
  task get_return_object() { return {}; }
  std::suspend_never initial_suspend() noexcept { return {}; }
  std::suspend_never final_suspend() noexcept { return {}; }
  void return_void() {}
  void unhandled_exception() { std::puts("unhandled"); }
}; };

struct throwing {
  bool await_ready() { return false; }
  void await_suspend(std::coroutine_handle<>) { throw std::runtime_error("boom"); }
  void await_resume() { std::puts("never printed"); }
};

task t() {
  try { co_await throwing{}; }
  catch (const std::exception& e) { std::printf("caught in coroutine: %s\n", e.what()); }
}

int main() { t(); }
```

程序输出 `caught in coroutine: boom`，`await_resume` 不会被调用。按字面，这条规则只写在 `void` 的情形下；本机 Clang 23 对返回 `bool` 和 `coroutine_handle` 的 `await_suspend` 抛异常也是同样处理。

### 恢复之后（¶5.2）

¶5.2 `await_ready()` 为 `true`，或者协程被恢复（不是因为 `await_suspend` 抛异常而恢复）时，求值 `await_resume()`，结果就是整个 `co_await` 表达式的结果。

注 2：就求值顺序而言，`co_await` 是不可分割的（[[intro.execution]]）。在 `f(co_await a, g())` 中，`g()` 要么在整个 `co_await a`（包括挂起和恢复）之前求值，要么在它之后，不会在挂起期间求值。

`await_ready()` 返回 `true` 时 `await_suspend` 不会被调用，但它仍然必须能通过编译：¶3.7 的类型要求是编译期检查，与运行时走不走这一分支无关。

## 对称转移

一个协程等待另一个协程时，常见的写法是父协程挂起并恢复子协程，子协程结束时再恢复父协程。如果用返回 `void` 的 `await_suspend`，在函数里直接调用 `h.resume()`，每一次等待都会在栈上多出几层调用，循环一百万次就可能栈溢出。

`await_suspend` 返回句柄时，当前协程先挂起，再由 `co_await` 的展开去恢复返回的协程。实现可以把这次恢复编译成尾调用：当前协程的 resume 函数先返回，再跳到目标协程，栈深度保持不变。没有要转移的目标时，返回 `std::noop_coroutine()`，恢复它什么也不做，控制直接回到调用者。

```cpp run ok
#include <coroutine>
#include <cstdio>
#include <exception>
#include <utility>

struct task {
  struct promise_type {
    std::coroutine_handle<> cont = std::noop_coroutine();
    int value = 0;
    task get_return_object() {
      return task{std::coroutine_handle<promise_type>::from_promise(*this)};
    }
    std::suspend_always initial_suspend() noexcept { return {}; }   // 惰性启动
    struct final_awaiter {
      bool await_ready() noexcept { return false; }
      std::coroutine_handle<>
      await_suspend(std::coroutine_handle<promise_type> h) noexcept {
        return h.promise().cont;     // 结束时转回等待者
      }
      void await_resume() noexcept {}
    };
    final_awaiter final_suspend() noexcept { return {}; }
    void return_value(int v) { value = v; }
    void unhandled_exception() { std::terminate(); }
  };

  std::coroutine_handle<promise_type> h;
  explicit task(std::coroutine_handle<promise_type> h) : h(h) {}
  task(task&& o) noexcept : h(std::exchange(o.h, {})) {}
  ~task() { if (h) h.destroy(); }

  // task 本身就是 awaiter
  bool await_ready() const noexcept { return false; }
  std::coroutine_handle<> await_suspend(std::coroutine_handle<> caller) noexcept {
    h.promise().cont = caller;
    return h;                        // ¶5.1.1：直接恢复子协程
  }
  int await_resume() const noexcept { return h.promise().value; }
};

task leaf(int i) { co_return i; }

task sum(int n) {
  int s = 0;
  for (int i = 0; i < n; ++i)
    s += co_await leaf(1);
  co_return s;
}

int main() {
  task t = sum(1'000'000);
  t.h.resume();
  std::printf("%d\n", t.h.promise().value);   // 1000000
}
```

标准只要求求值 `await_suspend` 再调用 `.resume()`，没有要求尾调用，这属于实现质量。但对称转移的设计目的就是让尾调用成为可能（[[P0913R1]]），主流实现也都这样做。本机 Clang 23 在 `-O0 -fsanitize=address` 下也能跑完这一百万次。

## 可以写在哪里（¶2）

¶2 `co_await` 只能作为潜在求值的表达式，出现在函数体或 lambda 体的复合语句里，并且：

- 不在异常处理器（`catch` 块）里；
- 在声明语句里，以及 `if`、`for` 等语句的初始化语句里，只能出现在初始化器中；
- 不在默认实参里；
- 不在静态或线程存储期的块作用域变量的初始化器里；
- {{c++26}} 不是契约断言谓词中的潜在求值子表达式（[[basic.contract]]）。

满足这些条件的位置叫做函数的**挂起语境**（[[g:suspension-context]]）。

```cpp error
#include <coroutine>
struct task { struct promise_type {
  task get_return_object() { return {}; }
  std::suspend_never initial_suspend() noexcept { return {}; }
  std::suspend_never final_suspend() noexcept { return {}; }
  void return_void() {}
  void unhandled_exception() {}
}; };

task ok() {
  try { co_await std::suspend_never{}; }            // OK：try 块里可以
  catch (...) {}
  int x = (co_await std::suspend_never{}, 1);       // OK：初始化器
  (void)x;
}
task a() { try {} catch (...) { co_await std::suspend_never{}; } }   // error: 在 handler 里
void c(int = (co_await std::suspend_never{}, 1));                    // error: 默认实参
task d() { decltype(co_await std::suspend_never{})* p = nullptr; co_return; }  // error: 未求值
task b() { static int s = (co_await std::suspend_never{}, 1); }      // error: 静态局部变量
```

本机 Clang 23 诊断了前三处错误，但接受了最后一处（静态局部变量的初始化器），这是 Clang 的缺陷。

每条限制都有原因：

- 挂起是运行时动作，放在 `sizeof`、`decltype` 这类不求值的位置没有意义。
- `catch` 块里有一个正在处理的异常，`throw;` 和 `std::current_exception` 都依赖它，而这份状态与线程绑定。协程可能在另一个线程上恢复，挂起会让这些状态难以定义。通常的做法是在 `catch` 里记下信息，离开后再 `co_await`。
- 静态局部变量的初始化保证只执行一次而且线程安全（[[stmt.dcl]]），通常靠一把锁实现。持锁挂起会让其他线程一直阻塞。
- 默认实参在调用方求值，而调用方不一定是协程。
- 契约断言可能不求值，也可能多次求值（[[basic.contract]]），在里面挂起会让控制流取决于契约的求值语义。

## 实现视角

!!! impl "协程帧与 co_await 的编译"
    - Clang、GCC、MSVC 都把协程拆成首次调用的 ramp 函数、resume 函数和 destroy 函数。跨越挂起点存活的局部变量和 awaiter 都放在协程帧里，帧中记录当前挂起点的编号，resume 函数据此跳转。`std::coroutine_handle` 就是指向协程帧的指针，`h.resume()` 是一次间接调用。
    - `await_ready()` 返回 `true` 时不需要保存任何状态。内联之后，等待一个已就绪的 awaiter 和普通函数调用一样便宜。
    - 协程帧通常在堆上分配。如果协程的生命周期严格嵌套在调用者之内，LLVM 可以把帧放在调用者的栈上，省掉堆分配（HALO）。依据是 [[dcl.fct.def.coroutine]] 允许省略协程状态的分配。

## 历史与演进

!!! history
    - 协程先以 Coroutines TS 发布，C++20 通过 [[P0912R5]] 并入标准。
    - 对称转移和 `std::noop_coroutine` 来自 [[P0913R1]]，在并入标准之前加入了 TS。
    - C++26 引入契约后，¶2 增加了不能出现在契约谓词中的限制。

## 常见误解

!!! pitfall "交出句柄之后继续访问 awaiter"
    协程在调用 `await_suspend` 之前已经算作挂起。`await_suspend` 把 `h` 交给另一个线程后，那个线程可能立刻恢复协程，协程可能一直运行到结束并销毁协程帧，awaiter 也随之销毁。此后 `await_suspend` 再访问 `this` 的成员就是 UB。交出句柄应当是 `await_suspend` 里最后一个碰到 awaiter 或协程帧的动作。

!!! pitfall "以为写了 `operator co_await` 就一定会用到"
    promise 只要声明了 `await_transform`，`operator co_await` 就作用在 `await_transform` 的结果上，而不是原来的操作数上。

!!! pitfall "两个 bool 的方向相反"
    `await_ready()` 返回 `true` 表示已就绪、不挂起；`await_suspend` 返回 `true` 表示保持挂起。如果已经把 `h` 交给了别的线程，`await_suspend` 又返回 `false`，两边可能同时恢复同一个协程，这是 UB。

## 思考题

!!! question "思考题 1"
    promise 没有 `await_transform`。`struct X { std::suspend_never operator co_await(); };`，另有非成员 `std::suspend_never operator co_await(X);`。`co_await X{}` 会怎样？

<details markdown="1">
<summary>答案</summary>

非良构，重载决议有歧义。¶3.3 按 [[over.match.oper]] 同时收集成员和非成员候选。实参是 `X` 类型的 prvalue：成员候选的隐式对象形参是 `X&`，没有引用限定符的成员函数允许绑定右值（[[over.match.funcs]]），是恒等转换；非成员候选按值传递，也是恒等转换。两者不分优劣。本机 Clang 23 报告 `use of overloaded operator 'co_await' is ambiguous`。
</details>

!!! question "思考题 2"
    为什么 `co_yield` 和初始、最终挂起产生的 `co_await` 不经过 `await_transform`？如果经过会怎样？

<details markdown="1">
<summary>答案</summary>

它们的操作数本来就是 promise 自己的成员调用，promise 已经完全控制了返回值，再变换一次是多余的。如果经过，`std::generator` 这样用 deleted `await_transform` 禁止 `co_await` 的设计，就会连自己的 `co_yield` 和初始、最终挂起也一起禁掉。
</details>
