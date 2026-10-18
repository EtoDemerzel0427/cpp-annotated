---
title: co_await
summary: co_await 表达式如何由操作数一步步得到 awaiter（await_transform → operator co_await → 临时量实质化），await_ready / await_suspend / await_resume 的求值顺序与 await_suspend 三种返回类型（void、bool、coroutine_handle 对称转移）的语义，以及 co_await 可以出现的位置
status: draft
since: c++20
papers: P0912R5, P0913R1
related: dcl.fct.def.coroutine, expr.yield, stmt.return.coroutine, coroutine.handle, support.coroutine, over.match.oper, class.temporary
tags: 协程, co_await, awaiter, 对称转移
updated: 2026-10-17
---

{{c++20}} `co_await e` 是协程的"暂停点制造器"：它把当前协程**挂起**，把控制权交还给调用者或恢复者（resumer），等到某个时刻有人通过 `std::coroutine_handle` 恢复它时，再从这里继续，并把 `e` 所代表的计算的结果作为整个表达式的值。

与 `throw` 或函数调用不同，`co_await` 的语义几乎完全是**由库定制的**：标准只规定了一个固定的"展开模板"——先从操作数得到一个 **awaiter** 对象，再依次调用它的三个成员 `await_ready`、`await_suspend`、`await_resume`。awaiter 上这三个函数的返回类型和行为决定了"要不要挂起"、"挂起之后交给谁"、"恢复之后得到什么"。理解本节就是理解这个模板的每一个分支。

预备知识：协程的定义、promise 对象、协程状态与"替换函数体"见 [[dcl.fct.def.coroutine]]；`co_yield` 是 `co_await promise.yield_value(e)` 的语法糖，见 [[expr.yield]]；`co_return` 见 [[stmt.return.coroutine]]；`std::coroutine_handle` 见 [[coroutine.handle]]。

## 作用与文法（¶1）

¶1 *await-expression* 的形式是 `co_await cast-expression`，所以 `co_await` 与其他一元运算符同优先级：`co_await a + b` 是 `(co_await a) + b`，`co_await f().g()` 是 `co_await (f().g())`。

