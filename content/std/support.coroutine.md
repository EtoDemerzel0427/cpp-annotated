---
title: 协程支持
summary: <coroutine> 的全部内容——编译器如何用 coroutine_traits 找到 promise 类型、coroutine_handle 的每个操作的前置条件（resume/destroy/done/promise/from_address）、跨执行代理恢复的规定、noop 协程与对称转移，以及 suspend_always/suspend_never
status: done
covers: *
papers: P0912R5, P0913R1
related: dcl.fct.def.coroutine, expr.await, expr.yield, stmt.return.coroutine, namespace.std, unord.hash, cmp
tags: 标准库, 协程, coroutine_handle, 对称转移
updated: 2026-10-18
---

C++20 协程的语言部分（[[dcl.fct.def.coroutine]]、[[expr.await]]、[[expr.yield]]）只规定了**变换规则**：编译器把含有 `co_await`/`co_yield`/`co_return` 的函数体改写成对一个 **promise 对象**的一系列调用。至于"promise 类型是什么""怎样从外部恢复一个挂起的协程"，核心语言把它们交给了 `<coroutine>` 里的两个"接口点"：

- `std::coroutine_traits`：编译器通过它，从协程的**返回类型和形参类型**找到 promise 类型；
- `std::coroutine_handle`：编译器把协程帧的句柄以它的形式交给 `await_suspend`，用户通过它恢复、销毁协程，访问 promise。

¶1（[support.coroutine.general]）：`<coroutine>` 定义了为 C++ 程序中的协程提供编译期和运行期支持的若干类型。整个头文件是 freestanding 的，并且包含 `<compare>`（因为 `coroutine_handle` 的 `<=>` 返回 `strong_ordering`）。

