---
title: 协程全景
summary: C++20 协程的完整机制：promise、awaiter、句柄三个角色，co_await 怎样展开，编译器怎样把协程变成状态机，为什么需要对称转移，以及最常见的生命周期错误。
status: draft
since: c++20
order: 65
papers: P0912R5, P2502R2
related: dcl.fct.def.coroutine, expr.await, expr.yield, stmt.return.coroutine, support.coroutine, coroutine.handle, coro.generator, class.copy.elision, topics/dangling-references
tags: 协程, co_await, 状态机, 对称转移, 生命周期
updated: 2026-10-19
---

!!! tldr
    - 协程是能在 `co_await` 处挂起、之后再恢复的函数。C++ 的协程是无栈的：局部变量存放在单独分配的协程状态里，只有协程体本身能挂起。
    - 语言只规定一套改写规则，挂起和恢复的每一步都调用用户提供的钩子：promise 决定整个协程的策略，awaiter 决定一次挂起的策略，`coroutine_handle` 用来恢复和销毁协程。
    - `co_await e` 先调用 `await_ready`，不就绪才挂起并调用 `await_suspend(h)`，恢复后 `await_resume()` 的结果就是表达式的值。协程在调用 `await_suspend` 之前就已经算作挂起。
    - `await_suspend` 返回一个句柄时会接着恢复那个协程（对称转移），实现把它编译成尾调用，协程之间互相恢复不会让栈无限增长。
    - 协程的调用在第一次挂起时就返回了，函数体却在之后继续运行。引用形参、lambda 捕获、`this` 都可能在恢复时已经失效。

## 协程是什么

