---
title: 协程全景
summary: C++20 协程从头到尾：promise / awaiter / handle 三个角色、co_await 的完整展开、编译器如何把协程降级为状态机（ramp / resume / destroy、Clang 的帧布局、HALO）、对称转移为何必要、跨线程恢复、std::generator，以及最常见的生命周期 bug
status: draft
since: c++20
order: 65
papers: P0912R5
related: dcl.fct.def.coroutine, expr.await, expr.yield, stmt.return.coroutine, support.coroutine, coroutine.handle, coro.generator, class.copy.elision
tags: 协程, co_await, 状态机, 对称转移, 生命周期
updated: 2026-10-18
---

C++20 协程常被称为"给库作者的特性"：语言只提供一套**改写协议**，`task`、`generator`、异步 I/O、调度器全都由库实现。这让初学者觉得无从下手——写一个最简单的协程也要先写一个几十行的 promise 类型。本专题把散落在 [[dcl.fct.def.coroutine]]、[[expr.await]]、[[expr.yield]]、[[stmt.return.coroutine]]、[[support.coroutine]] 中的规则串成一条线：

1. 三个角色各自负责什么；
2. 编译器看到 `co_await` 时到底生成了什么；
3. 协程在机器层面长什么样；
4. 为什么需要对称转移；
5. 哪些写法会悬垂。

## 一、一句话模型

> **协程 = 一个可以在 `co_await` 处"暂停并返回"的函数；它的局部变量存放在一块独立的帧里，而不是调用栈上；暂停与恢复的每一步都调用用户提供的钩子。**

C++ 协程是**无栈**的：只有协程函数体本身能挂起，它调用的普通函数不能"代替它"挂起。挂起时控制交还给调用者（或恢复者）——就像函数返回了一样，但帧还在。

## 二、三个角色

| 角色 | 是什么 | 谁提供 | 负责什么 |
|---|---|---|---|
| **promise** | 协程帧内的一个对象，类型由 `std::coroutine_traits<R, Args...>::promise_type` 决定 | 返回类型的作者 | 协程的"生命周期策略"：开始时是否挂起、结果/异常放哪里、结束时做什么、`co_yield` 的含义、怎样构造返回对象 |
| **awaiter** | `co_await e` 中由 `e` 得到的对象，有 `await_ready` / `await_suspend` / `await_resume` | 被等待者的作者 | 一次挂起的"策略"：要不要挂起、挂起后把句柄交给谁、恢复时返回什么 |
| **coroutine_handle** | 指向协程帧的非拥有指针 | 标准库（[[coroutine.handle]]） | `resume()`、`destroy()`、`done()`、`promise()`、`from_promise()`、`address()` |

返回给调用者的对象（`task<T>`、`generator<T>`）通常持有一个 `coroutine_handle`，是协程帧的**所有者**；promise 是帧**内部**的控制器；awaiter 是**每次** `co_await` 的临时协议对象。

### promise 的钩子

