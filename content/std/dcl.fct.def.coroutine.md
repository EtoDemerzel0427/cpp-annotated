---
title: 协程定义
summary: 函数体中出现 co_await/co_yield/co_return 就是协程：promise 类型经 coroutine_traits 查找、函数体被改写为"替换体"（initial_suspend / final_suspend / unhandled_exception）、get_return_object 的时机、协程状态的分配与释放（promise 中的 operator new、分配失败的处理）、形参复制进协程帧（引用形参会悬垂）、destroy 与流出末尾
status: draft
since: c++20
papers: P0912R5
related: expr.await, expr.yield, stmt.return.coroutine, coroutine.handle, support.coroutine, class.copy.elision, dcl.contract, topics/coroutines
tags: 协程, promise, coroutine_handle, 生命周期, UB
updated: 2026-10-18
---

C++20 的协程是**无栈**（stackless）协程：一个协程可以在 `co_await` / `co_yield` 处挂起，把控制交还给调用者或恢复者，之后再从挂起点继续；它的局部状态保存在一块堆上（或被优化掉）的**协程状态**（coroutine state，俗称"协程帧"）中，而不是独占一个栈。

语言本身对协程"做什么"几乎没有规定——没有内置的 `task`、`generator`、调度器。标准只规定一个**改写协议**：编译器把协程函数体改写成对用户提供的 **promise 类型**的一系列调用。所有语义（惰性还是立即执行、结果放在哪里、异常怎么传播、谁负责销毁）都由 promise 类型和 awaiter 决定。本节（[dcl.fct.def.coroutine]）规定这个改写的框架；`co_await` 的细节在 [[expr.await]]，`co_yield` 在 [[expr.yield]]，`co_return` 在 [[stmt.return.coroutine]]，库组件（`coroutine_handle`、`coroutine_traits`）在 [[support.coroutine]]。端到端的介绍与实现剖析见专题 [[topics/coroutines]]。

## 什么函数是协程（¶1–2）

¶1 函数的函数体若**包含** *coroutine-return-statement*（`co_return`）、*await-expression*（`co_await`）或 *yield-expression*（`co_yield`），它就是**协程**（coroutine）。

注意：

- 判定是**语法**的，不看返回类型：任何返回类型都可以，只要能找到合适的 promise 类型。反过来，从外部（声明）看不出一个函数是不是协程——协程是**实现细节**，调用者只看到一个普通函数；
- "包含"不穿透 lambda：函数体内 lambda 中的 `co_await` 使 lambda 成为协程，而不是外层函数；
- 协程的形参声明子句不能以**不属于形参声明的省略号**结尾——C 风格可变参数函数不能是协程（形参无法被复制进协程帧）。形参包没问题。

此外，其他条款规定以下函数**不能**是协程：`main`（[[basic.start.main]]）、构造函数（[[class.ctor]]）、析构函数（[[class.dtor]]）、返回类型含占位符（`auto`、`decltype(auto)`）的函数（[[dcl.spec.auto]]——promise 类型的查找需要返回类型）。`constexpr` 函数可以声明，但协程不是 constexpr-suitable 的（[[dcl.constexpr]]），所以非模板的 constexpr 函数不能是协程。

```cpp title="not-coroutine.cpp" error
#include <coroutine>
struct r {
    struct promise_type {
        r get_return_object() { return {}; }
        std::suspend_never initial_suspend() noexcept { return {}; }
        std::suspend_never final_suspend() noexcept { return {}; }
        void return_value(int) { }
        void unhandled_exception() { }
    };
};
r g(int a, ...) { co_return 1; }       // error: 可变参数函数不能是协程
r h() { return r{}; co_return 1; }     // error: 协程中不能有 return 语句（[stmt.return.coroutine]）
auto k() { co_return 1; }              // error: 占位符返回类型
```

## promise 类型（¶3–4）

¶3 协程的 **promise 类型**是

```cpp
std::coroutine_traits<R, P1, ..., Pn>::promise_type
```

