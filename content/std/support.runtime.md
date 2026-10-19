---
title: 其他运行时支持
summary: C++ 对从 C 继承的运行时设施附加的规则：getenv 和 setlocale 的数据竞争、<cstdarg> 的实参提升和 va_start、longjmp 跳过非平凡析构函数即为 UB，以及信号处理函数里哪些操作是信号安全的。
status: done
covers: *
related: expr.call, except.throw, except.ctor, expr.await, intro.races, atomics, basic.start.dynamic, stmt.dcl, support.start.term, res.on.data.races
tags: 标准库, setjmp, longjmp, 信号, 可变参数, UB
updated: 2026-10-19
---

!!! tldr
    - `getenv` 本身不引入数据竞争，但和 `setenv`、`putenv` 并发就是数据竞争。
    - 用 `va_arg` 取可变参数时，类型要写提升之后的类型：`float` 要按 `double` 取，`char`、`short` 要按 `int` 取。
    - 把 `setjmp`/`longjmp` 换成 `catch`/`throw` 后，如果会调用某个自动对象的非平凡析构函数，这次 `longjmp` 就是 UB。
    - 信号处理函数里只能做信号安全的事：无锁原子操作、少数标明信号安全的库函数；不能调用 `printf`、`new`，不能抛异常，不能访问 `thread_local`。

C++ 从 C 继承了可变参数、非局部跳转和信号这几样运行时设施。C 的规则不涉及析构函数、异常、线程和协程，回答不了 `longjmp` 跳过一个 `std::string` 会怎样、信号处理函数里能不能 `new` 这类问题。本节就是 C++ 为它们附加的规则，大多是对 C 语义的收紧。

## 环境变量和 locale [support.runtime.general]

¶1 `<csetjmp>`（非局部跳转）、`<csignal>`（信号处理）、`<cstdarg>`（可变参数）和 `<cstdlib>` 中的运行时环境函数（`getenv`、`system`）用于与 C 代码兼容。

¶2 只要没有东西修改环境，调用 `getenv` 就不会引入数据竞争（[[res.on.data.races]]）。注 1 指出，POSIX 的 `setenv` 和 `putenv` 会修改环境。所以一个线程调用 `getenv`、另一个线程同时调用 `setenv`，就是数据竞争。多线程程序里这是一个常见的崩溃原因，比如某个第三方库在后台线程里调用了 `setenv`。

¶3 调用 `setlocale` 可能与其他 `setlocale` 调用发生数据竞争，也可能与受当前 C locale 影响的函数（`printf`、`isalpha`、`strtod` 等）发生数据竞争。实现的行为必须如同除了 `locale::global` 之外，没有任何库函数调用 `setlocale`。也就是说，标准库不会在程序不知情时改动 C locale。

## 可变参数 [cstdarg.syn]

```cpp run title="va-args.cpp" ok
#include <cstdarg>

int sum(int count, ...) {
  std::va_list ap;
  va_start(ap, count);   // 按草案第二个实参会被丢弃；Clang 仍要求写
  int s = 0;
  for (int i = 0; i < count; ++i)
    s += va_arg(ap, int);   // char、short 已被提升为 int
  va_end(ap);
  return s;
}

double avg(int n, ...) {
  std::va_list ap;
  va_start(ap, n);
  double s = 0;
  for (int i = 0; i < n; ++i)
    s += va_arg(ap, double);   // float 已被提升为 double
  va_end(ap);
  return s / n;
}

int main() {
  char c = 1;
  short h = 2;
  return (sum(3, c, h, 3) == 6 && avg(2, 1.0f, 3.0) == 2.0) ? 0 : 1;
}
```

¶1 `<cstdarg>` 的内容与 C 的 `<stdarg.h>` 相同，整个头文件是 freestanding 的。C++ 改了两处。

### 默认实参提升（¶1.1）

