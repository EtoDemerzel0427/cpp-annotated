---
title: 产出值（co_yield）
summary: co_yield e 等价于 co_await p.yield_value(e)：它只能出现在挂起语境中，操作数可以是花括号列表，不经过 await_transform，而且可以有值。
status: done
since: c++20
papers: P0912R5
related: expr.await, dcl.fct.def.coroutine, stmt.return.coroutine, expr.assign, expr.const.core, coro.generator
tags: 协程, co_yield
updated: 2026-10-19
---

!!! tldr
    - `co_yield e` 的含义完全由改写给出：等价于 `co_await p.yield_value(e)`，`p` 是当前协程的承诺对象。
    - `co_yield` 的值由 `yield_value` 返回的 awaiter 决定。返回 `std::suspend_always` 时它是 `void`，返回自定义 awaiter 时可以把值从调用者传回协程。
    - 操作数可以是花括号列表，`co_yield {i, i};` 合法，而 `co_await {1, 2}` 不合法。
    - 改写出的 `co_await` 不经过 `await_transform`，所以禁止 `co_await` 的生成器仍然可以 `co_yield`。
    - `co_yield` 只能出现在函数体内、`catch` 块外，优先级与赋值相同。

## `co_yield` 就是一个 `co_await`（¶1）

一个函数体里出现 `co_await`、`co_yield` 或 `co_return`，它就成了**协程**（[[g:coroutine]]）：可以在中途挂起，把控制交回调用者，之后再从挂起点恢复。每个协程有一个**承诺对象**（[[g:promise-object]]），它的类型由返回类型决定，协程通过它与外界交换数据（[[dcl.fct.def.coroutine]]）。

¶1 设 *yield-expression* 的操作数是 `e`，`p` 是指名外围协程承诺对象的 lvalue，那么：

!!! std
    the *yield-expression* is equivalent to the expression `co_await p.yield_value(e)`.

所以 `co_yield` 做两件事。先调用承诺对象的 `yield_value`，通常是把值存起来供调用者读取；再对 `yield_value` 的返回值做 `co_await`（[[expr.await]]）。返回 `std::suspend_always` 时协程挂起，控制回到调用者或恢复者。

`co_await` 表达式的值来自 awaiter 的 `await_resume`。`std::suspend_always::await_resume()` 返回 `void`，所以最常见的 `co_yield x;` 是 `void` 表达式。换成自定义 awaiter，`co_yield` 就有了值，协程可以借此接收调用者传回的数据：

```cpp run title="yield-two-way.cpp" ok
#include <coroutine>
#include <cstdio>
#include <utility>

struct Gen {
    struct promise_type {
        int current = 0;    // 协程 → 调用者
        int received = 0;   // 调用者 → 协程
        Gen get_return_object() {
            return Gen{std::coroutine_handle<promise_type>::from_promise(*this)};
        }
        std::suspend_always initial_suspend() noexcept { return {}; }
        std::suspend_always final_suspend() noexcept { return {}; }
        struct Awaiter {
            promise_type* p;
            bool await_ready() noexcept { return false; }
            void await_suspend(std::coroutine_handle<>) noexcept {}
            int await_resume() noexcept { return p->received; }   // co_yield 的值
        };
        Awaiter yield_value(int v) { current = v; return {this}; }
        void return_void() {}
        void unhandled_exception() {}
    };
    std::coroutine_handle<promise_type> h;
    explicit Gen(std::coroutine_handle<promise_type> h) : h(h) {}
    Gen(Gen&& o) : h(std::exchange(o.h, {})) {}
    ~Gen() { if (h) h.destroy(); }
};

Gen accumulate() {
    int total = 0;
    for (int i = 1; i <= 3; ++i) {
        int got = co_yield i;   // 产出 i；恢复时得到调用者放进来的值
        total += got;
    }
    co_yield total;
}

int main() {
    Gen g = accumulate();
    for (int k = 0; k < 4; ++k) {
        g.h.promise().received = 10 * k;
        g.h.resume();
        std::printf("%d ", g.h.promise().current);   // 输出 1 2 3 60
    }
}
```

## 文法：优先级与花括号列表

```text
yield-expression:
    co_yield assignment-expression
    co_yield braced-init-list
```

*yield-expression* 是 *assignment-expression* 的一种（[[expr.assign]]），与赋值、`throw` 同级。所以 `co_yield a + b` 产出 `a + b`；`co_yield a, b` 是 `(co_yield a), b`；`1 + co_yield 2` 是语法错误，要写成 `1 + (co_yield 2)`。它可以出现在赋值右侧和初始化器里，比如上例的 `int got = co_yield i;`。

