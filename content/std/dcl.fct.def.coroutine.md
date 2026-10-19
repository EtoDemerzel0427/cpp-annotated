---
title: 协程定义
summary: 函数体里出现 co_await、co_yield 或 co_return 的函数就是协程；编译器按 promise 类型把函数体改写成固定的骨架，并规定协程状态怎样分配、形参怎样复制、何时销毁。
status: done
since: c++20
papers: P0912R5
related: expr.await, expr.yield, stmt.return.coroutine, coroutine.handle, support.coroutine, coro.generator, class.copy.elision, dcl.contract.func, topics/coroutines
tags: 协程, promise, coroutine_handle, 生命周期, UB
updated: 2026-10-19
---

!!! tldr
    - 函数体里出现 `co_await`、`co_yield` 或 `co_return`，这个函数就是协程。调用者从声明上看不出来。
    - 语言只规定一个骨架：创建 promise 对象，`initial_suspend`，函数体，`final_suspend`。惰性还是立即执行、结果放哪里、谁负责销毁，全由返回类型里的 `promise_type` 决定。
    - 形参在协程开始时复制进协程状态。按值形参被移动进去，引用形参只复制引用，协程恢复时它可能已经悬垂。
    - 协程状态在流出末尾或调用 `destroy()` 时销毁。对没有挂起的协程调用 `resume()` 或 `destroy()` 是 UB。
    - promise 只有 `return_value` 时，流出函数体末尾是 UB 而不是编译错误；`co_await promise.final_suspend()` 必须不抛异常。

## 一个最小的协程

```cpp run title="generator.cpp" ok
#include <coroutine>
#include <cstdio>
#include <utility>

template<class T>
class generator {
public:
    struct promise_type {
        T current;
        generator get_return_object() {
            return generator{std::coroutine_handle<promise_type>::from_promise(*this)};
        }
        std::suspend_always initial_suspend() noexcept { return {}; }  // 创建后先挂起
        std::suspend_always final_suspend() noexcept { return {}; }    // 结束后停住，由 generator 销毁
        std::suspend_always yield_value(T v) { current = std::move(v); return {}; }
        void return_void() { }
        void unhandled_exception() { throw; }
    };
    explicit generator(std::coroutine_handle<promise_type> h) : h_(h) { }
    generator(generator&& o) noexcept : h_(std::exchange(o.h_, {})) { }
    ~generator() { if (h_) h_.destroy(); }

    bool next() { h_.resume(); return !h_.done(); }
    const T& value() const { return h_.promise().current; }
private:
    std::coroutine_handle<promise_type> h_;
};

generator<int> fib(int n) {
    int a = 0, b = 1;
    for (int i = 0; i < n; ++i) {
        co_yield a;                      // 交出 a，挂起
        a = std::exchange(b, a + b);
    }
}

int main() {
    auto g = fib(10);
    while (g.next()) std::printf("%d ", g.value());   // 0 1 1 2 3 5 8 13 21 34
    std::printf("\n");
}
```

`fib` 看上去是一个普通函数，返回 `generator<int>`。它的特别之处在 `co_yield`：每执行一次，`fib` 就挂起，把控制交还给 `main`；`main` 调用 `g.next()` 时，它从挂起处接着运行，局部变量 `a`、`b`、`i` 都还在。

能挂起又能恢复，局部变量就不能放在调用者的栈上。它们保存在一块单独分配的存储里，叫做[[g:coroutine-state|协程状态]]（coroutine state，常称协程帧）。C++ 的协程是**无栈**（stackless）协程：只能在自己的函数体里挂起，不能在它调用的普通函数内部挂起。

`generator` 和它的 `promise_type` 都是用户写的。语言本身没有内置 task、generator 或调度器，只规定编译器怎样把协程体改写成对 promise 的一串调用。`co_await` 的细节在 [[expr.await]]，`co_yield` 在 [[expr.yield]]，`co_return` 在 [[stmt.return.coroutine]]，`coroutine_handle` 等库组件在 [[support.coroutine]]，完整的介绍见 [[topics/coroutines]]。C++23 起标准库已经提供了功能完整的 `std::generator`（[[coro.generator]]）。

## 什么函数是协程（¶1–¶2）

¶1 函数体里含有 `co_return` 语句、`co_await` 表达式或 `co_yield` 表达式的函数就是[[g:coroutine|协程]]（coroutine）。