其中 `R` 是函数的返回类型，`P1 … Pn` 是**非对象形参**的类型序列；若协程是非静态成员函数，前面还要加上**对象参数**的类型（[[dcl.fct]]）——对隐式对象成员函数，就是隐式对象参数的类型（如 `C&`、`const C&`、`C&&`，[[over.match.funcs]]）。promise 类型必须是**类类型**。

`std::coroutine_traits` 的主模板（[[coroutine.traits]]）在 `R::promise_type` 存在时就取它。所以通常的写法是在返回类型里嵌套一个 `promise_type`；而对于**无法修改的返回类型**（如 `std::future<T>`），可以特化 `coroutine_traits` 来"适配"它：

```cpp title="traits-specialize.cpp" error
#include <coroutine>
struct NP { int x; };
template<> struct std::coroutine_traits<NP, int> { using promise_type = int; };
NP g(int) { co_return; }     // error: promise 类型 int 不是类类型
```

把形参类型也作为 `coroutine_traits` 的模板实参，意味着同一个返回类型可以根据形参选择不同的 promise 类型——例如第一个形参是分配器时选用"带分配器的 promise"。

¶4 为后文叙述，标准定义了记号：`p_i` 是类型为 `P_i` 的左值，指代**原始形参**（对隐式对象成员函数，`p_1` 指代对象参数 `*this`）；`q_i` 指代**形参的副本**（见 ¶13），但对隐式对象成员函数，`q_1` 是指代 `*this` 的左值（`*this` 不被复制）。

## 替换体（¶5）

¶5 协程的行为**如同**：先去掉所有形参声明中的**顶层 cv 限定符**，再把函数体替换为下面的**替换体**（replacement body）：

```
{
    promise-type promise promise-constructor-arguments ;
    try {
        co_await promise.initial_suspend() ;
        function-body
    } catch ( ... ) {
        if (!initial-await-resume-called)
            throw ;
        promise.unhandled_exception() ;
    }
final-suspend :
    co_await promise.final_suspend() ;
}
```

逐项解释（¶5.1–5.9）：