一个函数的函数体里只要出现 `co_await`、`co_yield` 或 `co_return`，它就是**协程**（[[g:coroutine|coroutine]]，[[dcl.fct.def.coroutine#1]]）。从调用者看它和普通函数没有区别；区别在于它可以在 `co_await` 处暂停，把控制交还给调用者，以后再从暂停处接着运行。[[dcl.fct.def.coroutine]] 的开头有一个最小的 `generator` 例子：`fib` 每次 `co_yield` 都挂起，`main` 每调用一次 `next()` 它就算出下一项。

协程能暂停，是因为它的局部变量和形参副本不放在调用栈上，而放在单独分配的**协程状态**（[[g:coroutine-state|coroutine state]]，俗称协程帧）里。挂起相当于函数返回，但协程状态还在，下次恢复时接着用。

C++ 的协程是**无栈**的：只有协程体自己能挂起。协程调用的普通函数不能代替它挂起，想在被调用的函数里挂起，那个函数也必须是协程，并且由调用者 `co_await` 它。

标准库没有提供 `task` 之类的现成协程类型（`std::generator` 是唯一的例外），语言规定的只是一套改写协议。返回类型的作者通过下面三个角色告诉编译器，挂起、恢复、返回值各该怎么处理。

## 三个角色

| 角色 | 是什么 | 由谁提供 | 负责什么 |
|---|---|---|---|
| promise | 协程状态里的一个对象，类型是 `std::coroutine_traits<R, Args...>::promise_type`，默认就是 `R::promise_type` | 返回类型 `R` 的作者 | 整个协程的策略：开始时是否挂起、结果和异常放在哪里、结束时做什么、`co_yield` 的含义、怎样构造返回给调用者的对象 |
| awaiter | `co_await e` 中由 `e` 得到的对象，有 `await_ready`、`await_suspend`、`await_resume` 三个成员 | 被等待类型的作者 | 一次挂起的策略：要不要挂起、挂起后把句柄交给谁、恢复后返回什么 |
| `coroutine_handle` | 指向协程状态的非拥有指针 | 标准库（[[coroutine.handle]]） | `resume()`、`destroy()`、`done()`、`promise()`、`from_promise()` |

[[g:promise-type|promise 类型]]的对象叫 **promise 对象**，它住在协程状态内部，是协程的控制器。返回给调用者的对象（`task<T>`、`generator<T>`）通常持有一个 `coroutine_handle`，负责在析构时销毁协程状态。awaiter 则是每次 `co_await` 时才出现的临时对象。

### promise 的钩子

编译器把协程的函数体替换成下面的形式（[[dcl.fct.def.coroutine#5]]，略去细节）：

```cpp
{
    promise_type promise(/* 形参副本，如果有匹配的构造函数 */);
    /* 返回给调用者的对象 = */ promise.get_return_object();   // 在 initial_suspend 之前，只调用一次
    try {
        co_await promise.initial_suspend();
        /* 原来的函数体，其中：
           co_yield e    →  co_await promise.yield_value(e)
           co_return e;  →  promise.return_value(e); goto final_suspend;
           co_return;    →  promise.return_void();   goto final_suspend;
           流出末尾      →  有 return_void 时同 co_return;，否则是 UB */
    } catch (...) {
        if (!initial_await_resume_called) throw;   // 函数体还没开始，异常直接抛给调用者
        promise.unhandled_exception();
    }
final_suspend:
    co_await promise.final_suspend();              // 这个表达式不得抛出异常
}
```

`get_return_object` 的调用顺序见 [[dcl.fct.def.coroutine#7]]，流出末尾的规则见 [[stmt.return.coroutine#3]]，`final_suspend` 不得抛出见 [[dcl.fct.def.coroutine#15]]。

`initial_suspend` 和 `final_suspend` 的返回值决定了协程类型的基本行为：

| `initial_suspend` | `final_suspend` | 行为 | 例子 |
|---|---|---|---|
| `suspend_always` | `suspend_always` | 创建后先挂起，等调用者恢复；结束后停在最终挂起点，由所有者 `destroy()` | `generator`、惰性 `task` |
| `suspend_never` | `suspend_never` | 立即执行；结束时协程状态自动销毁，句柄随即失效 | 发出后不再管的协程（fire-and-forget） |
| `suspend_always` | 返回等待者句柄的 awaiter | 惰性启动；结束时转去恢复等待它的协程 | 可以组合的 `task`（见下文对称转移） |

## `co_await` 怎样展开

### 从操作数得到 awaiter

[[expr.await#3]] 分三步把 `co_await expr` 的操作数变成 awaiter `e`：

1. 如果 promise 类型有名为 `await_transform` 的成员，`a = promise.await_transform(expr)`，否则 `a = expr`。`initial_suspend`、`final_suspend`、`yield_value` 产生的隐式 `co_await` 跳过这一步。promise 借此可以拦截协程里所有的 `co_await`，例如只允许等待特定类型，或者插入取消检查。
2. 对 `a` 做重载决议，查找 `operator co_await`（成员或非成员）。找到就 `o = operator co_await(a)`，否则 `o = a`。这样一个类型可以另外提供 awaiter，而不必自己实现三个成员函数。标准的例子给 `std::chrono::duration` 定义了 `operator co_await`，于是可以写 `co_await 10ms;`。
3. `o` 是 prvalue 时实质化为临时对象，`e` 是指代它的左值。

### 挂起与恢复

然后按 [[expr.await#5]] 求值：

```cpp
if (!e.await_ready()) {
    // 从这里起协程就算作已挂起
    // 按 await_suspend 的返回类型：
    //   void                : e.await_suspend(h); 然后返回给调用者或恢复者
    //   bool                : 返回 true 就返回给调用者或恢复者；返回 false 就立即恢复本协程
    //   coroutine_handle<Z> : e.await_suspend(h).resume();   对称转移，见下文
    // <挂起点>
}
// 恢复之后，或者 await_ready 为 true 时直接到这里：
result = e.await_resume();   // co_await 表达式的值
```

`h` 是指向当前协程的 `coroutine_handle<P>`。调用 `h.resume()` 的那次求值叫做**恢复者**（[[g:resumer|resumer]]）。有几点要注意：

- `await_ready()` 返回 `true` 时完全不挂起。结果已经就绪时，这条快速路径省掉了挂起的开销。
- 协程在调用 `await_suspend` 之前就算作已挂起。所以 `await_suspend` 可以把 `h` 交给另一个线程，那个线程可以立即 `h.resume()`，哪怕 `await_suspend` 还没返回。如果反过来，要等 `await_suspend` 返回才算挂起，这次恢复就会命中"恢复一个没有挂起的协程"的 UB（[[dcl.fct.def.coroutine#8]]）。
- `await_suspend` 抛出异常时，协程被恢复，然后立即重新抛出这个异常。
- `co_await` 只能出现在函数体内，并且不能出现在 `catch` 块、默认实参、静态或线程局部变量的初始化器以及契约断言的谓词中（[[expr.await#2]]）。

### 在另一个线程上恢复

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
        std::jthread* o = out;                  // 先把成员读到局部变量
        *o = std::jthread([h] { h.resume(); }); // 新线程启动后，本 awaiter 可能已被销毁
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
}   // t 在这里 join
```

`await_suspend` 里先把 `out` 读到局部变量，是为了避开一个真实的错误。awaiter 是协程状态里的临时对象。新线程一旦恢复协程，协程可能在 `await_suspend` 返回之前就运行到结束，协程状态随之销毁，这时再读 `this->out` 就是读已经销毁的对象。

如果直接写 `*out = std::jthread(...)`，就会出这个问题：C++17 起赋值的右操作数先于左操作数求值，`out` 恰好在线程启动之后才被读取。所以 `await_suspend` 把句柄交出去之后，不能再访问 awaiter 自身或协程状态中的任何东西。

## 编译器怎样实现协程

标准只规定了行为，下面是 Clang 的实际做法，GCC 大体相同。了解它有助于理解句柄的接口和协程的开销。

### 拆成三个函数

Clang 把一个协程 `fib(int)` 拆成三个函数。用 `clang++ -O1 -c` 编译 [[dcl.fct.def.coroutine]] 中的 generator 例子，`nm | c++filt` 能看到这三个符号：

- `fib(int)`，也叫 ramp 函数：分配协程状态，复制形参，构造 promise，调用 `get_return_object` 和 `initial_suspend`，在第一次挂起时返回；
- `fib(int) (.resume)`：从保存的挂起点继续执行；
- `fib(int) (.destroy)`：销毁当前挂起点上还活着的局部变量、promise 和形参副本，然后释放协程状态。

resume 函数的主体是一个 `switch`，按挂起点编号跳回上次停下的位置：

```cpp
// 概念上的结果（伪代码，不是标准规定的形式）
struct fib_frame {
    void (*resume)(fib_frame*);     // 偏移 0
    void (*destroy)(fib_frame*);    // 偏移 8
    generator<int>::promise_type promise;
    int n, a, b, i;                 // 形参副本，以及跨挂起点存活的局部变量
    unsigned char index;            // 当前挂起点的编号
};

void fib_resume(fib_frame* f) {
    switch (f->index) {
    case 0: goto initial_resumed;   // 从初始挂起点恢复
    case 1: goto after_yield;       // 从 co_yield 恢复
    }
initial_resumed:
    f->a = 0; f->b = 1;
    for (f->i = 0; f->i < f->n; ++f->i) {
        f->promise.yield_value(f->a);
        f->index = 1;
        return;                     // 挂起就是返回到恢复者
after_yield:
        f->a = std::exchange(f->b, f->a + f->b);
    }
    f->promise.return_void();
    f->resume = nullptr;            // 到达最终挂起点：resume 指针置空
    return;
}
```

### 协程状态的布局

Clang 和 GCC 的协程状态都以两个函数指针开头，分别指向 resume 函数和 destroy 函数，接着是 promise 对象，然后是形参副本、跨挂起点存活的局部变量和挂起点编号。由此可以理解 `coroutine_handle` 的接口：

- `resume()` 和 `destroy()` 只需要协程状态的地址，通过开头的两个指针就能调用到具体协程的代码，相当于手写的类型擦除；
- `done()` 检查 resume 指针是否为空；
- `promise()` 和 `from_promise()` 按固定偏移在协程状态地址和 promise 地址之间换算。偏移取决于 promise 的大小和对齐，所以只有 `coroutine_handle<P>` 提供它们，`coroutine_handle<>` 没有。

只有跨挂起点存活的变量才需要放进协程状态，优化级别不同，协程状态的大小和布局也不同。

### 省掉堆分配

[[dcl.fct.def.coroutine#9]] 说实现可能需要为协程状态分配存储。如果编译器能证明协程状态的生命周期完全嵌套在调用者之内（在调用者里创建、使用、销毁，句柄没有逃逸），就可以把它放进调用者的栈帧，省掉 `operator new` 和 `operator delete`。这种优化叫 HALO（heap allocation elision optimization）。

本机用 `-O2` 编译上面的 generator 例子，`main` 里没有任何 `operator new` 调用。但 HALO 不可靠：句柄被存进容器、作为返回值传出去，或者协程的定义在另一个翻译单元里看不到，优化就会失效。需要确定内存行为的代码，可以在 promise 里提供自己的 `operator new`，见 [[dcl.fct.def.coroutine]] 中的例子。

## 对称转移

考虑一个惰性的 `task`：`co_await child` 时，在 `await_suspend` 里启动 child；child 结束时，在它的 `final_suspend` 里恢复等待它的协程。最直接的写法是在 `await_suspend` 里调用 `resume()`：

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

这个程序在本机 `-O0` 下因栈溢出崩溃（退出码 139）。每轮循环，`loop` 的 resume 函数在 `await_suspend` 里调用 `leaf` 的 resume 函数；`leaf` 结束时，又在 `final_suspend` 的 `await_suspend` 里调用 `loop` 的 resume 函数。这些调用都不返回，栈帧一层压一层，一百万轮就是几百万层。

**对称转移**（symmetric transfer）的做法是：`await_suspend` 不自己调用 `resume()`，而是返回要恢复的句柄，由实现对它调用 `resume()`（[[expr.await#5.1.1]]）。标准没有直接写"尾调用"，但它的注 1 说可以这样依次恢复任意多个协程，最终回到调用者。实现会把这次调用编译成尾调用，先弹出当前协程的栈帧：Clang 在 LLVM IR 里使用 `musttail`，`-O0` 下也是如此。

上例只需改两处：

```cpp
// final_suspend 返回的 awaiter：
std::coroutine_handle<> await_suspend(std::coroutine_handle<promise_type> h) noexcept {
    return h.promise().cont ? h.promise().cont : std::noop_coroutine();
}
// task 自己作为 awaiter：
std::coroutine_handle<> await_suspend(std::coroutine_handle<> c) { h.promise().cont = c; return h; }
```

改完后同样的循环在 `-O0` 下正常输出 `done`。`std::noop_coroutine()`（[[coroutine.noop]]）返回一个恢复时什么也不做的句柄，用在没有要转移的协程、只想返回给调用者的情形。

## `std::generator` {{c++23}}

C++23 标准库提供了 `std::generator<Ref, V = void, Allocator = void>`（[[coro.generator]]，[[P2502R2]]），它同时是一个 `std::ranges::view`：

```cpp title="std-generator.cpp"
#include <generator>
#include <print>
#include <ranges>

std::generator<int> iota(int n) {
    for (int i = 0; i < n; ++i) co_yield i;
}

std::generator<int> twice(int n) {
    co_yield std::ranges::elements_of(iota(n));   // 委托给另一个 generator，不必逐个转发
    co_yield std::ranges::elements_of(iota(n));
}

int main() {
    for (int x : twice(3) | std::views::transform([](int v) { return v * 10; }))
        std::print("{} ", x);                       // 0 10 20 0 10 20
}
```

本机 Clang 23 附带的 libc++ 还没有 `<generator>` 头文件（libstdc++ 已经实现），所以这个例子没有在本地编译。`elements_of` 的委托在实现上用的就是对称转移，嵌套多深都不会增加栈深度。

## 常见的生命周期错误

协程的错误大多是生命周期错误。协程的调用在第一次挂起时就返回了，函数体却在之后继续运行。调用表达式里的临时量、调用者的局部变量，到协程恢复时可能都已经不在了。

| # | 写法 | 问题 | 改法 |
|---|---|---|---|
| 1 | `task f(const std::string& s)`，调用 `f("literal")` | 临时 `string` 在调用所在的完整表达式结束时销毁，协程状态里只有引用（[[dcl.fct.def.coroutine#13]]） | 按值接收：`task f(std::string s)` |
| 2 | `task f(std::string_view sv)` | `string_view` 复制进了协程状态，它指向的字符没有 | 同上 |
| 3 | `[&x]() -> task { co_await …; use(x); }()` | 闭包对象是临时量，不会复制进协程状态，捕获随闭包一起消失 | 不让协程 lambda 捕获；或用 C++23 的 `[x](this auto self) -> task { … }` 把闭包按值传进去 |
| 4 | `task C::run() { co_await …; use(m); }` | 协程状态里只有 `this` 指针，对象销毁后再恢复 | 用 `shared_from_this`，或保证对象活得比协程长 |
| 5 | `final_suspend` 返回 `suspend_never`，返回对象的析构函数仍然 `h.destroy()` | 协程状态已经自动销毁，又销毁一次 | 两种所有权模型只选一种 |
| 6 | `await_suspend` 把 `h` 交给其他线程后访问 `this` | 协程可能已经在另一个线程上结束 | 交出句柄后不再访问 awaiter 和协程状态 |
| 7 | `task<int> f() { if (c) co_return 1; }` | promise 没有 `return_void` 时流出末尾是 UB（[[stmt.return.coroutine#3]]） | 开启 `-Werror=return-type` |
| 8 | 在 `await_suspend` 里直接 `resume()` 另一个协程 | 栈无限增长 | 对称转移：返回句柄 |
| 9 | 持有 `std::lock_guard` 跨越 `co_await` | 协程可能在另一个线程上恢复，在那里解锁不属于它的互斥量是 UB | 在 `co_await` 之前释放锁 |

第 1 种的完整演示和 ASan 报告见 [[topics/dangling-references]] 第 8 节。

## 设计一个协程类型

写一个协程返回类型时，依次回答下面几个问题：

1. 谁拥有协程状态？返回对象持有句柄并在析构时 `destroy()`，还是协程结束时自动销毁？这决定 `final_suspend`。
2. 调用时是否立即运行？这决定 `initial_suspend`。惰性启动更容易组合，也不会出现返回对象还没构造好、协程就已经运行完的情况。
3. 结果和异常放在哪里？这决定 `return_value` 或 `return_void`，以及 `unhandled_exception`。
4. 被 `co_await` 时怎样衔接？让返回类型本身成为 awaiter，用对称转移启动子协程、回到等待者。
5. 协程里允许等待什么？用 `await_transform` 控制。
6. 内存从哪里来？在 promise 里提供 `operator new`（可以带分配器形参），需要时再提供 `get_return_object_on_allocation_failure`。

## 思考题

!!! question "思考题 1"
    `co_await std::suspend_always{};` 和 `co_await std::suspend_never{};` 分别怎样展开？哪一个会产生挂起点？

<details markdown="1">
<summary>答案</summary>

`suspend_always::await_ready()` 返回 `false`，于是调用返回 `void` 的 `await_suspend(h)`，然后返回给调用者或恢复者，这里产生一个挂起点；恢复后调用 `await_resume()`，没有值。`suspend_never::await_ready()` 返回 `true`，直接调用 `await_resume()`，不挂起。

两者都是 [[support.coroutine]] 中定义的平凡 awaiter，所有成员都是 `constexpr` 且 `noexcept`，所以可以用作 `final_suspend` 的返回值（[[dcl.fct.def.coroutine#15]] 要求这个表达式不抛异常）。
</details>

!!! question "思考题 2"
    `std::coroutine_handle<>` 不知道 promise 类型，为什么还能 `resume()` 和 `destroy()`？为什么不能 `promise()`？

<details markdown="1">
<summary>答案</summary>

实现约定协程状态以 resume 和 destroy 两个函数指针开头，`resume()`、`destroy()` 只要有协程状态的地址，就能通过这两个指针调用到具体协程的代码。`promise()` 需要知道 promise 对象在协程状态里的偏移和类型，偏移又取决于 promise 的大小和对齐，所以只有 `coroutine_handle<P>` 能提供它。
</details>
