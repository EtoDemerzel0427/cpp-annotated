---
title: 其他运行时支持
summary: 来自 C 的运行时设施在 C++ 中的额外限制——getenv/setlocale 的数据竞争、<cstdarg> 的默认实参提升与 va_start、setjmp/longjmp 跳过非平凡析构即 UB、<csignal>，以及信号处理函数中"信号安全"的精确定义
status: done
covers: *
related: expr.call, except.throw, except.ctor, expr.await, intro.races, atomics, basic.start.dynamic, stmt.dcl, support.start.term, res.on.data.races
tags: 标准库, setjmp, longjmp, 信号, 可变参数, UB
updated: 2026-10-18
---

C++ 从 C 继承了一批"底层运行时"设施：可变参数、非局部跳转、信号。它们在 C 里工作得好好的，但 C++ 有析构函数、异常、线程、协程——C 的规则不足以回答"`longjmp` 跳过了一个 `std::string` 会怎样""信号处理函数里能不能 `new`"这类问题。本节就是 C++ 对这些设施附加的规则，几乎每一条都是对 C 语义的**收紧**。

## 总则（[support.runtime.general]）

¶1：`<csetjmp>`（非局部跳转）、`<csignal>`（信号处理）、`<cstdarg>`（可变参数）和 `<cstdlib>`（运行时环境 `getenv`、`system`）进一步提供与 C 代码的兼容性。

¶2：只要没有东西修改环境，对 `getenv` 的调用就**不得**引入数据竞争（[[res.on.data.races]]）。注 1：POSIX 函数 `setenv` 和 `putenv` 会修改环境。——也就是说，`getenv` 本身是线程安全的，但它与 `setenv` 并发就是数据竞争。实践中这是多线程程序里一个常见的崩溃来源：某个第三方库在后台线程里调用了 `setenv`。

¶3：对 `setlocale` 的调用**可能**与其他 `setlocale` 调用、或受当前 C locale 影响的函数（`printf`、`isalpha`、`strtod`……）的调用产生数据竞争。实现的行为必须如同**除了 `locale::global` 之外没有任何库函数调用 `setlocale`**——标准库不会在你背后偷偷改 C locale。

## `<cstdarg>`：可变参数（[cstdarg.syn]）

```cpp
namespace std { using va_list = /* see below */; }
#define va_arg(V, P)        /* see below */
#define va_copy(VDST, VSRC) /* see below */
#define va_end(V)           /* see below */
#define va_start(V, ...)    /* see below */
```

整个头文件是 freestanding 的。¶1：内容与 C 的 `<stdarg.h>` 相同，但有两处修改：

¶1.1：用 C++ 的 [[expr.call]] 中的定义**取代** C 标准中的**默认实参提升**。两者大体一致（`float` → `double`，小于 `int` 的整数类型做整型提升），但 C++ 版本还规定了 C 中不存在的类型如何处理：

