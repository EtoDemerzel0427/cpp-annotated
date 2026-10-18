---
title: 产出值（co_yield）
summary: "co_yield e 等价于 co_await p.yield_value(e)：只能出现在挂起语境中；操作数可以是花括号初始化列表；不经过 await_transform；它是表达式，有值；在文法中处于赋值表达式这一级"
status: done
since: c++20
papers: P0912R5
related: expr.await, dcl.fct.def.coroutine, stmt.return.coroutine, expr.assign, expr.const.core, coro.generator
tags: 协程, co_yield
updated: 2026-10-18
---

`co_yield` 是 C++20 协程的三个关键字之一（另两个是 `co_await`、`co_return`）。从语言层面看，它几乎没有自己的语义：标准用一句话把它改写为一个 `co_await` 表达式。所以要理解 `co_yield`，关键在于理解 `co_await`（[[expr.await]]）和协程的承诺对象（promise object，[[dcl.fct.def.coroutine]]）。

本节只有一段，但其中有好几处细节值得注意：它能出现在哪里，操作数可以是什么，它为什么能有值，以及它和 `co_await` 的一处差别。

## 文法

```text
yield-expression:
    co_yield assignment-expression
    co_yield braced-init-list
```

*yield-expression* 出现在 [[expr.assign]] 的文法中，与 *throw-expression*、*conditional-expression* 并列，是 *assignment-expression* 的一种。由此推出两点：

- `co_yield` 的优先级很低，与赋值、`throw` 同级：`co_yield a + b` 产出 `a + b`；`co_yield a, b` 是 `(co_yield a), b`；
- 它不能直接作为 `+`、`*` 等运算符的操作数：`1 + co_yield 2` 是语法错误，要写 `1 + (co_yield 2)`。但它可以出现在赋值右边或初始化器中：`int got = co_yield v;`。

## 改写规则（¶1）

[[g:yield-expression]] 的语义完全由改写给出：

!!! std
    the yield-expression is equivalent to the expression co_await p.yield_value(e).

    *yield-expression* 等价于表达式 `co_await p.yield_value(e)`。

其中 `e` 是操作数，`p` 是指名外围协程承诺对象的 lvalue。换句话说，`co_yield` 做两件事：

1. 把值交给承诺对象的 `yield_value` 成员函数（通常存起来供调用者读取）；
2. 对 `yield_value` 的返回值做 `co_await`。这个返回值通常是 `std::suspend_always`，于是协程挂起，控制回到调用者或恢复者。

`yield_value` 的返回类型决定了是否挂起，以及恢复后 `co_yield` 表达式的值是什么（由 awaiter 的 `await_resume` 给出）。`std::suspend_always::await_resume()` 返回 `void`，所以最常见的 `co_yield x;` 是一个 `void` 表达式；但如果 promise 返回自定义的 awaiter，`co_yield` 就可以有值，从而实现双向通信：

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
        int got = co_yield i;   // 产出 i，恢复时得到调用者塞进来的值
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

### 花括号初始化列表

操作数可以是 *braced-init-list*：`co_yield {i, i};` 被改写为 `co_await p.yield_value({i, i})`，花括号列表作为函数实参去初始化 `yield_value` 的参数（[[dcl.init.list]]）。标准的例 1 正是用 `co_yield {i,i}` 产出 `pair<int,int>`。这是 `co_yield` 比普通表达式方便的地方，`co_await {1, 2}` 就不合法（*await-expression* 的操作数是 *cast-expression*）。

### 不经过 `await_transform`