操作数可以是花括号列表。`co_yield {i, i};` 改写为 `co_await p.yield_value({i, i})`，花括号列表用来初始化 `yield_value` 的形参（[[dcl.init.list]]）。标准例 1 就用它产出 `pair<int, int>`。`co_await` 的操作数是 *cast-expression*，不能是花括号列表。

## 不经过 `await_transform`

如果承诺类型声明了 `await_transform`，用户写的 `co_await x` 会先变成 `p.await_transform(x)`。但 [[expr.await#3.2]] 把由 *yield-expression* 产生的 `co_await` 排除在外，`co_yield` 改写出的 `co_await p.yield_value(e)` 不会再调用 `await_transform`。

这是为了让承诺类型可以禁止 `co_await` 而不影响 `co_yield`。`std::generator` 的承诺类型就声明了 `void await_transform() = delete;`（[[coro.generator.promise]]）：名字查找总能找到它，而它不接受任何实参，于是生成器里的任何 `co_await x` 都非良构，`co_yield` 照常工作。

反过来，想拦截 `co_yield`，要在 `yield_value` 里做，`await_transform` 管不到。

## 只能出现在挂起语境中

¶1 第一句规定，*yield-expression* 只能出现在函数的**挂起语境**（[[g:suspension-context]]）中。挂起语境由 [[expr.await#2]] 定义：函数体或 lambda 体之内、异常处理器（`catch` 块）之外，并且不在默认实参、静态或线程存储期块变量的初始化器、契约断言的谓词中。

```cpp title="yield-context.cpp" error
#include <coroutine>

auto f(int x = co_yield 5);     // error：默认实参不是挂起语境
int a[] = { co_yield 1 };       // error：不在函数体内
```

```cpp title="yield-in-handler.cpp" error
#include <coroutine>
struct Gen { struct promise_type; };   // 细节从略

Gen g() {
    try { throw 1; }
    catch (...) { co_yield 1; }        // error：catch 块中不能挂起
}
```

`catch` 块执行期间有一个当前正在处理的异常，`throw;` 和 `std::current_exception` 都依赖这个与线程绑定的状态。协程如果在这里挂起，之后又在别的线程上恢复，这个状态就无法维护。

函数体中出现 `co_yield`，这个函数就成了协程，必须满足协程的全部要求：返回类型要有合适的 `promise_type`，不能用普通的 `return`，不能是 `main`。协程也不能是 constexpr 函数，*yield-expression* 不能出现在常量求值中（[[expr.const.core#2.27]]）。

!!! impl "实现视角"
    编译器把协程拆成一个协程帧（通常在堆上分配，能证明生命周期受限时可以省掉这次分配）和若干恢复点。每个 `co_yield` 是一个挂起点：先调用 `yield_value`，再按 awaiter 的 `await_ready`、`await_suspend` 决定是否挂起，并在协程帧里记下这个恢复点的编号。生成器的每次迭代因此只是一次间接跳转，开销与手写状态机相当。

!!! history
    协程先以 Coroutines TS 发布，C++20 由 [[P0912R5]] 并入标准。C++23 加入的 `std::generator`（[[coro.generator]]）建立在 `co_yield` 之上：它的 `yield_value` 只保存被产出对象的地址，因为在挂起期间那个对象一直存活；`co_yield std::ranges::elements_of(r)` 则把另一个范围或生成器的全部元素依次产出。

## 思考题

!!! question "思考题"
    承诺类型 `P` 同时有 `yield_value(int)` 和 `await_transform`。`co_yield 1;` 和用户手写的 `co_await p.yield_value(1);`（假设能在协程里拿到 `p`）完全相同吗？

<details markdown="1">
<summary>答案</summary>

不完全相同。前者是由 *yield-expression* 产生的 `co_await`，按 [[expr.await#3.2]] 不查找 `await_transform`。后者是用户写的 `co_await`，会查找 `await_transform` 并调用 `p.await_transform(p.yield_value(1))`；如果 `await_transform` 不接受 `yield_value` 的返回类型，它还会非良构。所以标准说的等价，指的是按那个 `co_await` 表达式求值，同时保留它由 `co_yield` 产生这一身份。
</details>

## 小结

| 方面 | 规则 |
|---|---|
| 含义 | `co_yield e` ≡ `co_await p.yield_value(e)` |
| 操作数 | *assignment-expression* 或花括号列表 |
| 优先级 | 与赋值同级，`1 + co_yield 2` 要加括号 |
| 出现位置 | 挂起语境：函数体内、`catch` 块外、不在默认实参等处 |
| `await_transform` | 不适用 |
| 值 | 由 awaiter 的 `await_resume` 决定 |
| 常量求值 | 不能出现 |