- `std::nullptr_t` 被转换为 `void*`；
- 传递**作用域枚举**类型的实参，或者具有合格的非平凡复制构造函数、合格的非平凡移动构造函数或非平凡析构函数的类类型实参，是**有条件支持**的，语义由实现定义（[[expr.call#13]]）。对非平凡类类型，Clang 的选择是报错（`-Wnon-pod-varargs`，默认为错误），并说明"call will abort at runtime"。

¶1.2：`va_start` 的签名是 `va_start(V, ...)`（C23 风格）。若提供了多于一个实参，且第二个及之后的实参展开后含有不配对的括号，或含有无法转换为记号的预处理记号，**程序非良构，不要求诊断**。第二个及之后的实参的预处理记号**被丢弃**。注 1：`va_start` 接受第二个实参是为了与 C++ 之前的版本兼容。

这意味着按照当前草案，`va_start(ap)` 就够了，不再需要写出最后一个具名形参——这对 `void f(...)` 这种**没有具名形参**的可变参数函数尤其重要，以前它根本无法使用 `va_start`。

!!! impl "Clang 的 C++ 模式尚未支持单实参 `va_start`"
    Clang 资源目录的 `__stdarg_va_arg.h` 只在 `__STDC_VERSION__ >= 202311L`（即 C23 模式）下把 `va_start` 定义为变参宏 `__builtin_c23_va_start(__VA_ARGS__)`；在 C++ 模式下仍是 `va_start(ap, param)`，所以 `va_start(ap)` 报"too few arguments provided to function-like macro invocation"。截至本文编写时，可移植的写法仍是两个实参。

```cpp run title="va-args.cpp" ok
#include <cstdarg>

int sum(int count, ...) {
    std::va_list ap;
    va_start(ap, count);          // 第二个实参：按当前草案会被丢弃；Clang 目前仍要求它
    int s = 0;
    for (int i = 0; i < count; ++i)
        s += va_arg(ap, int);     // char、short 实参已被默认实参提升为 int
    va_end(ap);
    return s;
}

double avg(int n, ...) {
    std::va_list ap;
    va_start(ap, n);
    double s = 0;
    for (int i = 0; i < n; ++i)
        s += va_arg(ap, double);  // float 实参被提升为 double：这里不能写 va_arg(ap, float)
    va_end(ap);
    return s / n;
}

int main() {
    char c = 1; short h = 2;
    return (sum(3, c, h, 3) == 6 && avg(2, 1.0f, 3.0) == 2.0) ? 0 : 1;
}
```

!!! pitfall "`va_arg` 的类型必须与提升后的实参类型一致"
    `va_arg(ap, T)` 中 `T` 与实际（提升后的）实参类型不兼容时，行为未定义（C 的规则）。最常见的错误是 `va_arg(ap, float)`、`va_arg(ap, char)`——它们永远不可能正确。在 C++ 中，可变参数模板（[[temp.variadic]]）几乎总是更好的选择：类型安全、可以传任何类型。

## `<csetjmp>`：非局部跳转（[csetjmp.syn]）

```cpp
namespace std {
  using jmp_buf = /* see below */;
  [[noreturn]] void longjmp(jmp_buf env, int val);
}
#define setjmp(env) /* see below */
```

¶1：内容与 C 的 `<setjmp.h>` 相同。¶2 是 C++ 最重要的附加限制：

!!! std
    A `setjmp`/`longjmp` call pair has undefined behavior if replacing the `setjmp` and `longjmp` by `catch` and `throw` would invoke any non-trivial destructors for any objects with automatic storage duration. A call to `setjmp` or `longjmp` has undefined behavior if invoked in a suspension context of a coroutine.

    如果把 `setjmp` 和 `longjmp` 替换成 `catch` 和 `throw` 会调用任何自动存储期对象的**非平凡析构函数**，则这对 `setjmp`/`longjmp` 调用具有**未定义行为**。在协程的**挂起语境**中调用 `setjmp` 或 `longjmp` 是未定义行为。

这条规则的判定方法很巧妙：**做一个思想实验**——如果把 `longjmp` 换成 `throw`、把 `setjmp` 所在处换成 `catch`，栈回溯（[[except.ctor]]）沿途会析构哪些对象？如果其中有任何一个析构函数是非平凡的，那么 `longjmp` 就是 UB。

为什么是 UB 而不是"跳过析构"？因为 `longjmp` 的实现只是恢复寄存器（栈指针、程序计数器、被调用者保存寄存器），它对 C++ 对象一无所知。跳过析构函数意味着 `std::string` 的堆内存泄漏、`std::lock_guard` 的锁永不释放、`std::unique_ptr` 的资源丢失——而更糟的是，有些平台（例如 Windows 的 MSVC）的 `longjmp` 实际上**会**执行栈回溯并调用析构函数。标准不想规定任何一种行为，所以干脆定为 UB。

```cpp run title="setjmp-ok.cpp" ok
#include <csetjmp>
#include <cstdio>

std::jmp_buf env;

void fail() { std::longjmp(env, 1); }

int main() {
    if (setjmp(env) == 0) {
        int x = 42;                  // 平凡析构：换成 throw/catch 也不会调用任何非平凡析构函数
        (void)x;
        fail();
    } else {
        std::puts("jumped back");    // OK
    }
}
```

```cpp run title="setjmp-ub.cpp" ub
#include <csetjmp>
#include <string>

std::jmp_buf env;

void fail() { std::longjmp(env, 1); }

void work() {
    std::string s = "this string owns heap memory";
    fail();                          // UB：换成 throw 会调用 s 的非平凡析构函数
}

int main() {
    if (setjmp(env) == 0) work();
}
```

还有几条来自 C 的限制在 C++ 中照样适用：

- `setjmp` 只能出现在特定语境中（`if`/`switch`/循环的整个条件、与整型常量比较、或作为表达式语句），把它的返回值存进变量是 UB。
- `setjmp` 所在函数中的**非 `volatile` 自动变量**，若在 `setjmp` 与 `longjmp` 之间被修改，`longjmp` 之后其值是不确定的。
- 跳回一个**已经返回**的函数中的 `jmp_buf` 是 UB。

¶2 的第二句针对协程：在协程的**挂起语境**（[[expr.await]]，即可以出现 `co_await` 的协程函数体内）调用 `setjmp`/`longjmp` 是 UB。协程帧可能在堆上，挂起点会把控制交回调用者，`jmp_buf` 保存的栈状态与协程的执行模型完全不兼容。

!!! tip "在 C++ 中用异常替代 `longjmp`"
    `setjmp`/`longjmp` 唯一合理的使用场景是与 C 库交互（例如 libpng、libjpeg 的错误处理，Lua 的 C API）。即使如此，也要确保 `setjmp` 与 `longjmp` 之间的所有 C++ 帧都只含平凡析构的对象——通常的做法是在一个极薄的 C 风格包装函数里调用 `setjmp`，跳回后再在 C++ 层面 `throw` 一个异常。

## `<csignal>`（[csignal.syn]）

```cpp
namespace std {
  using sig_atomic_t = /* see below */;
  extern "C" using signal-handler = void(int);       // 仅用于说明
  signal-handler* signal(int sig, signal-handler* func);
  int raise(int sig);
}
// SIG_DFL, SIG_ERR, SIG_IGN, SIGABRT, SIGFPE, SIGILL, SIGINT, SIGSEGV, SIGTERM
```

¶1：内容与 C 的 `<signal.h>` 相同。注意信号处理函数的类型是 `extern "C"` 的函数类型——严格来说，传一个 C++ 语言链接的函数给 `signal` 是类型不匹配的（[[dcl.link]]）；主流编译器不区分语言链接，所以实践中可以工作，但最严谨的写法是把处理函数声明为 `extern "C"`。

## 信号处理函数（[support.signal]）

### 同步（¶1）

¶1：对 `signal` 的调用**同步于**（synchronizes with，[[intro.races]]）由此安装的信号处理函数的任何一次调用。所以在调用 `signal` 之前写入的数据，在处理函数中是可见的。

### 普通无锁原子操作（¶2）

¶2 定义**普通无锁原子操作**（[[g:plain-lock-free-atomic-operation]]）：对 [[atomics]] 中某个函数 `f` 的调用，满足以下之一：

- ¶2.1 `f` 是 `atomic_is_lock_free()`；¶2.2 `f` 是成员函数 `is_lock_free()`；
- ¶2.3 `f` 是 `atomic_flag` 的非静态成员函数；¶2.4 `f` 是非成员函数，且第一个形参类型为 *cv* `atomic_flag*`；
- ¶2.5 `f` 是在对象 `A` 上调用的非静态成员函数，且 `A.is_lock_free()` 为 `true`；
- ¶2.6 `f` 是非成员函数，且对传给 `f` 的每个指向原子对象的实参 `A`，`atomic_is_lock_free(A)` 为 `true`。

`atomic_flag` 无条件入选，因为标准保证它的操作总是无锁的（[[atomics.flag]]）；其他原子类型要看具体对象是否无锁。

### 信号安全（¶3）

!!! std
    An evaluation is *signal-safe* unless it includes one of the following: ... A signal handler invocation has undefined behavior if it includes an evaluation that is not signal-safe.

    一个求值是**信号安全**的，除非它包含下列之一……信号处理函数的调用如果包含非信号安全的求值，行为未定义。

一个求值**不是**信号安全（[[g:signal-safe]]）的，如果它包含：

| ¶ | 不安全的操作 | 原因 |
|---|---|---|
| ¶3.1 | 调用任何标准库函数，**除了**普通无锁原子操作和明确标注为信号安全的函数 | 库函数可能持有锁（`malloc`、`printf`）；信号打断持锁的线程后再次加锁即死锁。注 1：这隐式地排除了依赖库提供的分配器的 `new` 和 `delete` 表达式 |
| ¶3.2 | 访问线程存储期对象 | 访问 `thread_local` 可能需要惰性初始化或调用 `__tls_get_addr`，后者可能分配内存 |
| ¶3.3 | `dynamic_cast` 表达式 | 运行时库实现可能不是异步信号安全的 |
| ¶3.4 | 抛出异常 | 栈回溯器不是异步信号安全的，而且信号帧不一定有回溯信息 |
| ¶3.5 | 控制进入 *try-block* 或 *function-try-block* | 同上，保守起见 |
| ¶3.6 | 需要**动态初始化**的静态存储期变量的初始化（[[basic.start.dynamic]]、[[stmt.dcl]]） | 脚注 170：这可能因为它是该变量的第一次 odr-use 而发生；局部静态变量的初始化需要加锁（[[stmt.dcl]] 的线程安全保证） |
| ¶3.7 | 等待某个静态存储期变量的初始化完成 | 同上：如果被打断的线程正持有该初始化锁，处理函数将永远等下去 |

"明确标注为信号安全的函数"散布在标准各处，本章就有不少：`_Exit`、`abort`（[[support.start.term]]）、`quick_exit`（当注册的回调都安全时）、`numeric_limits` 的所有成员函数（[[numeric.limits.members]]）、`initializer_list` 的所有函数（[[support.initlist]]）；以及 `<type_traits>` 中的所有函数（[[meta]]）、`std::forward`/`std::move` 等（[[forward]]）。

¶4：`signal` 函数本身，当以**引发当前处理函数调用的那个信号编号**为第一个实参调用时，是信号安全的——这允许处理函数重新安装自己（有些系统在调用处理函数前把处理方式重置为 `SIG_DFL`）。

```cpp run title="signal-handler.cpp" ok
#include <atomic>
#include <csignal>
#include <cstdio>

volatile std::sig_atomic_t flag = 0;               // C 风格：volatile sig_atomic_t
std::atomic<int> counter{0};
static_assert(std::atomic<int>::is_always_lock_free);   // ¶2.5 要求：对象是无锁的

extern "C" void handler(int sig) {
    flag = 1;                                      // OK：对 volatile sig_atomic_t 赋值
    counter.fetch_add(1, std::memory_order_relaxed);   // OK：普通无锁原子操作
    std::signal(sig, handler);                     // OK：¶4，以当前信号编号调用
    // std::printf("got signal\n");                // UB：printf 不是信号安全的
    // throw 1;                                    // UB：¶3.4
}

int main() {
    std::signal(SIGINT, handler);
    std::raise(SIGINT);                            // 同步地触发处理函数
    std::printf("%d %d\n", int(flag), counter.load());   // 1 1
}
```

!!! note "C++ 的“信号安全”与 POSIX 的“异步信号安全”"
    标准的信号安全列表比 POSIX 的"异步信号安全函数"列表**窄得多**：POSIX 允许在处理函数中调用 `write`、`_exit` 等系统调用，而 C++ 标准对这些非标准函数什么也不说（它们不是"标准库函数"，所以 ¶3.1 不禁止它们，其安全性由 POSIX 规定）。实践中，Unix 上的信号处理函数通常只做三件事之一：设置一个原子标志、向一个 self-pipe 写一个字节、或者调用 `_exit`。

## 小结

!!! summary
    - `getenv` 与修改环境的操作并发即数据竞争；标准库内部不会调用 `setlocale`（除 `locale::global`）。
    - `<cstdarg>`：用 C++ 的默认实参提升；`va_start` 的第二个及之后的实参被丢弃（Clang 的 C++ 模式尚未支持单实参形式）；传非平凡类类型是有条件支持的。
    - `longjmp`：若换成 `throw`/`catch` 会调用任何非平凡析构函数，则为 UB；在协程挂起语境中调用 `setjmp`/`longjmp` 为 UB。
    - 信号处理函数中只能做信号安全的求值：普通无锁原子操作、明确标注为信号安全的库函数；不能访问 `thread_local`、`dynamic_cast`、抛异常、进入 try 块、触发静态变量的动态初始化。
    - `signal` 的调用同步于处理函数的调用；处理函数可以用当前信号编号重新调用 `signal`。