- **初始 await 表达式**（initial await expression）是含 `initial_suspend()` 的那个 `co_await`；**最终 await 表达式**（final await expression）是含 `final_suspend()` 的那个。它们不经过 `await_transform`（[[expr.await#3]]）。
- *initial-await-resume-called* 初始为 `false`，在初始 await 表达式的 *await-resume* 求值**之前**被置为 `true`。作用：在协程体真正开始之前（例如 `initial_suspend()` 本身、或其 awaiter 的 `await_ready`/`await_suspend` 抛出）发生的异常**不交给** `unhandled_exception`，而是直接传播给调用者——此时协程还没有"开始"，调用者应当看到这个异常。
- `promise` 是协程的 **promise 对象**（promise object），`final-suspend` 是仅用于说明的标号，`co_return` 最终 `goto` 到这里（[[stmt.return.coroutine]]）。
- ¶5.7 **promise 的构造实参**：先尝试用 `(q_1, …, q_n)`（形参副本，成员函数时还包括 `*this`）进行重载决议，若找到**可行**的构造函数就用它；否则默认构造。这让 promise 能"看到"协程的实参（例如提取分配器、调度器、取消令牌）。
- ¶5.8 在初始 await 表达式处挂起，称为挂起于**初始挂起点**（initial suspend point）。
- ¶5.9 在最终 await 表达式处挂起，或因 `unhandled_exception()` 抛出异常而退出（¶14），称为挂起于**最终挂起点**（final suspend point）。

把这个结构记住，就能推出协程的大部分行为：

| promise 成员 | 何时调用 | 典型选择 |
|---|---|---|
| 构造函数 | 协程被调用时，形参复制之后 | 默认构造，或接收形参 |
| `get_return_object()` | 构造 promise 之后、`initial_suspend` 之前（¶7） | 用 `coroutine_handle::from_promise(*this)` 构造返回对象 |
| `initial_suspend()` | 函数体之前 | `suspend_always`（惰性，如 task/generator）或 `suspend_never`（立即执行） |
| `yield_value(e)` | 每个 `co_yield e` | 保存值并挂起 |
| `return_value(e)` / `return_void()` | `co_return e;` / `co_return;` 或流出末尾 | 保存结果 |
| `unhandled_exception()` | 函数体抛出未捕获的异常 | `std::current_exception()` 存起来，或 `throw;` 重抛，或 `std::terminate()` |
| `final_suspend()` | 函数体结束之后 | `suspend_always`（由所有者 `destroy`）或对称转移到等待者；必须 `noexcept`（¶15） |
| `await_transform(e)` | 每个用户写的 `co_await e`（可选） | 拦截/改写被等待的对象 |

## get_return_object 的时机（¶7）

¶7 表达式 `promise.get_return_object()` 用于初始化协程调用所返回的引用或 prvalue 结果对象。对它的调用**按顺序先于**对 `initial_suspend` 的调用，并且**最多调用一次**。

为什么要在 `initial_suspend` 之前？因为若 `initial_suspend` 不挂起，协程体会立即运行，可能运行到结束、甚至销毁协程状态（`final_suspend` 返回 `suspend_never` 时）——那时 promise 已经不存在，再调用 `get_return_object` 就太晚了。返回对象通常持有 `coroutine_handle`，必须在一切开始之前拿到。

## 恢复与 resumer（¶8）

¶8 挂起的协程可以通过调用指代它的**协程句柄**（[[coroutine.handle]]）的恢复成员函数（`resume()`、`operator()`）来继续执行。调用恢复成员函数的那个求值称为**恢复者**（resumer）。对**未挂起**的协程调用恢复成员函数，行为未定义 {{ub}}——包括对正在运行的协程（例如在协程内部对自己的句柄 `resume()`）和已经在最终挂起点的协程（`done()` 为真）。

协程挂起时，控制返回到调用者（第一次）或恢复者（之后）。这就是"无栈"的含义：协程不能从它调用的普通函数内部挂起，只能在自己的函数体里的 `co_await` 处挂起，然后返回到上一层。

## 协程状态的分配（¶9–10）

¶9 实现可能需要为协程分配额外的存储，称为**协程状态**（[[g:coroutine-state|coroutine state]]），通过调用**非数组分配函数**（[[basic.stc.dynamic.allocation]]）获得，这一调用是替换体的一部分。分配函数的名字**先在 promise 类型的作用域中查找**：

- ¶9.1 若找到任何声明，先尝试用实参列表 `(size, p_1, …, p_n)` 做重载决议——注意这里传的是**原始形参** `p_i`（带原始的 cv），不是副本；若没有可行函数，再用 `(size)` 做一次；
- ¶9.2 若在 promise 类型中找不到，就在全局作用域查找，用 `(size)` 调用。

"may need to allocate"——**可能**需要：当编译器能证明协程状态的生命周期严格嵌套在调用者之内时，可以把它放进调用者的栈帧，完全省去堆分配。这称为**堆分配消除**（heap allocation elision，HALO）。

¶10 若在 promise 类型作用域中查找名字 `get_return_object_on_allocation_failure` 找到了任何声明，则：

- 认为分配函数在失败时返回 `nullptr`（而不是抛出 `std::bad_alloc`）；若选中的是全局分配函数，改用 `::operator new(size_t, nothrow_t)` 形式；
- 所用的分配函数必须具有不抛出的 *noexcept-specifier*；
- 若分配函数返回 `nullptr`，协程立即把控制交还给调用者，返回值通过调用 `T::get_return_object_on_allocation_failure()`（`T` 是 promise 类型）获得——这时 promise 对象根本没有被构造。

这为不使用异常的环境（嵌入式、游戏、内核）提供了处理分配失败的途径。

```cpp run title="coro-alloc.cpp" ok
#include <coroutine>
#include <cstddef>
#include <cstdio>
#include <exception>

struct arena { char buf[1024]; std::size_t used = 0; };

struct job {
    struct promise_type {
        // ¶9.1：先尝试 operator new(size, arena&, int)——额外实参就是协程的原始形参
        static void* operator new(std::size_t n, arena& a, int) noexcept {
            std::printf("arena alloc %zu bytes\n", n);
            if (a.used + n > sizeof a.buf) return nullptr;
            void* p = a.buf + a.used;
            a.used += n;
            return p;
        }
        // ¶12：只找到带 size 的形式，就用它，并传入块的大小
        static void operator delete(void*, std::size_t n) noexcept { std::printf("free %zu bytes\n", n); }
        // ¶10：声明了它 ⇒ 分配函数返回 nullptr 表示失败
        static job get_return_object_on_allocation_failure() { std::puts("allocation failed"); return job{nullptr}; }

        promise_type(arena&, int id) { std::printf("promise ctor sees id=%d\n", id); }  // ¶5.7

        job get_return_object() { return job{std::coroutine_handle<promise_type>::from_promise(*this)}; }
        std::suspend_never initial_suspend() noexcept { return {}; }
        std::suspend_never final_suspend() noexcept { return {}; }   // 结束时协程状态自动销毁（¶11）
        void return_void() { }
        void unhandled_exception() { std::terminate(); }
    };
    std::coroutine_handle<promise_type> h;
    explicit job(std::coroutine_handle<promise_type> h) : h(h) { }
};

job work(arena&, int id) {
    std::printf("body runs, id=%d\n", id);
    co_return;
}

int main() {
    arena a;
    work(a, 7);
}
```

本机（Clang 23，arm64，`-O0`）输出 `arena alloc 32 bytes` / `promise ctor sees id=7` / `body runs, id=7` / `free 32 bytes`；把 `buf` 改小到 16 字节则输出 `arena alloc 32 bytes` / `allocation failed`，协程体与 promise 构造函数都不会执行。协程帧的大小是实现细节，会随优化级别变化。

## 协程状态的销毁（¶11–12）

¶11 协程状态在以下两种情况下被销毁：

1. 控制**流出协程的末尾**——即最终 await 表达式没有挂起（`final_suspend()` 返回 `suspend_never` 一类的 awaiter），替换体执行完毕；
2. 调用指代该协程的句柄的 `destroy()` 成员函数。此时视为控制从函数中**转移出去**（[[stmt.dcl]]）：所有活跃的自动变量（包括形参副本与 promise 对象）按逆序析构，就像 `goto` 跳出它们的作用域。

协程状态的存储通过调用**非数组解分配函数**释放。对**未挂起**的协程调用 `destroy()` 是未定义行为 {{ub}}。

后果：若 `final_suspend` 返回 `suspend_never`，协程运行结束后句柄立即失效，持有句柄的对象**绝不能**再调用 `destroy()` 或 `done()`；若返回 `suspend_always`，协程停在最终挂起点，所有者**必须**调用 `destroy()`，否则泄漏。这两种所有权模型二选一，是设计协程类型时最重要的决定。

¶12 解分配函数的名字先在 promise 类型的作用域中查找，找不到再到全局作用域。若同时找到"只有指针形参"的和"指针 + 大小形参"的**通常解分配函数**，选**两个形参**的那个；否则选一个形参的。若找不到通常解分配函数，程序非良构。选中的函数以存储块的地址为第一个实参调用；若带 `size_t` 形参，传入块的大小。

注意 ¶12 与 ¶9 不对称：解分配函数**不会**收到协程的形参（销毁时形参副本已经析构了）。所以用 arena 分配时，要么 arena 能从地址反推，要么在分配时把 arena 指针存在块的头部。

## 形参被复制进协程帧（¶13）

¶13 协程被调用时，在替换体的开头为每个形参创建一个**副本**。对原始声明类型为 cv `T` 的形参：

- ¶13.1 若 `T` 是引用类型，副本是 cv `T` 类型的引用，**绑定到同一个对象**；
- ¶13.2 否则，副本是 cv `T` 类型、自动存储期的变量，用指代该形参的 `T` 类型 **xvalue 直接初始化**——也就是说按值形参会被**移动**进协程帧。

注 2：函数体中命名这些形参的标识符指代的是**副本**，不是原始形参（[[expr.prim.id.unqual]]）。

副本的初始化和销毁发生在被调协程的语境中。副本的初始化**按顺序先于** promise 构造函数的调用，彼此之间**顺序不确定**。副本的生命周期在 promise 对象的生命周期结束**之后立即**结束。

为什么要复制？原始形参位于调用者为这次调用准备的位置（寄存器或调用者栈帧），协程第一次挂起返回后它们就不复存在了；而协程体可能在之后很久才恢复。所以按值形参必须搬进协程帧。[[class.copy.elision]] ¶1.3 允许在不改变程序含义（除了副本的构造与析构）时省略这次复制。

!!! ub "引用形参会悬垂"
    注 3：若协程有按引用传递的形参，在被引用实体的生命周期结束**之后**恢复协程，很可能导致未定义行为。副本只是"同一个引用"，并不延长任何东西的生命周期。

```cpp run title="coro-dangling.cpp" ub
#include <coroutine>
#include <cstdio>
#include <string>
#include <utility>

struct lazy {
    struct promise_type {
        lazy get_return_object() { return lazy{std::coroutine_handle<promise_type>::from_promise(*this)}; }
        std::suspend_always initial_suspend() noexcept { return {}; }   // 惰性：调用时不运行函数体
        std::suspend_always final_suspend() noexcept { return {}; }
        void return_void() { }
        void unhandled_exception() { throw; }
    };
    std::coroutine_handle<promise_type> h;
    explicit lazy(std::coroutine_handle<promise_type> h) : h(h) { }
    lazy(lazy&& o) noexcept : h(std::exchange(o.h, {})) { }
    ~lazy() { if (h) h.destroy(); }
};

lazy print(const std::string& s) {        // 引用形参：帧中的"副本"仍是同一个引用
    std::printf("%s\n", s.c_str());
    co_return;
}

int main() {
    lazy t = print(std::string(40, 'x')); // 临时 string 在这条完整表达式结束时销毁
    t.h.resume();                          // UB: 函数体此时才运行，s 已悬垂
}
```

AddressSanitizer 报告 `stack-use-after-scope`。修正方法：协程的形参**按值**接收（`lazy print(std::string s)`），让它被移动进帧里。这条规则对 `std::string_view`、`std::span`、迭代器等"借用"类型同样适用——它们是按值传递的，但所指向的数据不在帧里。成员函数协程中的 `this` 也是如此：`q_1` 指代 `*this`，**不被复制**，对象销毁后恢复协程同样悬垂。

## unhandled_exception 抛出（¶14）与 final_suspend 不抛出（¶15）

¶14 若 `promise.unhandled_exception()` 的求值通过异常退出，协程被视为**挂起于最终挂起点**，异常传播给调用者或恢复者。这使得"在 `unhandled_exception` 中 `throw;` 重抛"成为一种合法的策略（generator 常用）：异常从 `resume()` 中抛出，句柄的 `done()` 为真，之后 `destroy()` 仍然合法。

¶15 表达式 `co_await promise.final_suspend()` 不能是**潜在抛出**的（[[except.spec]]）——包括 `final_suspend()` 本身、返回的 awaiter 的 `await_ready`/`await_suspend`/`await_resume`、以及 awaiter 的析构。原因是：最终挂起点位于 `try` 块之外（见替换体），若此处抛出，异常无处可去，协程状态处于一种无法定义的半销毁状态。

```cpp title="final-noexcept.cpp" error
#include <coroutine>
struct r {
    struct promise_type {
        r get_return_object() { return {}; }
        std::suspend_never initial_suspend() { return {}; }
        std::suspend_never final_suspend() { return {}; }   // 缺 noexcept
        void return_void() { }
        void unhandled_exception() { }
    };
};
r f() { co_return; }   // error: 'co_await __promise.final_suspend()' 必须是不抛出的
```

## 与契约的交互（¶6）

¶6（注）在协程的后置条件中 odr-use 非引用形参是非良构的（[[dcl.contract]]）。普通函数中只要把形参声明为 `const` 就可以在后置条件中使用；协程中即使 `const` 也不行——函数体操作的是帧中的**副本**，原始形参在协程第一次挂起后就已不存在。

## 流出末尾

¶11 提到"控制流出协程的末尾"指的是流出**替换体**的末尾。流出**函数体**（用户写的部分）的末尾由 [[stmt.return.coroutine#3]] 规定：若 `p.return_void()` 的重载决议成功，流出末尾等价于 `co_return;`；**否则行为未定义** {{ub}}。也就是说，promise 只有 `return_value` 的协程（如 `task<int>`）若某条路径忘了 `co_return x;`，不是编译错误，而是 UB——Clang 给出 `-Wreturn-type` 警告（"non-void coroutine does not return a value"）。

## 两个完整例子

### 最小 generator

```cpp run title="generator.cpp" ok
#include <coroutine>
#include <cstdio>
#include <exception>
#include <utility>

template<class T>
class generator {
public:
    struct promise_type {
        T current;
        generator get_return_object() {                                   // ¶7：先于 initial_suspend
            return generator{std::coroutine_handle<promise_type>::from_promise(*this)};
        }
        std::suspend_always initial_suspend() noexcept { return {}; }     // 惰性：创建后先挂起
        std::suspend_always final_suspend() noexcept { return {}; }       // 停在最终挂起点，由 generator 销毁
        std::suspend_always yield_value(T v) { current = std::move(v); return {}; }   // co_yield v
        void return_void() { }                                            // 允许流出末尾
        void unhandled_exception() { throw; }                             // ¶14：重抛给 resume() 的调用者
    };
    explicit generator(std::coroutine_handle<promise_type> h) : h_(h) { }
    generator(generator&& o) noexcept : h_(std::exchange(o.h_, {})) { }
    generator(const generator&) = delete;
    ~generator() { if (h_) h_.destroy(); }                                // ¶11：销毁协程状态

    bool next() { h_.resume(); return !h_.done(); }
    const T& value() const { return h_.promise().current; }
private:
    std::coroutine_handle<promise_type> h_;
};

generator<int> fib(int n) {
    int a = 0, b = 1;
    for (int i = 0; i < n; ++i) {
        co_yield a;                        // 即 co_await promise.yield_value(a)（[expr.yield]）
        a = std::exchange(b, a + b);
    }
}

int main() {
    auto g = fib(10);
    while (g.next()) std::printf("%d ", g.value());   // 0 1 1 2 3 5 8 13 21 34
    std::printf("\n");
}
```

C++23 起标准库提供了完整的 `std::generator`（[[coro.generator]]），支持 range 接口、递归 `co_yield std::ranges::elements_of(…)` 和分配器。

### 最小 task：co_await 另一个协程

```cpp run title="task.cpp" ok
#include <coroutine>
#include <cstdio>
#include <exception>
#include <utility>

template<class T>
class task {
public:
    struct promise_type {
        T value{};
        std::exception_ptr error;
        std::coroutine_handle<> continuation = std::noop_coroutine();   // 谁在等我

        task get_return_object() {
            return task{std::coroutine_handle<promise_type>::from_promise(*this)};
        }
        std::suspend_always initial_suspend() noexcept { return {}; }   // 惰性启动
        auto final_suspend() noexcept {
            struct final_awaiter {
                bool await_ready() noexcept { return false; }
                std::coroutine_handle<> await_suspend(std::coroutine_handle<promise_type> h) noexcept {
                    return h.promise().continuation;    // 对称转移：直接恢复等待者
                }
                void await_resume() noexcept { }
            };
            return final_awaiter{};
        }
        void return_value(T v) { value = std::move(v); }
        void unhandled_exception() { error = std::current_exception(); }
    };

    explicit task(std::coroutine_handle<promise_type> h) : h_(h) { }
    task(task&& o) noexcept : h_(std::exchange(o.h_, {})) { }
    ~task() { if (h_) h_.destroy(); }

    // awaiter 接口：使 task 可以被 co_await（[expr.await]）
    bool await_ready() const noexcept { return false; }
    std::coroutine_handle<> await_suspend(std::coroutine_handle<> awaiting) noexcept {
        h_.promise().continuation = awaiting;
        return h_;                                      // 对称转移：启动被等待的 task
    }
    T await_resume() {
        if (h_.promise().error) std::rethrow_exception(h_.promise().error);
        return std::move(h_.promise().value);
    }

    T run() {                 // 演示用：从普通函数同步驱动（本例所有等待都同步完成）
        h_.resume();
        return await_resume();
    }
private:
    std::coroutine_handle<promise_type> h_;
};

task<int> leaf(int x) { co_return x * 2; }

task<int> sum() {
    int a = co_await leaf(10);   // 挂起 sum，转移到 leaf；leaf 结束时转移回 sum
    int b = co_await leaf(11);
    co_return a + b;
}

int main() {
    std::printf("%d\n", sum().run());   // 42
}
```

控制流：`sum().run()` 恢复 `sum`；`co_await leaf(10)` 调用 `leaf`（惰性，停在初始挂起点），`task::await_suspend` 记录 `sum` 为 continuation 并返回 `leaf` 的句柄——编译器对返回的句柄调用 `resume()`（[[expr.await#5]]），以尾调用的方式进入 `leaf`；`leaf` 执行 `co_return` 后在最终挂起点返回 continuation，转回 `sum`。`sum` 结束时 continuation 是 `noop_coroutine()`，于是控制回到 `run()`。这种"返回句柄"的写法称为**对称转移**（symmetric transfer），避免了互相 `resume()` 导致的栈增长。

## 实现视角

!!! impl
    - **拆分**：Clang 在 LLVM 中把协程拆成三个函数（"ramp"、resume、destroy）。ramp 函数就是调用者看到的那个函数：分配帧、复制形参、构造 promise、调用 `get_return_object` 与 `initial_suspend`，在第一次挂起时返回；resume 与 destroy 函数通过帧中保存的"挂起点编号"跳转到对应位置（一个 switch 状态机）。
    - **帧布局（Clang）**：帧的开头是两个函数指针——resume 函数和 destroy 函数——随后是 promise 对象，然后是跨挂起点存活的局部变量与形参副本、挂起点索引。`coroutine_handle::resume()` 就是"调用帧首地址处的函数指针"，`destroy()` 调用第二个，`from_promise`/`promise()` 通过固定偏移在帧地址与 promise 地址之间换算。GCC 采用相同的约定（帧首两个函数指针）。正是这种"帧首是函数指针"的约定使 `coroutine_handle<>` 可以在不知道 promise 类型的情况下恢复和销毁协程。
    - **HALO**：Clang 在优化时（如 `-O2`）若能证明协程帧不逃逸出调用者（典型：调用者创建 generator 并在本函数内耗尽、析构），会消除 `operator new`/`delete`，把帧放进调用者的栈帧。¶9 的"may need to allocate"为此提供了许可。
    - **诊断**：Clang 对流出非 void 协程末尾给出 `-Wreturn-type`；对 `final_suspend` 不是 noexcept 报错；对 promise 类型不是类报错。

## 历史与演进

!!! history
    - **Coroutines TS**（ISO/IEC TS 22277:2017）：基于 Gor Nishanov 的设计，在 MSVC 和 Clang 中以 `std::experimental` 实现多年。
    - **C++20**：通过 [[P0912R5]] 合入国际标准。随后的核心问题修订明确了形参副本的生命周期、`get_return_object` 的调用时机、`unhandled_exception` 抛出后的状态（¶14）等。
    - **C++23**：标准库加入 `std::generator`（[[coro.generator]]）。
    - **C++26**：协程后置条件中不能 odr-use 非引用形参（¶6，随契约引入）；标准库加入基于 sender/receiver 的执行框架 `std::execution`，其中 `std::execution::task` 等组件提供了标准的协程 task 类型（请以库条款为准）。

## 陷阱

!!! pitfall "引用与借用形参"
    协程签名中的 `const T&`、`std::string_view`、`std::span`、lambda 捕获的引用，都可能在协程恢复时悬垂。经验法则：会挂起的协程**按值接收一切**。

!!! pitfall "协程 lambda 的捕获"
    lambda 协程的闭包对象**不会**被复制进帧——`operator()` 的隐式对象参数是引用（`q_1` 指代 `*this`）。`[x]() -> task<> { co_await …; use(x); }()` 中临时闭包对象在完整表达式结束时销毁，之后恢复协程访问 `x` 就是 UB。C++23 起可以用显式对象参数按值接收闭包：`[x](this auto self) -> task<> { … }`。

!!! pitfall "`suspend_never` 作为 final_suspend"
    协程结束即自动销毁，返回对象中保存的句柄立即悬垂；此后任何 `h.done()`、`h.destroy()`、`h.promise()` 都是 UB。

!!! pitfall "忘记 co_return 值"
    promise 没有 `return_void` 时流出末尾是 UB，而不是编译错误；开启 `-Werror=return-type`。

## 思考题

!!! question "思考题 1"
    下面的协程被调用时，各步骤的顺序是什么？
    ```cpp
    task<int> f(Widget w);   // promise_type 有构造函数 promise_type(Widget&)
    ```

<details markdown="1">
<summary>答案</summary>

1. 调用者构造实参 `w`（原始形参）；
2. 调用分配函数获得协程状态（¶9；若 promise 有 `operator new(size_t, Widget&)`，以原始形参为额外实参）；
3. 用指代原始 `w` 的 xvalue 把 `w` **移动**构造进帧（¶13.2）；
4. 用形参副本构造 promise：`promise_type(Widget&)` 可行，于是以副本为实参（¶5.7）；
5. 调用 `get_return_object()`，结果用来初始化返回给调用者的 `task<int>`（¶7）；
6. `co_await promise.initial_suspend()`；若挂起，控制返回调用者；
7. 调用者在完整表达式结束时析构**原始**形参 `w`（帧中的副本不受影响）。
</details>

!!! question "思考题 2"
    为什么 promise 构造函数接收的是形参**副本** `q_i`，而 `operator new` 接收的是**原始形参** `p_i`？

<details markdown="1">
<summary>答案</summary>

时序决定了这一点：分配发生在形参复制**之前**——副本要放在新分配的帧里，分配时副本还不存在，只能把原始形参交给 `operator new`。promise 构造在复制**之后**，此时应当让 promise 引用帧中的副本（它们与协程同寿），而不是调用者那边即将消失的原始形参；若 promise 保存了对实参的引用，引用副本是安全的，引用原始形参则会悬垂。
</details>

!!! question "思考题 3"
    `generator` 的 `unhandled_exception` 写成 `throw;`，函数体抛出异常后，`g.next()` 中的 `h_.resume()` 会怎样？之后 `~generator()` 调用 `destroy()` 是否合法？

<details markdown="1">
<summary>答案</summary>

函数体的异常被替换体的 `catch (...)` 捕获，调用 `unhandled_exception()`，其中 `throw;` 重抛；按 ¶14，协程被视为挂起于最终挂起点，异常传播给恢复者，也就是从 `h_.resume()` 中抛出。由于协程处于挂起状态（最终挂起点），`done()` 为真，之后 `destroy()` 合法（¶11 只禁止对**未挂起**的协程调用 destroy）。
</details>

## 小结

!!! summary
    | 主题 | 要点 |
    |---|---|
    | 什么是协程 | 函数体含 `co_await`/`co_yield`/`co_return`；不能是可变参数、`main`、构造/析构、占位符返回类型 |
    | promise 类型 | `coroutine_traits<R, [对象参数类型,] P...>::promise_type`，须为类类型 |
    | 替换体 | promise 构造 → `initial_suspend` → 函数体（异常交给 `unhandled_exception`）→ `final_suspend` |
    | 初始挂起前的异常 | 直接传播给调用者，不交给 `unhandled_exception` |
    | `get_return_object` | 先于 `initial_suspend`，最多一次 |
    | 分配 | 先在 promise 中找 `operator new`（可带原始形参），否则全局；可被 HALO 消除 |
    | 分配失败 | 有 `get_return_object_on_allocation_failure` 时用不抛出的分配，`nullptr` 时返回它的结果 |
    | 销毁 | 流出替换体末尾或 `destroy()`；释放时优先带 size 的解分配函数 |
    | 形参 | 按值形参移动进帧；引用形参只复制引用——可能悬垂；`*this` 不复制 |
    | UB | 恢复/销毁未挂起的协程；无 `return_void` 时流出函数体末尾 |
    | `final_suspend` | 整个 `co_await` 必须不抛出 |