**一个函数只要函数体里出现了 `co_await`（或 `co_yield`、`co_return`），它就是协程**（[[dcl.fct.def.coroutine#1]]）。不存在"声明为协程"的语法，是否是协程是函数定义的属性，调用者看不出来。

## 可以出现在哪里：挂起语境（¶2）

¶2 `co_await` 只能作为**潜在求值**的表达式，出现在函数体或 lambda 的 *compound-statement* 中，并且：

- **不能在异常处理器（*handler*，即 `catch` 块）里**；
- 在声明语句中，只能出现在**初始化器**里（不能出现在数组边界等声明符位置）；
- **不能在默认实参里**；
- **不能在静态或线程存储期的块作用域变量的初始化器里**；
- **不能是契约断言谓词中的潜在求值子表达式** {{c++26}}（[[basic.contract]]）。

满足这些条件的位置称为函数的**挂起语境**（[[g:suspension-context]]）。

为什么有这些限制？

- **潜在求值**：`sizeof(co_await x)`、`decltype(co_await x)` 中的表达式不会被求值，而"挂起"是一个运行期动作，放在那里没有意义。
- **不在 `catch` 块里**：在 handler 中，当前异常对象被"正在处理"（[[except.handle]]），其生命周期与异常处理的动态上下文绑定（`std::current_exception`、`throw;` 重新抛出都依赖它）。如果在 handler 中挂起，协程可能在另一个线程上、另一个异常处理上下文中被恢复，这些状态难以定义且实现代价很高（例如 Itanium ABI 的"当前捕获异常栈"是线程局部的）。解决办法是在 `catch` 中记录信息，出了 handler 再 `co_await`。
- **静态局部变量的初始化器**：这种初始化有"仅一次 + 线程安全"的保证（[[stmt.dcl]]），通常由一个锁/守卫变量实现。在持有守卫时挂起，其他线程会一直阻塞，甚至死锁。
- **默认实参**：默认实参在**调用者**中求值，而调用者不一定是协程。
- **契约谓词**：契约断言的求值可能被忽略、观察或重复（[[basic.contract]]），在其中挂起会让协程的控制流取决于契约求值语义。

```cpp title="await-contexts.cpp" error
#include <coroutine>
struct task { struct promise_type {
    task get_return_object() { return {}; }
    std::suspend_never initial_suspend() noexcept { return {}; }
    std::suspend_never final_suspend() noexcept { return {}; }
    void return_void() {}
    void unhandled_exception() {}
}; };

task ok() {
    try { co_await std::suspend_never{}; }               // OK：在 try 块里可以
    catch (...) { }
    int x = (co_await std::suspend_never{}, 1);          // OK：声明的初始化器
    (void)x;
}
task a() { try { } catch (...) { co_await std::suspend_never{}; } }   // error: 在 handler 中
void c(int = (co_await std::suspend_never{}, 1));                     // error: 默认实参
task d() { decltype(co_await std::suspend_never{})* p = nullptr; co_return; }  // error: 未求值语境
task b() { static int s = (co_await std::suspend_never{}, 1); }       // error: 静态局部变量的初始化器
```

!!! warning "编译器现状"
    上例中前三处错误 Clang 23 都能诊断。最后一处（静态局部变量初始化器里的 `co_await`）按 ¶2 非良构，但截至写作时 Clang 23 **接受**了它而没有给出诊断。

标准例 1 里还有两个"挂起语境之外"的典型：命名空间作用域变量的初始化器 `int a[] = { co_await h() };`，以及默认实参。

## 辅助实体：从操作数到 awaiter（¶3）

¶3 定义了求值 *await-expression* 用到的一组辅助类型、表达式和对象。按顺序：

### p 与 P：promise 对象（¶3.1）

*p* 是命名外围协程 promise 对象的左值，`P` 是其类型。

### a：await_transform（¶3.2）

如果这个 *await-expression* 是**用户写的**（不是由 `co_yield`、初始 await、最终 await 隐式产生的），就在 `P` 的作用域中**查找名字 `await_transform`**（[[class.member.lookup]]）。只要找到至少一个声明：

- *a* 是 `p.await_transform(cast-expression)`；

否则 *a* 就是操作数本身。

几个要点：

- 这是**名字查找**而不是"是否可调用"的检查。只要 `P` 声明了任何 `await_transform`，所有用户写的 `co_await e` 都会改写成 `p.await_transform(e)`——如果没有能接受 `e` 的重载，就是**编译错误**，而不是退回到不变换。这让 promise 类型可以**白名单式地控制**协程体内能 `co_await` 什么（例如只允许 `co_await` 某些 Future 类型）。
- 初始/最终 await 与 `co_yield` 不经过 `await_transform`：`initial_suspend()`、`final_suspend()`、`yield_value()` 本来就是 promise 自己的成员，没必要再变换一次。

### o：operator co_await（¶3.3）

对实参 *a* 枚举可用的 `operator co_await` 函数（成员与非成员，按 [[over.match.oper]] 的规则，与其他可重载的一元运算符一样），用重载决议选出最佳：

- 有歧义 → 非良构；
- 没有可行函数 → *o* 就是 *a*；
- 否则 *o* 是对所选函数以 *a* 为实参的调用。

若 *o* 是 prvalue，应用**临时量实质化**——也就是说，awaiter 是一个**真实存在的临时对象**。

### e：awaiter（¶3.4）

*e* 是指代 *o* 求值结果的**左值**。于是之后所有的 `e.await_xxx()` 调用都作用于同一个对象。

!!! note "awaiter 临时量的生命周期"
    *o* 实质化的临时量和其他临时量一样，在包含 `co_await` 的**完整表达式**结束时销毁（[[class.temporary]]）。但这个完整表达式跨越了一次挂起：协程挂起时，临时量仍然"活着"——它和局部变量一样被保存在**协程状态**（coroutine frame）中，而不是栈上。因此 awaiter 可以安全地在 `await_suspend` 中保存 `this`，供恢复者在之后读写（典型做法：恢复者把 I/O 结果写入 awaiter 的成员，`await_resume` 再读出来）。

### h、await-ready、await-suspend、await-resume（¶3.5–¶3.8）

- *h* 是指代外围协程的 `std::coroutine_handle<P>` 对象（¶3.5）；
- *await-ready* 是 `e.await_ready()`，**按语境转换为 `bool`**（¶3.6）；
- *await-suspend* 是 `e.await_suspend(h)`，它必须是 `void`、`bool` 或某个 `std::coroutine_handle<Z>` 类型的 **prvalue**（¶3.7）；
- *await-resume* 是 `e.await_resume()`（¶3.8）。

注意三个函数都是**成员函数调用**的写法，标准没有为它们提供非成员版本或 ADL。`await_suspend` 的形参通常写成 `std::coroutine_handle<>`（类型擦除的版本），由 `coroutine_handle<P>` 隐式转换而来；也可以写成 `coroutine_handle<P>` 以访问 promise。

完整的"展开"流程可以总结为下图（伪代码，标准没有这样一段代码，但语义等价）：

```text
a = has_member_await_transform<P> ? p.await_transform(expr) : expr;      // ¶3.2
o = 有可用的 operator co_await ? operator co_await(a) : a;                // ¶3.3
auto&& e = o;                                                             // ¶3.4（prvalue 时实质化）
if (!e.await_ready()) {                                                   // ¶5
    <协程被视为已挂起>
    根据 e.await_suspend(h) 的类型：
      void              → 调用之；返回调用者/恢复者           [挂起点]
      bool              → 调用之；若为 false 立即恢复，否则返回 [挂起点]
      coroutine_handle  → 调用之，并 .resume() 其结果（对称转移）
    <恢复点>
}
result = e.await_resume();                                                 // ¶5.2
```

## 类型与值类别（¶4）

¶4 *await-expression* 的类型和值类别与 *await-resume* 表达式**相同**。`await_resume()` 返回 `int` 则 `co_await x` 是 `int` prvalue；返回 `T&` 则是左值；返回 `void` 则 `co_await x` 是 `void` 表达式。

## 求值（¶5）

¶5 先求值（可能经过转换的）*o*，再求值 *await-ready*。之后分两种情况。

### await_ready 为 false：挂起（¶5.1）

此时协程**被视为已挂起**（注意：在调用 `await_suspend` **之前**就算挂起了）。这一点很关键——它意味着在 `await_suspend` 内部，其他线程就可以通过 `h` 恢复这个协程（`h.resume()`），而不会违反 [[dcl.fct.def.coroutine#8]]"恢复未挂起的协程是 UB"的规则。

然后根据 *await-suspend* 的类型分三种：

**¶5.1.1 返回 `std::coroutine_handle<Z>`：对称转移。** 求值 *await-suspend*，然后对其结果调用 `.resume()`。注 1：这会恢复返回的那个协程；如此可以连续恢复任意多个协程，最终控制流回到当前协程的调用者或恢复者。

**¶5.1.2 返回 `bool`：** 求值 *await-suspend*；若结果为 `false`，**当前协程立即恢复**（就像没挂起过一样，接着执行 `await_resume`）。返回 `true` 则保持挂起，控制返回调用者。用途：`await_suspend` 里尝试注册回调，若发现操作已经完成（来不及注册），就返回 `false` 避免一次无意义的挂起/恢复。

**¶5.1.3 返回 `void`：** 求值 *await-suspend*，然后控制流返回当前协程的调用者或恢复者，**不退出任何作用域**（[[stmt.jump]]）——局部变量不会被析构，它们留在协程状态里。控制返回之前的那一点称为协程的**挂起点**（[[g:suspend-point]]）。

**异常**：如果 *await-suspend* 的求值**以异常退出**，异常被捕获、**协程被恢复**、然后异常**立即重新抛出**。效果是：异常就像是从 `co_await` 表达式本身抛出的一样，可以被协程体里包住 `co_await` 的 `try` 捕获。按字面，这句话只写在 ¶5.1.3（`void` 情形）之下；对于返回 `bool` 或 `coroutine_handle` 的 `await_suspend` 抛异常，本地验证 Clang 23 的行为与之相同（异常在协程体内的 `co_await` 处被捕获）。

### 恢复后：await_resume（¶5.2）

¶5.2 当 *await-ready* 为 `true`，或协程被恢复（不是因为 `await_suspend` 抛异常而恢复）时，求值 *await-resume*，其结果就是整个 *await-expression* 的结果。

注 2：就**顺序**而言，*await-expression* 是**不可分割的**（indivisible，[[intro.execution]]）——外面的表达式不能"插入"到 `co_await` 的中间步骤里。例如 `f(co_await a, g())` 中，`g()` 要么在整个 `co_await a`（含挂起和恢复）之前，要么之后求值，而不会在挂起期间求值。

## 例子

### 不挂起：await_ready 返回 true；bool 版 await_suspend

```cpp title="await-basic.cpp" run ok
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

struct ready_awaiter {
    int v;
    bool await_ready() const noexcept { return true; }       // 不挂起
    void await_suspend(std::coroutine_handle<>) noexcept {}  // 不会被调用
    int await_resume() const noexcept { return v; }          // co_await 的结果：int prvalue
};

struct maybe {
    bool await_ready() const noexcept { return false; }      // 先算"挂起"
    bool await_suspend(std::coroutine_handle<>) noexcept {
        return false;                                         // ¶5.1.2：立即恢复
    }
    const char* await_resume() const noexcept { return "resumed immediately"; }
};

int main() {
    auto co = []() -> task {
        int x = co_await ready_awaiter{42};
        std::printf("%d\n", x);
        std::printf("%s\n", co_await maybe{});
    };
    co();
}
```

输出 `42` 和 `resumed immediately`。标准库的 `std::suspend_always` / `std::suspend_never` 就是 `await_ready` 分别返回 `false` / `true`、`await_suspend` 与 `await_resume` 为空的两个平凡 awaiter。

### await_transform 与 operator co_await 的叠加

```cpp title="await-transform.cpp" run ok
#include <coroutine>
#include <cstdio>

struct awaiter_int {
    int v;
    bool await_ready() const noexcept { return true; }
    void await_suspend(std::coroutine_handle<>) noexcept {}
    int await_resume() const noexcept { return v; }
};

struct Seconds { int n; };
awaiter_int operator co_await(Seconds s) { return {s.n * 1000}; }   // ¶3.3

struct task {
    struct promise_type {
        task get_return_object() { return {}; }
        std::suspend_never initial_suspend() noexcept { return {}; }
        std::suspend_never final_suspend() noexcept { return {}; }
        void return_void() {}
        void unhandled_exception() {}
        Seconds await_transform(int n) { return {n}; }              // ¶3.2
    };
};

task co() {
    int ms = co_await 3;   // a = p.await_transform(3) → Seconds{3}
                           // o = operator co_await(a) → awaiter_int{3000}
    std::printf("%d\n", ms);
}

int main() { co(); }
```

这里如果写 `co_await Seconds{1}`，即使 `Seconds` 有 `operator co_await`，也会**编译失败**：promise 声明了 `await_transform`，于是先要调用 `p.await_transform(Seconds{1})`，而唯一的重载只接受 `int`。

### 对称转移（symmetric transfer）

```cpp title="symmetric-transfer.cpp" run ok
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
                return h.promise().cont;     // 结束时"跳"回等待者
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
        return h;                            // ¶5.1.1：直接恢复子协程
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

**为什么需要对称转移？** 若 `await_suspend` 返回 `void` 并在内部调用 `h.resume()`，那么"父协程恢复子协程，子协程结束时再恢复父协程"会形成**嵌套的函数调用**：每一轮循环都在栈上多压几帧，循环一百万次就可能栈溢出。返回 `coroutine_handle` 时，标准只说"求值 `await_suspend`，然后对结果 `.resume()`"，实现可以（而且主流实现确实）把这个 `.resume()` 编译成**尾调用**：当前协程的 resume 函数先返回，再跳转到目标协程，栈深度保持不变。`std::noop_coroutine()` 则是"没有可以转移的对象"时的占位：恢复它什么也不做，直接返回调用者。

标准本身没有要求尾调用（这属于实现质量），但对称转移的设计目的就是使之成为可能（[[P0913R1]]）。

### await_suspend 抛出异常

```cpp title="await-suspend-throws.cpp" run ok
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
    try { co_await throwing{}; }       // 异常像是从 co_await 本身抛出
    catch (const std::exception& e) { std::printf("caught in coroutine: %s\n", e.what()); }
}

int main() { t(); }
```

输出 `caught in coroutine: boom`：协程先被恢复，异常再在 `co_await` 处重新抛出，`await_resume` 不会被调用。

## 实现视角

!!! impl "协程帧与 co_await 的编译"
    - **协程帧**：Clang（LLVM 的 coroutine passes）、GCC、MSVC 都把协程拆成 ramp 函数（首次调用）、resume 函数和 destroy 函数。跨越挂起点存活的局部变量和 awaiter 临时量都放在堆上的协程帧里；帧中还保存一个"当前挂起点编号"，resume 函数据此 `switch` 跳转。`std::coroutine_handle` 本质上就是指向协程帧的指针，帧开头是 resume/destroy 两个函数指针，`h.resume()` 就是一次间接调用。
    - **await_ready 的价值**：`await_ready()` 返回 `true` 时完全不需要保存状态；内联后，`co_await` 一个已就绪的 awaiter 可以和普通函数调用一样便宜。
    - **对称转移与尾调用**：LLVM 的协程拆分在 `await_suspend` 返回句柄时把对目标协程的恢复生成为保证的尾调用（在支持的目标上），因此上面的例子在本地 `-O0 -fsanitize=address` 下也能跑完一百万次而不栈溢出。在不支持保证尾调用的目标上，这一性质可能无法保证。
    - **HALO**：若协程帧的生命周期严格嵌套在调用者之内，LLVM 可以把帧的堆分配省略、改为放在调用者的栈帧中（heap allocation elision optimization）。这与 [[expr.new]] 的分配省略是不同的机制，依据是 [[dcl.fct.def.coroutine]] 允许省略协程状态的分配。

## 历史与演进

!!! history "从 TS 到 C++20 及之后"
    - 协程最初以 Coroutines TS 的形式发布，C++20 通过 [[P0912R5]] 将其合并进标准。
    - 对称转移（`await_suspend` 返回 `coroutine_handle`）由 [[P0913R1]] 在合并之前加入；`std::noop_coroutine` 也来自这一提案。
    - C++20 的 `co_await` 规则基本沿用至今。C++26 引入契约后，¶2 增加了"不能出现在契约断言谓词中"的限制 {{c++26}}。
    - C++23 的 `std::generator`（[[coro.generator]]）是第一个标准库提供的协程返回类型；它通过 `await_transform` 被声明为 deleted 的方式**禁止**在生成器中使用 `co_await`——这正是 ¶3.2"只要找到声明就改写"的典型应用。

## 陷阱

!!! pitfall "在 await_suspend 里交出句柄后再访问 awaiter"
    协程在调用 `await_suspend` 之前就已被视为挂起。若 `await_suspend` 把 `h` 交给另一个线程，那个线程可能**立刻** `h.resume()`，协程可能一路运行到结束并销毁协程帧——包括 awaiter 临时量本身。此后 `await_suspend` 中再访问 `this` 的任何成员就是访问已销毁的对象（UB）。安全的写法是：交出句柄应当是 `await_suspend` 中**最后一个**触碰 awaiter 或协程帧的动作。

!!! pitfall "以为写了 operator co_await 就一定会被用"
    只要 promise 类型声明了任何 `await_transform`，用户写的每个 `co_await e` 都先变成 `p.await_transform(e)`。`operator co_await` 作用在 `await_transform` 的**结果**上，而不是 `e` 上。

!!! pitfall "await_ready 的返回值方向"
    `await_ready()` 返回 `true` 表示"已经就绪，**不要**挂起"；`await_suspend` 返回 `true` 表示"**保持**挂起"。两个 `bool` 的含义方向正好相反，很容易写反。

!!! pitfall "await_suspend 返回 bool 时的 false"
    返回 `false` 会立即恢复当前协程。如果此前已经把 `h` 交给了别的线程，那个线程也可能同时恢复它——两次恢复同一协程，后一次面对的是未挂起的协程，UB（[[dcl.fct.def.coroutine#8]]）。

## 思考题

!!! question "思考题 1"
    设 promise 类型没有 `await_transform`，`struct X { std::suspend_never operator co_await(); };`，另有非成员 `std::suspend_never operator co_await(X);`。`co_await X{}` 会怎样？

<details markdown="1">
<summary>答案</summary>

非良构：重载决议有歧义。¶3.3 按 [[over.match.oper]] 同时收集成员候选与非成员候选。实参是 `X` 类型的 prvalue：对成员候选，隐式对象形参是 `X&`，但无引用限定符的成员函数允许绑定右值（[[over.match.funcs]]），是恒等转换；对非成员候选，按值传递也是恒等转换。两者不分优劣，按 ¶3.3"If overload resolution is ambiguous, the program is ill-formed"。Clang 23 报告 "use of overloaded operator 'co_await' is ambiguous"。这与其他可重载一元运算符（如 `operator-`）的规则完全一致。
</details>

!!! question "思考题 2"
    `co_await` 一个 `await_ready()` 返回 `true` 的 awaiter，协程**是否经过挂起点**？`await_suspend` 是否需要能通过编译？

<details markdown="1">
<summary>答案</summary>

不经过挂起点：¶5.2 直接求值 *await-resume*。但 `await_suspend` 仍然必须**良构**：¶3.7 把 *await-suspend* 定义为 `e.await_suspend(h)`，并要求它是 `void`/`bool`/`coroutine_handle<Z>` 类型的 prvalue——这是编译期检查，与运行期是否走到这一分支无关。所以即便 `await_ready` 是 `constexpr` 地返回 `true`，也必须提供合法的 `await_suspend`。
</details>

!!! question "思考题 3"
    为什么 `co_yield` 和 `initial_suspend`/`final_suspend` 产生的 await 不经过 `await_transform`？如果经过会出什么问题？

<details markdown="1">
<summary>答案</summary>

这些 await 的操作数本身就是 promise 自己的成员调用（`p.yield_value(e)`、`p.initial_suspend()`、`p.final_suspend()`），promise 已经完全掌控它们返回什么，再经过一次 `await_transform` 是多余的。而且如果经过，像 `std::generator` 这种"用 deleted `await_transform` 禁止用户 `co_await`"的设计就会连自己的 `co_yield` 和初始/最终挂起也一起禁止掉，promise 将不得不为自己的 awaiter 类型再开白名单。
</details>

## 小结

| 步骤 | 条款 | 内容 |
|---|---|---|
| 位置限制 | ¶2 | 潜在求值；函数体内；不在 handler、默认实参、静态局部初始化器、契约谓词中 |
| 变换 1 | ¶3.2 | promise 有名为 `await_transform` 的成员 → `p.await_transform(e)`（不含 `co_yield`/初始/最终 await） |
| 变换 2 | ¶3.3 | 重载决议 `operator co_await`；无可行函数则不变换；歧义非良构 |
| awaiter | ¶3.4 | prvalue 实质化为临时量，生命周期跨越挂起，保存在协程帧 |
| 类型 | ¶4 | 与 `await_resume()` 相同的类型与值类别 |
| `await_ready()` 为 true | ¶5.2 | 不挂起，直接 `await_resume()` |
| `await_suspend` → `void` | ¶5.1.3 | 挂起，返回调用者/恢复者 |
| `await_suspend` → `bool` | ¶5.1.2 | `false` 立即恢复，`true` 保持挂起 |
| `await_suspend` → `coroutine_handle` | ¶5.1.1 | 对称转移：恢复返回的协程（实现通常为尾调用） |
| `await_suspend` 抛异常 | ¶5.1.3 | 恢复协程并在 `co_await` 处重新抛出 |
| 顺序 | ¶5 注 2 | `co_await` 相对于外部求值不可分割 |