求值 `co_await expr` 时，若承诺类型声明了 `await_transform`，会先把操作数变成 `p.await_transform(expr)`（[[expr.await#3]]）。但 [[expr.await]] ¶3.2 明确排除了由 *yield-expression* 隐式产生的 *await-expression*：`co_yield` 改写出的 `co_await p.yield_value(e)` **不会**再调用 `await_transform`。

这是有意为之。`await_transform` 常被用来禁止协程内部随意 `co_await`，而 `co_yield` 必须照常工作。例如 `std::generator` 的承诺类型声明了一个被删除的无参 `void await_transform() = delete;`（[[coro.generator.promise]]）。由于查找总能找到这个名字，生成器里的任何 `co_await x` 都会因无法调用 `p.await_transform(x)` 而非良构。给上例的 promise 加上 `void await_transform(int) = delete;` 之后，`co_yield` 仍能编译。

## 只能出现在挂起语境中

¶1 第一句规定，*yield-expression* 只能出现在函数的**挂起语境**（suspension context）中。挂起语境由 [[expr.await#2]] 定义：在函数体或 lambda 体的复合语句之内、异常处理器（`catch` 块）之外，并且不在默认实参、静态/线程存储期块变量的初始化器、契约断言的谓词中。标准例子给出了两个错误：

```cpp title="yield-context.cpp" error
#include <coroutine>

auto f(int x = co_yield 5);     // error: 默认实参不是挂起语境
int a[] = { co_yield 1 };       // error: 不在函数体内
```

此外，函数体中出现 `co_yield` 会使该函数成为协程（[[dcl.fct.def.coroutine]]），于是它必须满足协程的所有要求（返回类型有合适的 `promise_type`、不能是 `constexpr`/`consteval` 函数、不能是 `main`、不能用普通 `return` 等）。

```cpp title="yield-in-handler.cpp" error
#include <coroutine>
struct Gen { struct promise_type; };   // 细节从略

Gen g() {
    try { throw 1; }
    catch (...) { co_yield 1; }        // error: catch 块中不能挂起
}
```

不能在 `catch` 中挂起，是因为处理器执行期间存在一个当前正被处理的异常，它的状态与线程绑定（`std::current_exception`、`throw;`）。如果协程在这里挂起，之后又在另一个线程上恢复，异常处理的状态就无法正确维护。

## 常量求值

*yield-expression* 永远不能出现在常量表达式的求值中（[[expr.const.core]] ¶2.27），这与协程本身不能是 `constexpr` 函数一致。

!!! impl "实现视角"
    编译器把协程拆成一个协程帧（通常在堆上分配，可以被优化省略，即 HALO）和若干个恢复点。每个 `co_yield` 都是一个挂起点：它先调用 `yield_value`，再按 awaiter 的 `await_ready`/`await_suspend` 决定是否挂起，并把标识这个恢复点的状态编号写入协程帧。因此生成器的每次迭代只是一次间接跳转，开销与手写状态机相当。

## 历史与演进

!!! history
    - 协程最初作为 Coroutines TS 发布，C++20 由 [[P0912R5]] 合并进标准，`co_yield` 随之进入。
    - C++23 加入了标准生成器 `std::generator`（[[coro.generator]]），它正是基于 `co_yield` 构建的。其承诺类型的 `yield_value` 只保存被产出对象的地址（被产出的对象在挂起期间一直存活，无需复制）；当产出类型是右值引用而 `co_yield` 的是左值时，另有一个重载先复制一份；`co_yield std::ranges::elements_of(r)` 则用于递归地产出另一个范围或生成器的全部元素（[[coro.generator.promise]]）。

## 陷阱

!!! pitfall "`co_yield a, b` 产出 `b`？"
    不，它是 `(co_yield a), b`：产出 `a`，然后求值并丢弃 `b`。

!!! pitfall "以为 `co_yield` 的结果总是 `void`"
    它的值由 `yield_value` 返回的 awaiter 的 `await_resume` 决定，可以是任意类型。

!!! pitfall "用 `await_transform` 拦截 `co_yield`"
    `co_yield` 改写出的 `co_await` 不经过 `await_transform`；要拦截，就在 `yield_value` 里做。

## 思考题

!!! question "思考题"
    设协程的承诺类型 `P` 同时有 `yield_value(int)` 和 `await_transform(int)`。`co_yield 1;` 与 `co_await p.yield_value(1);`（假设能在协程里拿到 `p`）是否完全相同？

<details markdown="1">
<summary>答案</summary>

不完全相同。前者是由 *yield-expression* 隐式产生的 *await-expression*，[[expr.await]] ¶3.2 规定不查找 `await_transform`；后者是用户写的 `co_await`，会查找并调用 `p.await_transform(p.yield_value(1))`（若 `await_transform` 接受 `yield_value` 的返回类型）。标准所说的等价于 `co_await p.yield_value(e)`，应理解为按该 *await-expression* 求值，但这个表达式带着由 yield 产生的身份。
</details>

## 小结

| 方面 | 规则 |
|---|---|
| 改写 | `co_yield e` ≡ `co_await p.yield_value(e)` |
| 操作数 | *assignment-expression* 或 *braced-init-list* |
| 优先级 | 与赋值同级；`1 + co_yield 2` 需加括号 |
| 出现位置 | 只在挂起语境：函数体内、`catch` 块外、非默认实参等 |
| `await_transform` | 不适用 |
| 值 | 由 awaiter 的 `await_resume` 决定 |
| 常量求值 | 永远不是常量表达式 |