!!! note "库是语言的一部分"
    [[dcl.fct.def.coroutine#3]] 直接用 `std::coroutine_traits<R, P1, …, Pn>::promise_type` 定义协程的 promise 类型，协程变换中也要用 `std::coroutine_handle` 构造传给 `await_suspend` 的句柄。如果定义协程时 `<coroutine>` 未被包含，这些名字无法解析，程序非良构——Clang 的诊断是 `std::coroutine_traits type was not found; include <coroutine> before defining a coroutine`。这与 `<initializer_list>`、`<compare>`、`<typeinfo>` 一样，属于"核心语言依赖库"的少数场合。

## `coroutine_traits`：找到 promise 类型（[coroutine.traits]）

¶1（[coroutine.traits.general]）：本小节规定了表示**协程特征**（coroutine traits）的类所需满足的要求，并定义满足这些要求的类模板 `coroutine_traits`。

对一个返回类型为 `R`、形参类型为 `P1, ..., Pn` 的协程，[[dcl.fct.def.coroutine]] 规定其 promise 类型为 `std::coroutine_traits<R, P1', ..., Pn'>::promise_type`。（[[dcl.fct.def.coroutine#3]]：若协程是非静态成员函数，形参序列前面还要加上**对象形参**的类型，例如隐式对象成员函数的 `cv C&` 或 `cv C&&`。）

主模板（[coroutine.traits.primary] ¶1）：若限定名 `R::promise_type` 有效且表示一个类型（按 [[temp.deduct]] 的意义，即 SFINAE 友好），则 `coroutine_traits<R, ArgTypes...>` 有一个公开成员

```cpp
using promise_type = R::promise_type;
```

否则**没有任何成员**——于是使用它的协程定义非良构。这就是为什么通常把 `promise_type` 嵌套在返回类型（`Task`、`Generator`）中。

¶2：程序定义的特化**必须**定义一个公开可访问的嵌套类型 `promise_type`。特化 `coroutine_traits` 的价值在于：当返回类型**不是你能修改的类**（例如 `void`、`std::future<T>`）时，仍然可以为它指定 promise 类型。按 [[namespace.std]]，特化必须依赖于某个程序定义类型——可以借助形参类型来满足：

```cpp run title="coroutine-traits.cpp" ok
#include <coroutine>
#include <cstdio>
#include <exception>

struct Detached {};   // 程序定义的类型，用作"标签"形参

template<class... Args>
struct std::coroutine_traits<void, Detached, Args...> {   // 依赖于程序定义类型：允许
    struct promise_type {
        void get_return_object() {}
        std::suspend_never initial_suspend() noexcept { return {}; }
        std::suspend_never final_suspend() noexcept { return {}; }   // 结束时自动销毁协程帧
        void return_void() {}
        void unhandled_exception() { std::terminate(); }
    };
};

void task(Detached, int x) {     // 返回 void 的协程
    std::printf("running %d\n", x);
    co_return;
}

int main() { task(Detached{}, 42); }
```

## `coroutine_handle`（[coroutine.handle]）

### 两种形态（[coroutine.handle.general]）

```cpp
template<class Promise = void> struct coroutine_handle;   // 知道 promise 类型
template<> struct coroutine_handle<void>;                 // 类型擦除：coroutine_handle<>
```

`coroutine_handle<>`（即 `<void>`）是类型擦除的句柄，能指代任何协程，但不能访问 promise；`coroutine_handle<Promise>` 多了 `from_promise` 和 `promise()`，并可隐式转换为 `coroutine_handle<>`。二者都只有一个仅用于说明的 `void* ptr`——协程帧的地址。

¶1：`coroutine_handle<T>` 类型的对象称为**协程句柄**（[[g:coroutine-handle]]），可用于指代一个**挂起的或正在执行的**协程。`address()` 返回空指针的句柄不指代任何协程。两个句柄指代同一协程，**当且仅当**它们的 `address()` 返回相同的非空值。

¶2：程序声明 `coroutine_handle` 的显式或偏特化，**行为未定义**。（注意是 UB 而非"非良构"——标准库组件中两种措辞都存在，例如 `initializer_list` 与 `type_order` 是非良构。）

句柄是一个**非拥有的**原始指针：复制句柄不复制协程，句柄被销毁不影响协程。协程帧的生命期完全由 `destroy()` 或协程自然结束（`final_suspend` 不挂起时）控制。这就是为什么几乎所有协程返回类型都要像 `unique_ptr` 一样管理句柄。

### 构造与重置（[coroutine.handle.con]）

| 成员 | 规格 |
|---|---|
| 默认构造、`coroutine_handle(nullptr_t)` | ¶1 *Postconditions*：`address() == nullptr` |
| `static from_promise(Promise& p)` | ¶2 *Preconditions*：`p` 是某个协程的 promise 对象的引用；¶3–¶4 返回指代该协程的句柄 `h`，且 `addressof(h.promise()) == addressof(p)` |
| `operator=(nullptr_t)` | ¶5 *Postconditions*：`address() == nullptr` |

`from_promise` 是从 promise 回到句柄的唯一途径，典型用法是在 `get_return_object()` 中构造返回对象。它之所以可行，是因为 promise 对象**位于协程帧内的固定偏移处**——实现只需从 promise 地址减去一个偏移。传入不是协程 promise 的对象，违反前置条件，UB。

### 导出与导入（[coroutine.handle.export.import]）

- `address()`：返回 `ptr`（¶1）。
- `coroutine_handle<>::from_address(void* addr)`：¶2 *Preconditions*：`addr` 是先前对**某个** `coroutine_handle` 特化的对象调用 `address()` 得到的。
- `coroutine_handle<Promise>::from_address(void* addr)`：¶4 *Preconditions*：`addr` 是先前对 *cv* `coroutine_handle<Promise>` **（同一个 `Promise`）**的对象调用 `address()` 得到的。

这对函数让句柄可以穿过只接受 `void*` 的 C 接口（例如 `epoll_event.data.ptr`、操作系统回调的 `void* context`）。注意 `Promise` 版本的前置条件更严格：不能把一个 `coroutine_handle<A>` 的地址导入成 `coroutine_handle<B>`。

### 转换（[coroutine.handle.conv]）

`coroutine_handle<Promise>` → `coroutine_handle<>`：等价于 `coroutine_handle<>::from_address(address())`。反方向没有转换；需要时用 `coroutine_handle<P>::from_address(h.address())`，由你自己保证 promise 类型正确。

### 观察（[coroutine.handle.observers]）

- `explicit operator bool()`：`address() != nullptr`（¶1）。
- `done()`：¶2 *Preconditions*：`*this` 指代一个**挂起的**协程。¶3：若协程挂起于其**最终挂起点**（final suspend point），返回 `true`，否则 `false`。

`done()` 的前置条件意味着：对**空句柄**、对**已销毁**的协程、对**正在执行**的协程调用 `done()` 都是 UB。它不是一个"协程是否还活着"的查询——已经销毁的协程无法被查询。

### 恢复与销毁（[coroutine.handle.resumption]）

| 操作 | 前置条件 | 效果 |
|---|---|---|
| `resume()`、`operator()()` | ¶2：指代一个**挂起的**协程，且**不在最终挂起点** | ¶3：恢复协程的执行 |
| `destroy()` | ¶4：指代一个**挂起的**协程（可以在最终挂起点） | ¶5：销毁协程（[[dcl.fct.def.coroutine]]）：析构作用域内的对象、promise、参数副本，释放协程帧 |

违反前置条件的典型错误：

- 对已经执行完（停在最终挂起点）的协程调用 `resume()`——UB。所以生成器要先查 `done()`。
- 对 `final_suspend` 返回 `suspend_never` 的协程，在它结束后调用 `destroy()`——协程帧已经被自动释放，句柄悬垂，UB（"double free"）。
- 对**正在执行**的协程调用 `resume()` 或 `destroy()`——包括在协程自身的 `await_suspend` 返回之前从另一个线程恢复它。

¶1 是一条关于**执行代理**的规定：

!!! std
    Resuming a coroutine via `resume`, `operator()`, or `destroy` on an execution agent other than the one on which it was suspended has implementation-defined behavior unless each execution agent either is an instance of `std::thread` or `std::jthread`, or is the thread that executes `main`.

    在不同于协程挂起时所在执行代理的另一个执行代理上通过 `resume`、`operator()` 或 `destroy` 恢复协程，其行为由实现定义，除非两个执行代理都是 `std::thread` 或 `std::jthread` 的实例，或者是执行 `main` 的线程。

也就是说，在标准线程之间迁移协程是有保证的；在其他执行代理（例如并行算法的工作单元、某些平台的纤程、GPU 线程）之间迁移则由实现定义。注 1：在不同执行代理上恢复的协程应避免依赖线程身份的一致性，例如**跨挂起点持有互斥锁**（`std::mutex` 必须由加锁的线程解锁）、使用 `thread_local` 变量。注 2：并发地恢复同一个协程可能导致数据竞争。

### 访问 promise（[coroutine.handle.promise]）

`Promise& promise() const`：¶1 *Preconditions*：`*this` 指代一个协程（注意：不要求挂起——协程执行期间也可以通过句柄访问它的 promise）。¶2：返回该协程 promise 的引用。

### 比较与哈希（[coroutine.handle.compare]、[coroutine.handle.hash]）

`==` 比较 `address()`；`<=>` 返回 `compare_three_way()(x.address(), y.address())`——用 `compare_three_way` 而不是内建 `<`，是为了对不相关的指针也得到一个实现定义的**全序**（[[comparisons.three.way]]）。两个运算符都以 `coroutine_handle<>` 为形参，任何 `coroutine_handle<P>` 经隐式转换都可使用。`hash<coroutine_handle<P>>` 是启用的（[[unord.hash]]），所以句柄可以直接作为 `unordered_set` 的元素。

### 一个完整的生成器

```cpp run title="generator.cpp" ok
#include <coroutine>
#include <exception>
#include <utility>

template<class T>
class Generator {
public:
    struct promise_type {
        T current;
        Generator get_return_object() {
            return Generator{std::coroutine_handle<promise_type>::from_promise(*this)};
        }
        std::suspend_always initial_suspend() noexcept { return {}; }   // 创建后先挂起（惰性）
        std::suspend_always final_suspend() noexcept { return {}; }     // 结束时挂起，帧由 Generator 销毁
        std::suspend_always yield_value(T v) { current = std::move(v); return {}; }
        void return_void() {}
        void unhandled_exception() { std::terminate(); }
    };

    explicit Generator(std::coroutine_handle<promise_type> h) : h_(h) {}
    Generator(Generator&& o) noexcept : h_(std::exchange(o.h_, {})) {}
    ~Generator() { if (h_) h_.destroy(); }      // 前置条件：挂起（包括停在最终挂起点）

    bool next() {
        h_.resume();                            // 前置条件：挂起且不在最终挂起点
        return !h_.done();                      // 是否已经停在最终挂起点
    }
    const T& value() const { return h_.promise().current; }

private:
    std::coroutine_handle<promise_type> h_;
};

Generator<int> iota(int n) {
    for (int i = 0; i < n; ++i) co_yield i;
}

int main() {
    auto g = iota(4);
    int sum = 0;
    while (g.next()) sum += g.value();           // 0 + 1 + 2 + 3
    return sum == 6 ? 0 : 1;
}
```

（C++23 的 `std::generator`（`<generator>`）提供了生产级的实现，包括递归 `co_yield` 和分配器支持。）

!!! impl "Clang/libc++ 的实现"
    libc++ 的 `coroutine_handle` 只是对 Clang 内建函数的薄包装：`resume()` 调用 `__builtin_coro_resume`，`destroy()` 调用 `__builtin_coro_destroy`，`done()` 调用 `__builtin_coro_done`，`promise()` 和 `from_promise()` 调用 `__builtin_coro_promise`（带 promise 的对齐值，用于在帧地址和 promise 地址之间换算）。在 Clang 的实现中，协程帧开头是两个函数指针——**resume 函数**和 **destroy 函数**——`resume()` 就是一次通过帧内函数指针的间接调用，`done()` 检查 resume 函数指针是否为空。这正是 `coroutine_handle<>` 能类型擦除地恢复任何协程的原因。

## noop 协程（[coroutine.noop]）

### 类型（[coroutine.promise.noop]、[coroutine.handle.noop]）

`noop_coroutine_promise` 是一个空的结构体，作为 noop 协程的 promise 类型。`coroutine_handle<noop_coroutine_promise>`（别名 `noop_coroutine_handle`）是一个**显式特化**，与通用版本有几处不同：

| 成员 | noop 版本的规格 |
|---|---|
| `explicit operator bool()` | 总是 `true` |
| `done()` | 总是 `false`，并且是 `constexpr noexcept`、**没有前置条件** |
| `resume()`、`operator()()`、`destroy()` | **无效果**，`constexpr noexcept`；¶2：转换为 `coroutine_handle<>` 后，对其调用这三个函数也**没有可观察的效果** |
| `promise()` | 返回与此句柄关联的 promise 对象的引用 |
| `address()` | 返回 `ptr`；¶2：**总是非空** |
| 构造函数 | 私有，只能通过 `noop_coroutine()` 获得 |

### `noop_coroutine()`（[coroutine.noop.coroutine]）

¶1：返回一个指代"恢复或销毁时没有可观察效果"的协程的句柄。¶2：两次调用返回的句柄**可能相等也可能不相等**。

noop 协程存在的意义是**对称转移**（symmetric transfer）。`await_suspend` 可以返回一个 `coroutine_handle<>`，表示"挂起当前协程，然后立即恢复返回的那个协程"——编译器把它实现为尾调用，避免了在深层嵌套 `co_await` 链中栈的无限增长（[[expr.await]]）。但有时 `await_suspend` 没有下一个要恢复的协程（例如一个任务结束时，没有人在等它），这时需要一个"什么也不做"的句柄来返回——那就是 `noop_coroutine()`。

```cpp run title="symmetric-transfer.cpp" ok
#include <coroutine>
#include <exception>
#include <utility>

struct Task {
    struct promise_type {
        int value = 0;
        std::coroutine_handle<> continuation;          // 谁在等我
        Task get_return_object() { return Task{std::coroutine_handle<promise_type>::from_promise(*this)}; }
        std::suspend_always initial_suspend() noexcept { return {}; }
        struct FinalAwaiter {
            bool await_ready() noexcept { return false; }
            std::coroutine_handle<> await_suspend(std::coroutine_handle<promise_type> h) noexcept {
                auto c = h.promise().continuation;
                return c ? c : std::noop_coroutine();   // 没有等待者：转移到 noop 协程，控制返回给 resume() 的调用者
            }
            void await_resume() noexcept {}
        };
        FinalAwaiter final_suspend() noexcept { return {}; }
        void return_value(int v) { value = v; }
        void unhandled_exception() { std::terminate(); }
    };

    bool await_ready() { return false; }
    std::coroutine_handle<> await_suspend(std::coroutine_handle<> awaiting) {
        h_.promise().continuation = awaiting;
        return h_;                                     // 对称转移：直接恢复被等待的协程
    }
    int await_resume() { return h_.promise().value; }

    explicit Task(std::coroutine_handle<promise_type> h) : h_(h) {}
    Task(Task&& o) noexcept : h_(std::exchange(o.h_, {})) {}
    ~Task() { if (h_) h_.destroy(); }
    std::coroutine_handle<promise_type> h_;
};

Task leaf() { co_return 20; }
Task root() { int a = co_await leaf(); int b = co_await leaf(); co_return a + b + 2; }

int main() {
    Task t = root();
    t.h_.resume();                                     // 启动 root；全部完成后经 noop 协程返回这里
    return (t.h_.done() && t.h_.promise().value == 42) ? 0 : 1;
}
```

!!! impl
    Clang 提供 `__builtin_coro_noop()`，返回一个静态的、resume/destroy 函数都是空函数的"协程帧"，libc++ 用它构造 `noop_coroutine_handle`；对于不提供该内建函数的 GCC，libc++ 自己构造一个静态的假帧。因为帧是静态的，`address()` 永远非空，`done()` 永远为假。

## 平凡 awaitable（[coroutine.trivial.awaitables]）

```cpp
struct suspend_never {
  constexpr bool await_ready() const noexcept { return true; }
  constexpr void await_suspend(coroutine_handle<>) const noexcept {}
  constexpr void await_resume() const noexcept {}
};
struct suspend_always {
  constexpr bool await_ready() const noexcept { return false; }
  constexpr void await_suspend(coroutine_handle<>) const noexcept {}
  constexpr void await_resume() const noexcept {}
};
```

注 1：它们分别表示 *await-expression* "从不挂起"和"总是挂起"，两者都不产生值。最常见的用途是作为 `initial_suspend()` 和 `final_suspend()` 的返回值：

- `initial_suspend()` 返回 `suspend_always` → **惰性**协程（创建后不执行，直到第一次 `resume`），例如上面的生成器和 `Task`；返回 `suspend_never` → **急切**协程。
- `final_suspend()` 返回 `suspend_always` → 协程结束后停在最终挂起点，帧由句柄的持有者负责 `destroy()`；返回 `suspend_never` → 协程结束时**自动销毁**帧，之后任何句柄都悬垂。

[[dcl.fct.def.coroutine#15]] 要求表达式 `co_await promise.final_suspend()` **不得是潜在抛出的**——这就是为什么这两个类型的所有成员都是 `noexcept` 的，以及为什么自定义的 final awaiter 也必须全部 `noexcept`。

!!! history "历史"
    协程最初以技术规范（ISO/IEC TS 22277，Coroutines TS）的形式发布，[[P0912R5]] 将其合并进 C++20。`noop_coroutine` 和对称转移（`await_suspend` 返回 `coroutine_handle`）由 [[P0913R1]] 加入，解决了早期设计中"每次 `co_await` 恢复另一个协程都会消耗一层栈"的问题。

## 小结

!!! summary
    - 编译器通过 `coroutine_traits<R, Args...>::promise_type` 找 promise 类型；主模板转发 `R::promise_type`，否则没有成员；可以为 `void` 等返回类型特化（需依赖程序定义类型）。
    - `coroutine_handle` 是非拥有的帧指针；`<>` 版本类型擦除，`<P>` 版本可访问 promise。特化它是 UB。
    - `resume()` 要求挂起且不在最终挂起点；`destroy()` 和 `done()` 要求挂起；`from_promise` 要求实参是协程的 promise；`from_address` 要求地址来自（同类型的）句柄。
    - 在 `std::thread`/`std::jthread`/主线程之间迁移协程有保证，其他执行代理由实现定义。
    - `noop_coroutine()` 的句柄恢复/销毁无效果、地址非空、`done()` 为假，用作对称转移的"空目标"。
    - `suspend_always`/`suspend_never` 是最简单的 awaitable，决定协程的惰性/急切与帧的所有权。