这是一个纯语法的判断，与返回类型无关，声明上也看不出来。调用者看到的只是一个返回 `generator<int>` 的函数，协程是实现细节。判断不穿透 lambda：函数体内某个 lambda 里的 `co_await` 使那个 lambda 成为协程，外层函数不受影响。

¶1 还规定协程的形参列表不能以 C 风格的 `...` 结尾，形参包展开的 `...` 不受限制（¶2 的标准例子）。其他条款另外排除了几类函数：

- `main`（[[basic.start.main]]）、构造函数（[[class.ctor]]）、析构函数（[[class.dtor]]）；
- 返回类型含 `auto`、`decltype(auto)` 等占位符的函数（[[dcl.spec.auto#18]]），因为要靠返回类型找 promise 类型；
- 非模板的 constexpr 函数（包括 consteval 函数）。[[dcl.constexpr#3]] 规定协程不是 constexpr-suitable 的，而非模板的 constexpr 函数必须是 constexpr-suitable 的。constexpr 函数模板的实例化是协程不违反规则，只是不能在常量求值中调用；但 Clang 23 连这种函数模板也直接拒绝。

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
r g(int, ...) { co_return 1; }         // error: C 风格可变参数
r h() { return r{}; co_return 1; }     // error: 协程里不能有 return 语句
auto k() { co_return 1; }              // error: 占位符返回类型
constexpr r c() { co_return 1; }       // error: 非模板 constexpr 函数不能是协程
```

## promise 类型（¶3–¶4）

¶3 协程的[[g:promise-type|promise 类型]]是

```cpp
std::coroutine_traits<R, P1, ..., Pn>::promise_type
```

`R` 是返回类型，`P1 … Pn` 是形参类型。非静态成员函数还要在最前面加上对象参数的类型，例如 `C&`、`const C&`（[[dcl.fct]]）。promise 类型必须是类类型。

`std::coroutine_traits` 的主模板直接取 `R::promise_type`（[[coroutine.traits]]），所以通常的写法就是上面那样，在返回类型里嵌套一个 `promise_type`。返回类型改不了时（比如想让返回 `std::future<T>` 的函数成为协程），可以特化 `coroutine_traits`。形参类型也是模板实参，所以同一个返回类型可以按形参选择不同的 promise，例如第一个形参是分配器时换用带分配器的 promise。

```cpp title="traits-specialize.cpp" error
#include <coroutine>
struct NP { int x; };
template<> struct std::coroutine_traits<NP, int> { using promise_type = int; };
NP g(int) { co_return; }     // error: promise 类型 int 不是类类型
```

¶4 为后文定义两组记号。`p_i` 指代调用者传来的原始形参，`q_i` 指代协程里的形参副本（见 ¶13）。对隐式对象成员函数，`p_1` 是对象参数，`q_1` 指代 `*this` 本身：对象不会被复制。

## 编译器把函数体改写成什么（¶5）

¶5 协程的行为如同先去掉形参声明里的顶层 cv 限定，再把函数体换成下面的**替换体**（replacement body）：

```text
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

这个骨架决定了协程的大部分行为：

- `promise` 是协程的 [[g:promise-object|promise 对象]]。¶5.7 规定，如果 promise 有一个能用形参副本 `(q_1, …, q_n)` 调用的构造函数，就用它，否则默认构造。promise 由此能拿到协程的实参，例如分配器、调度器或取消令牌。
- 含 `initial_suspend()` 的 `co_await` 叫**初始 await 表达式**，含 `final_suspend()` 的叫**最终 await 表达式**。停在前者叫挂起于**初始挂起点**；停在后者，或因 `unhandled_exception()` 抛出异常而退出（¶14），叫挂起于**最终挂起点**（¶5.8–¶5.9）。
- *initial-await-resume-called* 在初始 await 表达式的 `await_resume` 求值之前才置为 `true`。所以 `initial_suspend()` 本身或它的 awaiter 抛出的异常直接传给调用者，不交给 `unhandled_exception`：函数体还没开始，调用者应当看到这个异常。
- `final-suspend` 是仅用于说明的标号，`co_return` 最后跳到这里（[[stmt.return.coroutine]]）。

把骨架和 promise 的成员对起来，就是写一个协程类型要做的全部决定：

| promise 成员 | 何时调用 | 常见写法 |
|---|---|---|
| 构造函数 | 形参复制之后 | 默认构造，或接收形参 |
| `get_return_object()` | 构造 promise 之后、`initial_suspend` 之前（¶7） | 用 `coroutine_handle::from_promise(*this)` 构造返回对象 |
| `initial_suspend()` | 函数体之前 | `suspend_always`（惰性）或 `suspend_never`（立即执行） |
| `yield_value(e)` | 每个 `co_yield e` | 保存值并挂起 |
| `return_value(e)` / `return_void()` | `co_return e;` / `co_return;` 或流出末尾 | 保存结果 |
| `unhandled_exception()` | 函数体抛出未捕获的异常 | 用 `std::current_exception()` 存起来，或 `throw;` 重抛 |
| `final_suspend()` | 函数体结束之后 | `suspend_always`（由所有者销毁）或转到等待者，必须不抛异常（¶15） |
| `await_transform(e)`（可选） | 每个用户写的 `co_await e` | 改写被等待的对象，不作用于初始和最终 await 表达式 |

¶6 是一条注：在协程的后置条件断言里 odr-use 非引用形参是非良构的（[[dcl.contract.func]]）。普通函数把形参声明为 `const` 就能在后置条件里使用；协程不行，因为函数体用的是副本，原始形参在第一次挂起后就不存在了。

## get_return_object 在 initial_suspend 之前（¶7）

¶7 `promise.get_return_object()` 的结果用来初始化协程调用的返回值。它在 `initial_suspend` 之前调用，最多调用一次。

顺序不能反过来。如果 `initial_suspend` 不挂起，函数体会立即运行，可能一直跑到结束；`final_suspend` 也不挂起的话，协程状态连同 promise 都已经销毁了。返回对象通常要持有指向协程的句柄，必须在一切开始之前拿到。

## 恢复（¶8）

¶8 挂起的协程通过句柄的 `resume()` 或 `operator()` 恢复（[[coroutine.handle]]），调用它的那个求值叫**恢复者**（resumer）。协程挂起时，控制第一次回到调用者，以后回到恢复者。

对没有挂起的协程调用恢复函数是未定义行为 {{ub}}。正在运行的协程（例如在协程内部对自己的句柄调用 `resume()`）和已经结束、状态已销毁的协程都属于这种情况。停在最终挂起点的协程虽然是挂起的，但 [[coroutine.handle.resumption]] 另外规定恢复它也是 UB，此时 `done()` 为真。

## 形参复制进协程状态（¶13）

¶13 协程被调用时，替换体一开始就为每个形参创建一个副本。设形参的原始声明类型是 cv `T`：

- ¶13.1 `T` 是引用类型时，副本是同一类型的引用，绑定到同一个对象；
- ¶13.2 否则，副本是 cv `T` 类型的自动变量，用指代原形参的 `T` 类型 xvalue 直接初始化。按值形参因此被移动进协程状态。

函数体里用到形参名时，指的是副本（注 2）。副本在 promise 构造之前初始化，彼此之间的顺序不确定；promise 对象的生命周期结束后，副本的生命周期紧接着结束。[[class.copy.elision]] ¶1.3 允许省略这次复制，只要除了副本的构造和析构之外程序含义不变。

原始形参位于调用者为这次调用准备的位置，协程第一次挂起、调用返回之后它们就没了，而协程体可能很久以后才恢复，所以必须复制。引用形参复制的只是引用，它不延长任何东西的生命周期。注 3 指出，被引用的实体结束生命周期后再恢复协程，很可能导致未定义行为：

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

lazy print(const std::string& s) {        // 副本仍是同一个引用
    std::printf("%s\n", s.c_str());
    co_return;
}

int main() {
    lazy t = print(std::string(40, 'x')); // 临时 string 在这条完整表达式结束时销毁
    t.h.resume();                          // UB: 函数体此时才运行，s 已悬垂
}
```

本机 AddressSanitizer 报告 `stack-use-after-scope`。改成按值接收（`lazy print(std::string s)`）就安全了。`std::string_view`、`std::span`、迭代器这类借用类型也一样：它们本身按值复制，指向的数据却不在协程状态里。

成员函数协程的 `*this` 也不复制（`q_1` 就是 `*this`）。lambda 协程的闭包对象同理，`[x]() -> task<> { co_await …; use(x); }()` 中的临时闭包在完整表达式结束时销毁，之后恢复协程再读 `x` 就是 UB。C++23 起可以用显式对象参数按值接收闭包：`[x](this auto self) -> task<> { … }`，`self` 是普通的按值形参，会移动进协程状态。

## 协程状态的分配（¶9–¶10）

¶9 实现可能需要为协程分配存储，这块存储就是协程状态。它通过调用非数组的分配函数（[[basic.stc.dynamic.allocation]]）取得。分配函数先在 promise 类型的作用域里找：

- ¶9.1 找到了，先用 `(size, p_1, …, p_n)` 做重载决议，这里传的是原始形参，保留原来的 cv；没有可行函数，再只用 `(size)` 试一次；
- ¶9.2 找不到，就用全局的 `operator new(size)`。

条文说的是可能需要。编译器能证明协程状态不会活得比调用者长时，可以把它放进调用者的栈帧，省掉堆分配，这叫**堆分配消除**（heap allocation elision，HALO）。

¶10 如果在 promise 类型里能找到名字 `get_return_object_on_allocation_failure`，分配失败就不再靠异常报告：

- 分配函数失败时返回 `nullptr`；选中的是全局分配函数时，改用 `::operator new(size_t, nothrow_t)`；
- 所用的分配函数必须声明为不抛异常；
- 分配函数返回 `nullptr` 时，协程立即返回调用者，返回值是 `T::get_return_object_on_allocation_failure()` 的结果（`T` 是 promise 类型）。promise 根本没有构造，函数体也不会运行。

这给不使用异常的环境留了一条处理分配失败的路。下面的 promise 从协程的实参里拿到一块 arena，在上面分配协程状态：

```cpp run title="coro-alloc.cpp" ok
#include <coroutine>
#include <cstddef>
#include <cstdio>
#include <exception>

struct arena { char buf[1024]; std::size_t used = 0; };

struct job {
    struct promise_type {
        // ¶9.1：额外实参就是协程的原始形参 (arena&, int)
        static void* operator new(std::size_t n, arena& a, int) noexcept {
            std::printf("arena alloc %zu bytes\n", n);
            if (a.used + n > sizeof a.buf) return nullptr;
            void* p = a.buf + a.used;
            a.used += n;
            return p;
        }
        // ¶12：释放时只传地址和大小
        static void operator delete(void*, std::size_t n) noexcept { std::printf("free %zu bytes\n", n); }
        // ¶10：声明了它，分配函数就用 nullptr 表示失败
        static job get_return_object_on_allocation_failure() { std::puts("allocation failed"); return job{nullptr}; }

        promise_type(arena&, int id) { std::printf("promise ctor sees id=%d\n", id); }  // ¶5.7

        job get_return_object() { return job{std::coroutine_handle<promise_type>::from_promise(*this)}; }
        std::suspend_never initial_suspend() noexcept { return {}; }
        std::suspend_never final_suspend() noexcept { return {}; }   // 结束时协程状态自动销毁
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

本机（Clang 23，arm64，`-O0`）依次输出 `arena alloc 32 bytes`、`promise ctor sees id=7`、`body runs, id=7`、`free 32 bytes`。把 `buf` 改成 16 字节，输出变成 `arena alloc 32 bytes`、`allocation failed`，promise 构造函数和函数体都不执行。协程状态的大小是实现细节，随优化级别变化。

为什么 `operator new` 拿到的是原始形参 `p_i`，promise 构造函数拿到的却是副本 `q_i`？因为分配在复制之前：副本要放进新分配的存储里，分配时它们还不存在。promise 构造在复制之后，这时引用副本才安全，副本和协程活得一样长。

## 协程状态的销毁（¶11–¶12）

¶11 协程状态在两种情况下销毁：

1. 控制流出协程的末尾，也就是最终 await 表达式没有挂起（`final_suspend()` 返回 `suspend_never` 一类的 awaiter），替换体执行完毕；
2. 对指代它的句柄调用 `destroy()`。这时视为控制从函数中转出（[[stmt.dcl]]），活着的自动变量（包括形参副本和 promise 对象）按构造的逆序析构。

存储通过调用非数组的解分配函数释放。对没有挂起的协程调用 `destroy()` 是未定义行为 {{ub}}。

由此得出协程类型的两种所有权模型，只能选一种：

- `final_suspend` 返回 `suspend_never`：协程结束时自动销毁，之后句柄立即失效，`h.done()`、`h.destroy()`、`h.promise()` 都是 UB；
- `final_suspend` 返回 `suspend_always`：协程停在最终挂起点，所有者必须调用 `destroy()`，否则泄漏。上面的 `generator` 用的就是这种。

¶12 解分配函数也是先在 promise 类型里找，找不到再用全局的。两种形式都有时，选带 `(void*, size_t)` 两个形参的那个，并传入块的大小；否则选只有指针形参的那个。一个通常解分配函数都找不到，程序非良构。

和 ¶9 不同，解分配函数收不到协程的形参，销毁时副本已经析构了。所以在 arena 上分配时，要么能从地址反推出 arena，要么在分配时把 arena 指针存在块的开头。

## 流出末尾与异常（¶14–¶15）

流出用户写的函数体末尾时，由 [[stmt.return.coroutine#3]] 决定发生什么：`promise.return_void()` 能调用，就等价于 `co_return;`；否则行为未定义 {{ub}}。所以 promise 只有 `return_value` 的协程（如 `task<int>`）在某条路径上漏写 `co_return x;`，结果不是编译错误而是 UB。Clang 对此给出 `-Wreturn-type` 警告：

```cpp title="flow-off.cpp" ub
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
r f(bool b) {
    if (b) co_return 1;
}              // b 为假时流出末尾：没有 return_void，UB
int main() { f(false); }
```

¶14 如果 `promise.unhandled_exception()` 本身抛出异常而退出，协程视为挂起于最终挂起点，异常传给调用者或恢复者。所以在 `unhandled_exception` 里写 `throw;` 是合法的策略：上面 `generator` 的函数体抛出异常时，异常从 `g.next()` 里的 `h_.resume()` 抛出，协程停在最终挂起点，`~generator()` 之后调用 `destroy()` 仍然合法。

¶15 `co_await promise.final_suspend()` 整个表达式不能是潜在抛出的（[[except.spec]]）。这包括 `final_suspend()` 本身、awaiter 的 `await_ready`、`await_suspend`、`await_resume`，以及 awaiter 的析构。最终 await 表达式在 `try` 块之外，在这里抛出的异常没有地方接住。

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
r f() { co_return; }   // error: co_await promise.final_suspend() 必须不抛异常
```

## 例子：task 等待另一个 task

`generator` 由普通函数驱动。task 类型则让一个协程 `co_await` 另一个协程，被等待的协程结束时直接转回等待者：

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
        std::coroutine_handle<> continuation = std::noop_coroutine();   // 等待者

        task get_return_object() {
            return task{std::coroutine_handle<promise_type>::from_promise(*this)};
        }
        std::suspend_always initial_suspend() noexcept { return {}; }   // 惰性启动
        auto final_suspend() noexcept {
            struct final_awaiter {
                bool await_ready() noexcept { return false; }
                std::coroutine_handle<> await_suspend(std::coroutine_handle<promise_type> h) noexcept {
                    return h.promise().continuation;    // 转回等待者
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

    // 使 task 可以被 co_await（[expr.await]）
    bool await_ready() const noexcept { return false; }
    std::coroutine_handle<> await_suspend(std::coroutine_handle<> awaiting) noexcept {
        h_.promise().continuation = awaiting;
        return h_;                                      // 启动被等待的 task
    }
    T await_resume() {
        if (h_.promise().error) std::rethrow_exception(h_.promise().error);
        return std::move(h_.promise().value);
    }

    T run() {                 // 从普通函数同步驱动（本例所有等待都同步完成）
        h_.resume();
        return await_resume();
    }
private:
    std::coroutine_handle<promise_type> h_;
};

task<int> leaf(int x) { co_return x * 2; }

task<int> sum() {
    int a = co_await leaf(10);   // 挂起 sum，转到 leaf；leaf 结束时转回 sum
    int b = co_await leaf(11);
    co_return a + b;
}

int main() {
    std::printf("%d\n", sum().run());   // 42
}
```

`sum().run()` 恢复 `sum`。`co_await leaf(10)` 先调用 `leaf`，它停在初始挂起点；`task::await_suspend` 把 `sum` 记为 continuation，返回 `leaf` 的句柄，编译器随即恢复这个句柄（[[expr.await#5]]）。`leaf` 执行 `co_return` 后，`final_awaiter` 返回 continuation，控制转回 `sum`。`sum` 的 continuation 是 `noop_coroutine()`，所以 `sum` 结束时控制回到 `run()`。

`await_suspend` 返回句柄的写法叫**对称转移**（symmetric transfer）。编译器以尾调用的方式恢复返回的句柄，两个协程来回切换不会让栈越来越深。

!!! impl "Clang 怎样实现协程"
    - LLVM 把一个协程拆成三个函数。ramp 函数就是调用者看到的那个函数：分配协程状态、复制形参、构造 promise、调用 `get_return_object` 和 `initial_suspend`，第一次挂起时返回。resume 和 destroy 函数按状态里保存的挂起点编号跳到对应位置。
    - 协程状态的开头是 resume 和 destroy 两个函数指针，接着是 promise 对象，然后是跨挂起点存活的局部变量、形参副本和挂起点编号。GCC 用同样的约定。`coroutine_handle<>` 因此不必知道 promise 类型就能恢复和销毁协程，`from_promise` 和 `promise()` 用固定偏移在两个地址之间换算。
    - 优化时（如 `-O2`），如果协程状态不逃出调用者，例如调用者创建 generator 并在本函数内用完、析构，Clang 会消除 `operator new` 和 `operator delete`，把状态放进调用者的栈帧，即前面说的 HALO。

## 历史与演进

!!! history
    - 协程先以 Coroutines TS（ISO/IEC TS 22277:2017）的形式发布，在 MSVC 和 Clang 中以 `std::experimental` 实现了多年，C++20 通过 [[P0912R5]] 并入标准。
    - C++23 在标准库中加入 `std::generator`（[[coro.generator]]）。
    - C++26 引入契约，相应地禁止在协程的后置条件中 odr-use 非引用形参（¶6）；`std::execution` 中加入了协程 task 类型 `std::execution::task`（[[exec.task]]）。

## 常见误解

!!! pitfall "看声明就能知道函数是不是协程"
    不能。协程是函数体的属性。同一个声明 `task<int> f(int);` 的定义可以是协程，也可以是一个返回现成 `task` 的普通函数。

!!! pitfall "const 引用形参在协程里也安全"
    绑定到引用形参的临时对象只活到调用所在的完整表达式结束（[[class.temporary]]）。惰性协程恢复时，那个临时对象早就没了。会挂起的协程应当按值接收形参。

!!! pitfall "漏写 co_return 会被编译器拒绝"
    promise 没有 `return_void` 时，流出函数体末尾是 UB，编译器只给警告。建议用 `-Werror=return-type`。

## 思考题

!!! question "思考题 1"
    下面的协程被调用时，各步骤的顺序是什么？
    ```cpp
    task<int> f(Widget w);   // promise_type 有构造函数 promise_type(Widget&)
    ```

<details markdown="1">
<summary>答案</summary>

1. 调用者构造实参 `w`，即原始形参；
2. 调用分配函数取得协程状态（¶9；若 promise 有 `operator new(size_t, Widget&)`，原始形参作为额外实参传入）；
3. 用指代原始 `w` 的 xvalue 把它移动构造进协程状态（¶13.2）；
4. 用形参副本构造 promise，`promise_type(Widget&)` 可行，于是以副本为实参（¶5.7）；
5. 调用 `get_return_object()`，结果用来初始化返回给调用者的 `task<int>`（¶7）；
6. 求值 `co_await promise.initial_suspend()`，如果挂起，控制回到调用者；
7. 调用者在完整表达式结束时析构原始形参 `w`，协程状态里的副本不受影响。
</details>

!!! question "思考题 2"
    在协程体内对自己的句柄调用 `h.resume()` 会怎样？如果 `final_suspend` 返回 `suspend_never`，协程结束后调用 `h.done()` 呢？

<details markdown="1">
<summary>答案</summary>

都是未定义行为。前者是对正在运行、没有挂起的协程调用恢复函数（¶8）。后者协程状态已经随流出末尾销毁（¶11），句柄不再指代任何协程，[[coroutine.handle.observers]] 要求调用 `done()` 时句柄指代一个挂起的协程。
</details>