¶1.1 默认实参提升用 C++ 的定义（[[expr.call#13]]），不用 C 的定义。实参传给 `...` 时，`float` 提升为 `double`，比 `int` 小的整数类型做整型提升，这一点和 C 一样。所以 `va_arg(ap, float)`、`va_arg(ap, char)` 永远不可能正确：`va_arg` 写的类型和提升后的实参类型不兼容时，行为未定义。

C++ 还规定了 C 里没有的几种类型：

- `std::nullptr_t` 的实参转换为 `void*`；
- 作用域枚举类型的实参，以及有合格的非平凡复制构造函数、合格的非平凡移动构造函数或非平凡析构函数的类类型实参，是**有条件支持**的，也就是实现可以不支持，支持时语义由实现定义。

对 `std::string` 这样的类型，Clang 选择不支持，给出一个默认即为错误的诊断：

```cpp error
#include <string>
void v(int, ...);
void f(std::string s) { v(0, s); }   // error: 不能把非平凡类型传给 ...
```

诊断原文是 `cannot pass object of non-trivial type 'std::string' ... through variadic function; call will abort at runtime [-Wnon-pod-varargs]`。

在 C++ 里，可变参数模板（[[temp.variadic]]）几乎总是更好的选择：它类型安全，什么类型都能传。

### `va_start` 只需要一个实参（¶1.2）

```cpp
#define va_start(V, ...) see below
```

¶1.2 按当前草案，`va_start` 和 C23 一样只需要一个实参，`va_start(ap)` 就够了，不必再写最后一个具名形参。如果写了第二个及之后的实参，它们的预处理记号会被丢弃；但这些实参展开后含有不配对的括号，或者含有不能转换成记号的预处理记号时，程序是 IFNDR，即非良构而不要求诊断。注 1 说明，保留第二个实参是为了兼容旧版 C++ 的写法。

这对 `void f(...)` 这种没有具名形参的函数尤其有用，以前它根本没法用 `va_start`。

!!! impl "Clang 的 C++ 模式还不支持单实参 `va_start`"
    Clang 的 `<stdarg.h>` 只在 C23 模式（`__STDC_VERSION__ >= 202311L`）下把 `va_start` 定义成变参宏；在 C++ 模式下它仍是 `va_start(ap, param)`，`va_start(ap)` 会报错 `too few arguments provided to function-like macro invocation`。截至写作时，可移植的写法仍然是写两个实参。

## 非局部跳转 [csetjmp.syn]

```cpp
namespace std {
  using jmp_buf = see below;
  [[noreturn]] void longjmp(jmp_buf env, int val);
}
#define setjmp(env) see below
```

¶1 `<csetjmp>` 的内容与 C 的 `<setjmp.h>` 相同。

### 跳过非平凡析构函数是 UB（¶2）

<div class="compare" markdown="1">

```cpp run ok
#include <csetjmp>
#include <cstdio>

std::jmp_buf env;
void fail() { std::longjmp(env, 1); }

int main() {
  if (setjmp(env) == 0) {
    int x = 42;   // 平凡析构
    (void)x;
    fail();
  } else {
    std::puts("jumped back");
  }
}
```

```cpp run ub
#include <csetjmp>
#include <string>

std::jmp_buf env;
void fail() { std::longjmp(env, 1); }

void work() {
  std::string s = "this string owns heap memory";
  fail();   // UB：换成 throw 会调用 s 的析构函数
}

int main() {
  if (setjmp(env) == 0) work();
}
```

</div>

!!! std
    A `setjmp`/`longjmp` call pair has undefined behavior if replacing the `setjmp` and `longjmp` by `catch` and `throw` would invoke any non-trivial destructors for any objects with automatic storage duration.

¶2 判断方法是一个思想实验：把 `longjmp` 换成 `throw`，把 `setjmp` 所在处换成 `catch`，然后看栈回溯（[[except.ctor]]）沿途要析构哪些自动对象。只要其中有一个析构函数是非平凡的，这次 `longjmp` 就是 UB。左边的 `x` 是 `int`，没有非平凡析构函数，所以没有问题；右边跳过了 `s` 的析构函数。

为什么定为 UB，而不规定跳过析构？`longjmp` 的典型实现只是恢复几个寄存器（栈指针、程序计数器、被调用者保存的寄存器），对 C++ 对象一无所知。跳过析构函数意味着 `std::string` 的堆内存泄漏、`std::lock_guard` 的锁永远不释放。另一方面，有的平台（例如 Windows 上的 MSVC）的 `longjmp` 会做栈回溯并调用析构函数。标准不想规定其中任何一种，所以定为 UB。

¶2 的第二句针对协程：在协程的**挂起语境**（suspension context，函数体中可以出现 `co_await` 的位置，见 [[expr.await]]）调用 `setjmp` 或 `longjmp`，行为未定义。协程帧可能在堆上，挂起时控制会交回调用者，`jmp_buf` 保存的栈状态和协程的执行方式不相容。

### 来自 C 的限制

C 的几条限制在 C++ 中照样适用：

- `setjmp` 只能出现在几种语境中：`if`、`switch` 或循环的整个条件，与整数常量表达式比较，`!setjmp(env)`，或者单独作为表达式语句。把它的返回值存进变量是 UB。
- 在 `setjmp` 所在的函数里，非 `volatile` 的自动变量如果在 `setjmp` 和 `longjmp` 之间被修改过，`longjmp` 之后它的值是不确定的。
- `setjmp` 所在的函数已经返回后，再 `longjmp` 回那个 `jmp_buf`，是 UB。

!!! tip "在 C++ 里用异常代替 `longjmp`"
    `setjmp`/`longjmp` 在 C++ 中唯一合理的用途是与用它报告错误的 C 库交互，例如 libpng、libjpeg 和 Lua 的 C API。这时要确保 `setjmp` 和 `longjmp` 之间的 C++ 栈帧里只有平凡析构的对象。通常的做法是在一个很薄的 C 风格包装函数里调用 `setjmp`，跳回来之后再在 C++ 层面抛出异常。

## 信号 [csignal.syn] [support.signal]

```cpp
namespace std {
  using sig_atomic_t = see below;
  extern "C" using signal-handler = void(int);   // 仅用于说明
  signal-handler* signal(int sig, signal-handler* func);
  int raise(int sig);
}
// 另有宏 SIG_DFL、SIG_ERR、SIG_IGN、SIGABRT、SIGFPE、SIGILL、SIGINT、SIGSEGV、SIGTERM
```

[csignal.syn] ¶1 `<csignal>` 的内容与 C 的 `<signal.h>` 相同。处理函数的类型是 `extern "C"` 的函数类型，所以严格地说，把一个 C++ 语言链接的函数传给 `signal` 是类型不匹配的（[[dcl.link]]）。主流编译器不区分函数类型的语言链接，实践中这样写也能工作，但最严谨的写法是把处理函数声明为 `extern "C"`。

```cpp run title="signal-handler.cpp" ok
#include <atomic>
#include <csignal>
#include <cstdio>

volatile std::sig_atomic_t flag = 0;
std::atomic<int> counter{0};
static_assert(std::atomic<int>::is_always_lock_free);

extern "C" void handler(int sig) {
  flag = 1;                                         // OK
  counter.fetch_add(1, std::memory_order_relaxed);  // OK：普通无锁原子操作
  std::signal(sig, handler);                        // OK：¶4
  // std::printf("got signal\n");                   // UB：printf 不是信号安全的
  // throw 1;                                       // UB：¶3.4
}

int main() {
  std::signal(SIGINT, handler);
  std::raise(SIGINT);   // 同步地触发处理函数
  std::printf("%d %d\n", int(flag), counter.load());   // 1 1
}
```

### 信号安全（¶3）

!!! std
    A signal handler invocation has undefined behavior if it includes an evaluation that is not signal-safe.

[support.signal] ¶3 信号处理函数的一次调用如果包含不是**信号安全**（[[g:signal-safe]]）的求值，行为未定义。一个求值只要包含下面任何一项，就不是信号安全的：

| ¶ | 不安全的操作 | 原因 |
|---|---|---|
| ¶3.1 | 调用标准库函数，普通无锁原子操作（见下文）和明确标为信号安全的函数除外 | 库函数可能持有锁，例如 `malloc`、`printf`。信号打断了持锁的线程，处理函数再加同一把锁就会死锁。注 1 指出，这也排除了使用库提供的分配器的 `new` 和 `delete` 表达式 |
| ¶3.2 | 访问线程存储期对象 | 访问 `thread_local` 可能触发惰性初始化或调用 `__tls_get_addr`，后者可能分配内存 |
| ¶3.3 | `dynamic_cast` 表达式 | 运行时库的实现不一定能在信号中安全执行 |
| ¶3.4 | 抛出异常 | 栈回溯器不是异步信号安全的，信号帧也不一定有回溯信息 |
| ¶3.5 | 控制进入 *try-block* 或 *function-try-block* | 与上一条同理 |
| ¶3.6 | 需要动态初始化的静态存储期变量的初始化（[[basic.start.dynamic]]、[[stmt.dcl]]） | 脚注说明，这可能因为处理函数第一次 odr-use 这个变量而发生；局部静态变量的初始化要加锁 |
| ¶3.7 | 等待某个静态存储期变量初始化完成 | 被打断的线程如果正持有初始化锁，处理函数会永远等下去 |

明确标为信号安全的函数分散在标准各处，例如 `_Exit`、`abort`、注册的回调都信号安全时的 `quick_exit`（[[support.start.term]]），`numeric_limits` 的全部成员函数（[[numeric.limits.members]]），`initializer_list` 的全部函数（[[support.initlist]]），`<type_traits>` 中的函数（[[type.traits.general]]），以及 `std::forward`、`std::move` 等（[[forward]]）。

### 普通无锁原子操作（¶2）

¶2 **普通无锁原子操作**（[[g:plain-lock-free-atomic-operation]]）是对 [[atomics]] 中某个函数 `f` 的调用，并且满足下列之一：

- ¶2.1 `f` 是 `atomic_is_lock_free()`，或者 ¶2.2 `f` 是成员函数 `is_lock_free()`；
- ¶2.3 `f` 是 `atomic_flag` 的非静态成员函数，或者 ¶2.4 `f` 是第一个形参类型为 *cv* `atomic_flag*` 的非成员函数；
- ¶2.5 `f` 是在对象 `A` 上调用的非静态成员函数，而 `A.is_lock_free()` 为 `true`；
- ¶2.6 `f` 是非成员函数，而对传给 `f` 的每个指向原子对象的实参 `A`，`atomic_is_lock_free(A)` 都为 `true`。

`atomic_flag` 无条件入选，因为它的操作保证是无锁的（[[atomics.flag]]）。其他原子类型要看具体对象是否无锁，上例用 `static_assert(std::atomic<int>::is_always_lock_free)` 确认了这一点。

### 同步和重新安装（¶1、¶4）

¶1 调用 `signal` 同步于（synchronizes with，[[intro.races]]）由此安装的处理函数的每一次调用。所以调用 `signal` 之前写入的数据，在处理函数里是可见的。

¶4 如果第一个实参等于引发这次处理函数调用的信号编号，在处理函数中调用 `signal` 是信号安全的。这允许处理函数重新安装自己；有些系统在调用处理函数之前会把处理方式重置为 `SIG_DFL`。

!!! note "C++ 的信号安全与 POSIX 的异步信号安全"
    POSIX 有自己的异步信号安全函数列表，允许在处理函数中调用 `write`、`_exit` 等系统调用。C++ 标准不管这些函数：它们不是标准库函数，¶3.1 不禁止它们，它们是否安全由 POSIX 规定。实践中，Unix 上的信号处理函数通常只做三件事之一：设置一个原子标志，向一个 self-pipe 写一个字节，或者调用 `_exit`。