协程函数体被改写为（[[dcl.fct.def.coroutine#5]]，略去细节）：

```cpp
{
    promise_type promise(/* 形参副本，若有匹配的构造函数 */);
    /* 返回值 = */ promise.get_return_object();      // 先于 initial_suspend，最多一次
    try {
        co_await promise.initial_suspend();
        /* 用户的函数体：
           co_yield e     →  co_await promise.yield_value(e)
           co_return e;   →  promise.return_value(e); goto final_suspend;
           co_return;     →  promise.return_void();   goto final_suspend;
           流出末尾       →  若有 return_void 则同 co_return; 否则 UB */
    } catch (...) {
        // 只有函数体真正开始之后的异常才到这里
        promise.unhandled_exception();
    }
final_suspend:
    co_await promise.final_suspend();                 // 整个表达式必须 noexcept
}
```

两个开关决定了协程类型的"性格"：

| `initial_suspend` | `final_suspend` | 含义 | 例子 |
|---|---|---|---|
| `suspend_always` | `suspend_always` | 惰性启动；结束后由所有者 `destroy()` | `generator`、惰性 `task` |
| `suspend_never` | `suspend_never` | 立即执行；结束后帧自动销毁，句柄立刻失效 | "发射后不管"（fire-and-forget） |
| `suspend_always` | 返回等待者句柄的 awaiter | 惰性启动；结束时对称转移给等待者 | 可组合的 `task` |

## 三、co_await 的完整展开

[[expr.await#3]] 把 `co_await expr` 分三步变成一个 awaiter `e`：

1. **await_transform**：若 promise 类型有名为 `await_transform` 的成员，`a = promise.await_transform(expr)`，否则 `a = expr`。（`initial_suspend`、`final_suspend`、`yield_value` 产生的隐式 `co_await` 跳过这一步。）这让 promise 可以拦截、禁止或改写协程中的所有 `co_await`——例如只允许等待特定类型，或注入取消检查。
2. **operator co_await**：对 `a` 做重载决议查找 `operator co_await`（成员或非成员）；找到就 `o = operator co_await(a)`，否则 `o = a`。这让一个类型可以"提供"一个独立的 awaiter，而不必自己实现三个函数（标准例子给 `std::chrono::duration` 定义了 `operator co_await`，于是可以写 `co_await 10ms;`）。
3. 若 `o` 是 prvalue，物化为临时对象；`e` 是指代它的左值。

然后（[[expr.await#5]]）：

```cpp
if (!e.await_ready()) {
    /* 协程此刻被认为"已挂起" */
    // 依 await_suspend 的返回类型：
    //   void              : e.await_suspend(h);  然后返回给调用者/恢复者
    //   bool              : if (e.await_suspend(h)) 返回给调用者/恢复者; else 立即恢复本协程
    //   coroutine_handle<Z>: e.await_suspend(h).resume();  —— 对称转移（实现保证为尾调用）
    /* <挂起点> */
}
/* 恢复后（或 await_ready 为真时直接到这里）： */
result = e.await_resume();     // co_await 表达式的值
```

要点：

- `await_ready()` 返回 `true` 时完全不挂起——这是"值已经就绪就不必付出挂起代价"的快速路径；
- 协程在调用 `await_suspend` **之前**就已经被认为是挂起的。因此 `await_suspend` 内可以把 `h` 交给另一个线程，另一个线程可以**立即** `h.resume()`——即使 `await_suspend` 还没返回；
- `await_suspend` 抛出异常时，协程被恢复并立即重抛；
- `co_await` 只能出现在函数体的复合语句中（不能在默认实参、静态局部变量的初始化器、异常处理器 `catch` 块中、契约谓词中，[[expr.await#2]]）。

### 一个跨线程恢复的 awaiter

```cpp run title="resume-on-thread.cpp" ok
#include <coroutine>
#include <cstdio>
#include <exception>
#include <thread>

struct fire_and_forget {
    struct promise_type {
        fire_and_forget get_return_object() { return {}; }
        std::suspend_never initial_suspend() noexcept { return {}; }
        std::suspend_never final_suspend() noexcept { return {}; }
        void return_void() { }
        void unhandled_exception() { std::terminate(); }
    };
};

struct resume_on_new_thread {
    std::jthread* out;
    bool await_ready() const noexcept { return false; }
    void await_suspend(std::coroutine_handle<> h) {
        std::jthread* o = out;                  // 先把需要的成员读到局部变量：
        *o = std::jthread([h] { h.resume(); }); // 新线程一启动，协程（连同本 awaiter）可能已运行结束并被销毁
    }
    void await_resume() const noexcept { }
};

fire_and_forget hop(std::jthread& t) {
    auto before = std::this_thread::get_id();
    co_await resume_on_new_thread{&t};
    auto after = std::this_thread::get_id();
    std::printf("switched thread: %s\n", before != after ? "yes" : "no");
}

int main() {
    std::jthread t;
    hop(t);
}   // t 在此 join
```

注释里那一行是真实的陷阱：awaiter 是协程帧里的临时对象。新线程一旦恢复协程，协程可能在 `await_suspend` 返回**之前**就运行到结束、销毁帧——此后再读 `this->out` 就是读已销毁的对象。写成 `*out = std::jthread(...)` 时，C++17 规定赋值的右操作数先于左操作数求值，于是 `out` 恰好是在线程启动**之后**才被读取的。规则：**`await_suspend` 在把句柄交出去之后，不能再访问 awaiter 自身或协程帧中的任何东西。**

## 四、编译器怎样降级协程

### 拆成三个函数

以 Clang 为例（GCC 的方案类似），一个协程 `fib(int)` 被拆成：

- **ramp 函数**：就是外部可见的 `fib(int)`。它分配帧、把形参复制进帧、构造 promise、调用 `get_return_object` 和 `initial_suspend`；在第一次挂起时返回；
- **`fib(int) (.resume)`**：从帧中保存的挂起点继续执行；
- **`fib(int) (.destroy)`**：从挂起点出发销毁活跃的局部变量、promise、形参副本，然后释放帧。

在本机用 `clang++ -O1 -c` 编译 [[dcl.fct.def.coroutine]] 中的 generator 例子后，`nm | c++filt` 显示三个符号：`fib(int)`、`fib(int) (.resume)`、`fib(int) (.destroy)`。

resume 函数的主体是一个 `switch`：

```cpp
// 概念上的降级结果（伪代码，不是标准规定的形式）
struct fib_frame {
    void (*resume)(fib_frame*);      // 偏移 0
    void (*destroy)(fib_frame*);     // 偏移 8
    generator<int>::promise_type promise;
    int n, a, b, i;                  // 形参副本与跨挂起点存活的局部变量
    unsigned char index;             // 当前挂起点编号
};

void fib_resume(fib_frame* f) {
    switch (f->index) {
    case 0: goto initial_resumed;    // 从初始挂起点恢复
    case 1: goto after_yield;        // 从 co_yield 恢复
    }
initial_resumed:
    f->a = 0; f->b = 1;
    for (f->i = 0; f->i < f->n; ++f->i) {
        f->promise.yield_value(f->a);   // 返回 suspend_always
        f->index = 1;
        return;                          // 挂起 = 返回到恢复者
after_yield:
        f->a = std::exchange(f->b, f->a + f->b);
    }
    f->promise.return_void();
    f->resume = nullptr;                 // 标记 done()：Clang 在最终挂起点把 resume 指针置空
    f->index = 2;
    return;
}
```

### 帧布局（Clang）

LLVM 的协程帧总是以两个函数指针开头：**resume 函数**、**destroy 函数**，接着是 **promise 对象**，然后是形参副本、跨挂起点存活的局部变量与挂起点索引。于是：

- `coroutine_handle<>::resume()` ≈ 调用 `((void(**)(void*))addr)[0](addr)`；`destroy()` 调用第二个；
- `done()` ≈ "resume 指针是否为空"（最终挂起点时置空）；
- `from_promise(p)` / `promise()` 通过固定偏移在帧地址与 promise 地址之间换算——这就是为什么 `coroutine_handle<P>` 需要知道 `P`，而 `coroutine_handle<>` 不需要。

本机 `-O0` 下 `fib` 的帧为 48 字节：偏移 0 与 8 是两个函数指针，偏移 16 是 promise（一个 `int`），之后是形参副本与局部变量，挂起点索引是一个 2 位整数，存在偏移 40 处。优化级别不同，帧的大小与布局也不同（只有跨挂起点存活的变量才需要进帧）。

### HALO：消除堆分配

[[dcl.fct.def.coroutine#9]] 说实现"**可能**需要"分配协程状态。若编译器能证明帧的生命周期严格嵌套在调用者之内（协程在调用者中创建、使用、销毁，句柄不逃逸），就可以把帧放进调用者的栈帧，消除 `operator new`/`delete`。这称为 **HALO**（Heap Allocation eLision Optimization）。

本机实测：上面的 generator 例子在 `-O2` 下，`main` 中不再有任何 `operator new` 调用——帧被内联进了 `main`。但 HALO 很脆弱：句柄一旦被存进容器、跨函数返回、或协程定义不可见（在另一个 TU），优化就失效。需要确定性内存行为的代码应在 promise 中提供 `operator new`（见 [[dcl.fct.def.coroutine]] 中的 arena 例子）。

## 五、对称转移

考虑一个惰性 `task`：`co_await child` 时，在 `await_suspend` 里启动 child；child 结束时，在它的 `final_suspend` 里恢复等待者。朴素写法是在 `await_suspend` 中直接调用 `resume()`：

```cpp run title="asymmetric-overflow.cpp"
#include <coroutine>
#include <cstdio>
#include <utility>

struct task {
    struct promise_type {
        std::coroutine_handle<> cont;
        task get_return_object() { return task{std::coroutine_handle<promise_type>::from_promise(*this)}; }
        std::suspend_always initial_suspend() noexcept { return {}; }
        auto final_suspend() noexcept {
            struct A {
                bool await_ready() noexcept { return false; }
                void await_suspend(std::coroutine_handle<promise_type> h) noexcept {
                    if (h.promise().cont) h.promise().cont.resume();   // 在 child 的栈帧里恢复 parent
                }
                void await_resume() noexcept { }
            };
            return A{};
        }
        void return_void() { }
        void unhandled_exception() { }
    };
    std::coroutine_handle<promise_type> h;
    explicit task(std::coroutine_handle<promise_type> h) : h(h) { }
    task(task&& o) noexcept : h(std::exchange(o.h, {})) { }
    ~task() { if (h) h.destroy(); }
    bool await_ready() { return false; }
    void await_suspend(std::coroutine_handle<> c) { h.promise().cont = c; h.resume(); }  // 在 parent 的栈帧里启动 child
    void await_resume() { }
};

task leaf() { co_return; }
task loop(int n) { for (int i = 0; i < n; ++i) co_await leaf(); }

int main() {
    auto t = loop(1000000);
    t.h.resume();
    std::puts("done");
}
```

这个程序在本机 `-O0` 下因**栈溢出**崩溃（退出码 139）。原因：每次循环，`loop` 的 resume 调用 `leaf` 的 resume（在 `await_suspend` 里），`leaf` 结束时又在 `final_suspend` 的 `await_suspend` 里调用 `loop` 的 resume——这些调用从不返回，一层压一层，一百万次循环就是几百万层栈帧。

**对称转移**（symmetric transfer）的解决方法：`await_suspend` 不自己调用 `resume()`，而是**返回**要恢复的句柄；[[expr.await#5]] ¶5.1.1 规定此时实现对返回的句柄调用 `resume()`，而实现会把这次调用编译为**尾调用**（Clang 在 LLVM IR 中使用 `musttail`，即使在 `-O0` 下也是如此），当前协程的 resume 函数的栈帧先被弹出。只需改两处：

```cpp
// final_suspend 的 awaiter：
std::coroutine_handle<> await_suspend(std::coroutine_handle<promise_type> h) noexcept {
    return h.promise().cont ? h.promise().cont : std::noop_coroutine();
}
// task 的 awaiter：
std::coroutine_handle<> await_suspend(std::coroutine_handle<> c) { h.promise().cont = c; return h; }
```

改后同样的循环在 `-O0` 下正常输出 `done`。`std::noop_coroutine()`（[[coroutine.noop]]）返回一个"恢复它什么也不做"的句柄，用于"没有可转移的对象，就返回给调用者"的情形。

## 六、std::generator {{c++23}}

C++23 标准库提供了 `std::generator<Ref, V = void, Allocator = void>`（[[coro.generator]]），它是一个 `std::ranges::view`：

```cpp title="std-generator.cpp" ok
#include <generator>
#include <print>
#include <ranges>

std::generator<int> iota(int n) {
    for (int i = 0; i < n; ++i) co_yield i;
}

std::generator<int> twice(int n) {
    co_yield std::ranges::elements_of(iota(n));   // 递归委托给另一个 generator，无需逐个转发
    co_yield std::ranges::elements_of(iota(n));
}

int main() {
    for (int x : twice(3) | std::views::transform([](int v) { return v * 10; }))
        std::print("{} ", x);                       // 0 10 20 0 10 20
}
```

截至写作时，本机 Clang 23 附带的 libc++ 尚未提供 `<generator>` 头文件（libstdc++ 已经实现），所以这个例子未在本地运行。`elements_of` 的递归委托在实现上使用对称转移，嵌套任意深都不会增加栈深度。

## 七、常见的生命周期 bug

协程的大部分 bug 都是生命周期 bug。原因是：**协程的调用在第一次挂起时就"返回"了，但它的函数体还会在之后继续运行**——调用表达式中的一切临时量、调用者的局部变量，在协程恢复时可能都已不在。

| # | 写法 | 问题 | 修正 |
|---|---|---|---|
| 1 | `task f(const std::string& s)` 被 `f("literal")` 调用 | 临时 `string` 在完整表达式结束时销毁；帧中只有引用（[[dcl.fct.def.coroutine#13]]） | 按值接收：`task f(std::string s)` |
| 2 | `task f(std::string_view sv)` | `string_view` 被复制进帧，但它指向的字符没有 | 同上 |
| 3 | `[&x]() -> task { co_await …; use(x); }()` | 闭包对象是临时量，`*this` 不被复制进帧；捕获随闭包一起消失 | 不要让 lambda 协程捕获；或用 C++23 `[x](this auto self) -> task { … }` 按值接收闭包 |
| 4 | `task C::run() { co_await …; this->m; }` | `*this` 不复制；对象被销毁后恢复 | 用 `shared_from_this` 或保证对象寿命长于协程 |
| 5 | `final_suspend` 返回 `suspend_never`，返回对象仍然 `h.destroy()` | 帧已自动销毁，二次销毁 | 两种所有权模型二选一 |
| 6 | `await_suspend` 把 `h` 交给其他线程后访问 `this` | 协程可能已在另一个线程结束 | 交出句柄后不再访问 awaiter 或帧（见第三节） |
| 7 | `task<int> f() { if (c) co_return 1; }` | 无 `return_void` 时流出末尾是 UB（[[stmt.return.coroutine#3]]） | `-Werror=return-type` |
| 8 | 在 `await_suspend` 中直接 `resume()` 另一个协程 | 无界栈增长（第五节） | 对称转移：返回句柄 |
| 9 | 在协程中持有 `std::lock_guard` 跨越 `co_await` | 可能在另一个线程上解锁互斥量（UB） | 在 `co_await` 之前释放锁 |

例子 1 的完整演示与 AddressSanitizer 报告见 [[dcl.fct.def.coroutine]]。

## 八、设计清单

写一个协程类型时，依次回答：

1. **谁拥有帧？**（返回对象持有句柄并在析构中 `destroy()`，还是协程结束时自动销毁？）→ 决定 `final_suspend`。
2. **调用时是否立即运行？** → 决定 `initial_suspend`。惰性启动更容易组合（结构化并发），也避免"在返回对象构造好之前就运行完"的竞态。
3. **结果与异常放在哪里？** → `return_value`/`return_void`、`unhandled_exception`。
4. **被 `co_await` 时怎样衔接？** → 让返回类型成为 awaiter，用对称转移启动与回到等待者。
5. **允许在协程中等待什么？** → `await_transform`。
6. **内存从哪里来？** → promise 的 `operator new`（可以带形参，如分配器）与 `get_return_object_on_allocation_failure`。

## 思考题

!!! question "思考题 1"
    `co_await std::suspend_always{};` 和 `co_await std::suspend_never{};` 的展开分别是什么？哪一个会产生挂起点？

<details markdown="1">
<summary>答案</summary>

`suspend_always::await_ready()` 返回 `false`，于是调用 `await_suspend(h)`（返回 `void`）并返回给调用者/恢复者——产生挂起点；恢复后调用 `await_resume()`（无值）。`suspend_never::await_ready()` 返回 `true`，直接调用 `await_resume()`，不挂起。二者都是 [[support.coroutine]] 中定义的平凡 awaiter，所有成员都是 `constexpr noexcept` 的——所以可以作为 `final_suspend` 的返回值（[[dcl.fct.def.coroutine#15]]）。
</details>

!!! question "思考题 2"
    为什么说"协程在调用 `await_suspend` 之前就被认为已挂起"是一个重要的设计决定？如果反过来（`await_suspend` 返回后才算挂起）会怎样？

<details markdown="1">
<summary>答案</summary>

`await_suspend` 的典型工作是把句柄注册到某处（I/O 完成队列、线程池、另一个协程的 continuation）。一旦注册，另一个线程可能立即调用 `h.resume()`。[[dcl.fct.def.coroutine#8]] 规定恢复未挂起的协程是 UB；若协程要到 `await_suspend` 返回后才算挂起，那么在 `await_suspend` 执行期间的这次恢复就是 UB，任何多线程 awaiter 都必须额外加锁同步。规定"先挂起，再调用 `await_suspend`"消除了这个竞态——代价是 `await_suspend` 在交出句柄后不能再碰协程帧（第三节的陷阱）。
</details>

!!! question "思考题 3"
    `std::coroutine_handle<>` 不知道 promise 类型，为什么还能 `resume()` 和 `destroy()`？为什么不能 `promise()`？

<details markdown="1">
<summary>答案</summary>

实现约定帧首是 resume 与 destroy 两个函数指针（第四节），`resume()`/`destroy()` 只需要帧地址就能通过这两个指针分派到具体协程的代码——这是一种手写的类型擦除。`promise()` 需要知道 promise 对象在帧中的偏移和类型，偏移取决于 promise 的对齐与大小，所以只有 `coroutine_handle<P>` 提供它。
</details>

## 小结

!!! summary
    | 主题 | 要点 |
    |---|---|
    | 本质 | 无栈协程；函数体被改写为调用 promise 钩子的"替换体" |
    | 三个角色 | promise（生命周期策略）、awaiter（单次挂起策略）、handle（非拥有的帧指针） |
    | `co_await` | `await_transform` → `operator co_await` → `await_ready` / `await_suspend` / `await_resume` |
    | `await_suspend` 返回 | `void` 挂起；`bool` 为假则不挂起；句柄则对称转移（尾调用） |
    | 降级 | ramp + resume + destroy 三个函数；switch 状态机；帧首两个函数指针 + promise |
    | 分配 | promise 的 `operator new` 优先；HALO 可消除堆分配，但不可依赖 |
    | 对称转移 | 避免 resume 互相嵌套导致的栈溢出；`noop_coroutine()` 作为"回到调用者" |
    | 生命周期 | 引用/借用形参、lambda 捕获、`this`、交出句柄后的 awaiter 都可能悬垂 |
    | 标准库 | `std::generator`（C++23）；`std::coroutine_handle`、`suspend_always/never`、`noop_coroutine` |
