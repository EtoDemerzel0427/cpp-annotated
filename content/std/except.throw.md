---
title: 抛出异常
summary: 抛出异常就是初始化一个异常对象：它的类型怎么定、哪些类型不能抛、存在哪里、什么时候销毁、为什么必须可拷贝；异常何时算未捕获；处理异常途中再抛出为什么会终止程序；C++26 起常量求值里也能抛出和捕获异常。
status: done
papers: P3068R6
related: expr.throw, except.handle, except.ctor, except.terminate, propagation, uncaught.exceptions, basic.stc.dynamic.allocation, class.copy.elision, expr.const.core
tags: 异常, 异常对象, exception_ptr, uncaught_exceptions
updated: 2026-10-19
---

!!! tldr
    - `throw e;` 按 `e` 的静态类型拷贝初始化一个新的**异常对象**；`throw;` 不创建新对象，重抛当前处理的那个。
    - 异常对象的存储方式未指定，不经过全局 `operator new`。它在最后一个活动 handler 非重抛退出、并且最后一个引用它的 `std::exception_ptr` 销毁后才销毁。
    - 异常对象的类型必须能从 `const T` 左值拷贝构造，只能移动的类型按标准不能抛出（Clang 目前不检查）。
    - 从异常对象初始化完成到 handler 参数初始化完成，异常处于未捕获状态。这期间异常处理机制调用的函数（回溯中的析构函数、handler 参数的拷贝构造函数）再抛出，程序调用 `std::terminate`。
    - C++26 允许在常量求值中抛出异常，前提是它在同一次求值里被捕获并销毁。

## 抛出的是一个对象（¶1–¶2）

```cpp run title="throw-types.cpp" ok
#include <cstdio>

struct Overflow { char op; double a, b; };

void f(double x) { throw Overflow{'+', x, 3.45e107}; }

int main() {
    try { throw "Help!"; }                  // 异常对象的类型是 const char*
    catch (const char* p) { std::puts(p); }

    try { f(1.2); }
    catch (Overflow& o) { std::printf("%c %g\n", o.op, o.a); }
}
```

¶1 抛出异常会把控制转移给一个 handler，同时传过去一个对象，由这个对象的类型决定哪些 handler 能捕获它。除了 `throw` 表达式，还有几处会抛出异常：

| 来源 | 例子 | 抛出的类型 |
|---|---|---|
| 分配函数（[[basic.stc.dynamic.allocation]]） | `operator new` 失败 | 能被 `std::bad_alloc` handler 捕获的类型 |
| `dynamic_cast`（[[expr.dynamic.cast]]） | 转换到引用失败 | `std::bad_cast` |
| `typeid`（[[expr.typeid]]） | `typeid(*p)`，`p` 是指向多态类型的空指针 | `std::bad_typeid` |
| *new-expression*（[[expr.new]]） | 数组长度非法 | `std::bad_array_new_length` |
| 标准库函数 | `std::vector::at` 越界 | 见各函数的 *Throws:* |

¶2 控制转到**最近的**、类型匹配的 handler。最近是按执行历史算的：在所有已进入、尚未退出的 try 块中，最后进入的那个。同一个 `throw` 在不同的调用路径上可能落到不同的 handler：

```cpp run title="nearest.cpp" ok
#include <cstdio>

void thrower() { throw 1; }

void middle() {
    try {
        thrower();                    // 最近进入的 try 块
    } catch (const char*) {           // 类型不匹配，继续向外找
        std::puts("middle");
    }
}

int main() {
    try {
        middle();
    } catch (int) {                   // 匹配
        std::puts("main");
    }
}
```

所有已进入的 try 块都没有匹配的 handler 时，调用 `std::terminate`（[[except.handle#8]]）。

## 异常对象的类型（¶3）

¶3 抛出异常会初始化一个具有动态存储期的对象，称为**异常对象**（[[g:exception-object]]）。它的类型由 [[expr.throw#2]] 规定：对操作数做数组到指针、函数到指针转换，再去掉顶层 cv 限定，然后用操作数拷贝初始化它。所以 `const int x = 1; throw x;` 抛出 `int`，`throw "abc";` 抛出 `const char*`。

异常对象的类型取自操作数的静态类型，`throw` 并不知道一个引用实际绑定的是哪个派生类对象：

```cpp run title="rethrow-vs-throw-e.cpp" ok
#include <cstdio>

struct B { virtual const char* who() const { return "B"; } };
struct D : B { const char* who() const override { return "D"; } };

int main() {
    try {
        try { throw D{}; }
        catch (B& b) { throw b; }      // 新的异常对象，类型是 B：切片
    } catch (B& b) { std::printf("throw b; -> %s\n", b.who()); }

    try {
        try { throw D{}; }
        catch (B&) { throw; }          // 重抛原来的 D 对象
    } catch (B& b) { std::printf("throw;   -> %s\n", b.who()); }
}
```

输出 `throw b; -> B` 和 `throw;   -> D`。不带操作数的 `throw;` 重抛**当前处理的异常**，也就是最近激活、仍然活动的 handler 所处理的那个异常（[[except.handle#10]]）。它不创建新对象。没有正在处理的异常时执行 `throw;`，调用 `std::terminate`。

`throw;` 不必写在 handler 的花括号里，从 handler 中调用的函数也可以用它。这让一个函数集中处理异常分类：

```cpp run title="dispatcher.cpp" ok
#include <cstdio>
#include <stdexcept>

int to_error_code() {          // 只能在 handler 里（直接或间接）调用
    try { throw; }
    catch (const std::invalid_argument&) { return 1; }
    catch (const std::exception&)        { return 2; }
    catch (...)                          { return 3; }
}

int main() {
    try { throw std::invalid_argument("x"); }
    catch (...) { std::printf("%d\n", to_error_code()); }
}
```

¶3 还规定，异常对象的类型如果是不完整类型、抽象类，或者指向不完整类型（cv `void` 除外）的指针，程序非良构：

```cpp title="bad-exception-types.cpp" error
struct Abs { virtual void f() = 0; };
struct Inc;

void a(Abs& r) { throw r; }     // error: 异常对象类型是 Abs，抽象类
void b(Inc* p) { throw p; }     // error: 指向不完整类型的指针
void c(void* p) { throw p; }    // OK: void* 例外
```

指向不完整类型的指针也不行，是因为 handler 可以通过派生类到基类的指针转换匹配（[[except.handle#3]]），实现必须在抛出点把类层次信息记录到运行时类型信息里，类型不完整时这些信息还不存在。`void*` 不参与这种转换。

## 存在哪里、何时销毁（¶4）

¶4 异常对象的内存以未指定的方式分配。[[basic.stc.dynamic.allocation]] 补充了一点：不会为它调用全局分配函数 `operator new`。替换全局 `operator new` 来统计内存时，异常对象不会被计入。Itanium C++ ABI 用 `__cxa_allocate_exception` 分配，通常走 `malloc`，失败时退回到一块预留的紧急缓冲区，保证内存耗尽时还能抛出 `std::bad_alloc`（[[toolchain/exception-implementation]]）。

handler 以重抛方式退出时，控制传给同一个异常对象的下一个 handler。异常对象什么时候销毁，由两种**潜在销毁点**决定：

- ¶4.1 一个活动 handler 以重抛以外的方式退出，紧接在 handler 形参销毁之后；
- ¶4.2 一个引用该异常对象的 `std::exception_ptr` 被销毁，在它的析构函数返回之前。

所有潜在销毁点里有一个未指定的最后一个，异常对象在那里销毁，其余的都 happens before 它。之所以这么规定，是因为 `std::exception_ptr` 能让异常对象比 handler 活得更久，甚至交给另一个线程：

```cpp run title="exception-ptr-lifetime.cpp" ok
#include <cstdio>
#include <exception>
#include <stdexcept>
#include <thread>

int main() {
    std::exception_ptr p;
    try {
        throw std::runtime_error("from main thread");
    } catch (...) {
        p = std::current_exception();   // 现在有两个潜在销毁点
    }                                   // handler 退出：不是最后一个，对象还在

    std::thread t([p] {                 // 另一个线程再持有一份
        try { std::rethrow_exception(p); }
        catch (const std::exception& e) { std::printf("thread: %s\n", e.what()); }
    });
    t.join();
}                                       // 最后一个 exception_ptr 销毁，异常对象随之销毁
```

实现通常用原子引用计数，计数归零的那一刻就是最后一个销毁点。注 2 说明，除此之外异常处理不隐含任何线程同步。注 3 说明，异常不会自己传播到别的线程，必须先捕获、保存，再用库函数重抛（[[propagation]]、[[futures]]）。

`std::current_exception()` 返回的 `exception_ptr` 可能引用当前异常本身，也可能引用它的一个副本，两次调用是否得到同一个对象是未指定的（[[propagation#9]]）。这是为把异常对象放在栈上的实现留的余地。libc++abi 把它放在堆上，从不复制：

```cpp run title="current-exception-same.cpp" unspecified
#include <cstdio>
#include <exception>

int main() {
    std::exception_ptr p1, p2;
    try { throw 42; }
    catch (int& r) {
        p1 = std::current_exception();
        p2 = std::current_exception();
        r = 7;                                  // 修改异常对象本身
    }
    std::printf("p1 == p2: %d\n", p1 == p2);    // 未指定；libc++abi 上为 1
    try { std::rethrow_exception(p1); }
    catch (int v) { std::printf("%d\n", v); }   // 未指定是否为 7；libc++abi 上为 7
}
```

## 异常类型必须可拷贝（¶5）

¶5 设 `T` 是异常对象的类型。在与 `T` 无关的上下文中，从 `const T` 左值拷贝初始化一个 `T` 必须是良构的；如果 `T` 是类类型，选中的构造函数被 odr-use，析构函数是潜在调用的（[[class.dtor]]）。

这条要求来自上一节的复制自由：`std::current_exception` 和 `std::rethrow_exception` 可能在运行时、在与抛出点无关的库代码里复制异常对象，所以抛出点就必须确保拷贝构造函数存在并且可用。与 `T` 无关的上下文这个限定，意思是访问检查不借用抛出点的权限：在 `T` 的成员函数里 `throw *this;`，私有的拷贝构造函数也不算可用。

```cpp title="move-only-throw.cpp" error
#include <memory>

struct MoveOnly {
    MoveOnly() = default;
    MoveOnly(MoveOnly&&) = default;      // 拷贝构造函数被隐式删除
};

void f() { throw MoveOnly{}; }           // 按 ¶5 非良构
void g() { throw std::make_unique<int>(1); }   // 同理
```

!!! impl "编译器现状"
    本机 Clang 23 接受上面的代码，不给诊断，这与标准不符。抛出只能移动的类型在 libc++abi 上能正常运行，因为它的 `current_exception` 从不复制。可移植的代码不应依赖这一点。

## 未捕获与已捕获（¶6–¶8）

¶6 从异常对象初始化完成，到某个 handler 激活完成（handler 的形参初始化完毕，[[except.handle#9]]）为止，异常处于**未捕获**（uncaught）状态。注 4 指出，由它引起的整个栈回溯期间，它都是未捕获的。

¶7 重抛的异常从重抛那一刻起到再次被捕获为止，又是未捕获的。¶8 handler 变为活动时，异常被视为已捕获。重抛之后，原来的 handler 还没退出、仍然活动，但异常又在寻找新的 handler，所以一个异常可以同时有活动的 handler 而又处于未捕获状态（注 6）。

`std::uncaught_exceptions()` 返回当前线程里未捕获异常的个数：

```cpp run title="uncaught-window.cpp" ok
#include <cstdio>
#include <exception>

struct Probe {
    const char* where;
    ~Probe() { std::printf("%-8s uncaught=%d\n", where, std::uncaught_exceptions()); }
};

struct E {
    E() = default;
    E(const E&) { std::printf("copy     uncaught=%d\n", std::uncaught_exceptions()); }
};

int main() {
    try {
        Probe p{"unwind"};        // 回溯期间：1
        throw E{};                // E{} 直接初始化异常对象，不调用拷贝构造
    } catch (E e) {               // 拷贝初始化 handler 形参：激活尚未完成，仍为 1
        Probe p{"handler"};       // handler 已激活：0
    }
}
```

输出：

```text
unwind   uncaught=1
copy     uncaught=1
handler  uncaught=0
```

未捕获区间从异常对象初始化完成开始。构造异常对象时抛出的异常（例如 `throw std::string(...)` 里分配失败）只是一次普通的抛出，原来那个 `throw` 根本没有发生。

计数的典型用途是 scope guard：析构函数比较构造时和析构时的计数，判断自己是不是因为栈回溯而析构，从而决定提交还是回滚。

```cpp run title="scope-guard.cpp" ok
#include <cstdio>
#include <exception>

struct Transaction {
    int on_entry = std::uncaught_exceptions();
    ~Transaction() {
        std::puts(std::uncaught_exceptions() > on_entry ? "rollback" : "commit");
    }
};

struct Inner {
    ~Inner() {
        try { Transaction t; } catch (...) {}   // 回溯途中新开的事务：commit
    }
};

int main() {
    { Transaction t; }                               // commit
    try { Transaction t; throw 1; } catch (int) {}   // rollback
    try { Inner i; throw 2; } catch (int) {}         // commit
}
```

C++17 之前只有返回 `bool` 的 `std::uncaught_exception()`，它在第三种情况下返回 `true`，回溯途中新开的事务会被误回滚。所以 C++17 加入了计数版本，C++20 删除了旧函数（[[uncaught.exceptions]]）。

## 处理途中再抛出：terminate（¶9）

```cpp run title="throw-during-unwind.cpp" ok
#include <cstdio>
#include <cstdlib>
#include <exception>

struct Bomb { ~Bomb() noexcept(false) { throw 2; } };

int main() {
    std::set_terminate([] { std::fputs("terminate\n", stderr); std::abort(); });
    try {
        Bomb b;
        throw 1;          // 回溯时 ~Bomb 抛出 2：调用 std::terminate
    } catch (...) {
        std::puts("never reached");
    }
}
```

程序本身良构，运行时一定以 `std::terminate` 结束。

¶9 处理一个未捕获的异常时，如果异常处理机制直接调用的某个函数以异常退出，就调用 `std::terminate`。这样的函数有两类：栈回溯中的析构函数（注 7），以及初始化 handler 形参时的拷贝构造函数。语言没有办法让两个异常同时传播，handler 只能接一个对象，回溯也只能朝一个方向走，所以选择直接终止。

第二类更隐蔽。handler 按值捕获时，机制要调用拷贝构造函数初始化形参，这时异常仍是未捕获的：

```cpp run title="copy-into-handler.cpp" ok
#include <cstdio>
#include <cstdlib>
#include <exception>

struct C {
    C() { }
    C(const C&) {
        if (std::uncaught_exceptions())
            throw 0;      // 拷贝到 handler 形参时抛出
    }
};

int main() {
    std::set_terminate([] { std::fputs("terminate\n", stderr); std::abort(); });
    try {
        throw C();        // 如果这次拷贝没有被消除，调用 std::terminate
    } catch (C) { std::puts("caught"); }
}
```

[[class.copy.elision#1]] 允许把 handler 形参当作异常对象的别名、省掉这次拷贝。Clang 23 没有省略，程序调用了 `std::terminate`。

关键词是直接。析构函数内部自己 `try { throw ...; } catch (...) {}`，异常在析构函数里处理完了，析构函数没有以异常退出，就没有问题，上面 `Inner` 的例子就是这样。初始化异常对象本身时调用的构造函数也不在此列，那时异常还没有进入未捕获状态。

## 常量求值中的异常 {{c++26}}

C++26 之前，常量求值中只要求值了 `throw` 表达式，整个表达式就不是常量表达式。C++26（[[P3068R6]]）放宽了这一点，[[expr.const.core#2]] 只要求：

- 异常对象，以及 `std::current_exception`、`std::rethrow_exception` 造出的副本，都在本次求值内部销毁，也就是说异常必须在编译期就被捕获处理完，不能漏到运行时；
- 不带操作数的 `throw;` 只能重抛本次求值中构造的异常。

`std::exception_ptr`、`std::make_exception_ptr`、`std::rethrow_exception` 等也随之成为 `constexpr`（[[propagation]]）。

```cpp title="constexpr-exceptions.cpp"
struct ParseError { int pos; };

constexpr int parse_digit(char c) {
    if (c < '0' || c > '9') throw ParseError{0};
    return c - '0';
}

constexpr int safe_parse(char c) {
    try { return parse_digit(c); }
    catch (ParseError) { return -1; }   // 在常量求值内部捕获、销毁
}

static_assert(safe_parse('7') == 7);
static_assert(safe_parse('x') == -1);   // C++26: OK；C++23: 不是常量表达式

constexpr int bad = parse_digit('x');   // error: 异常逃出了常量求值
```

本机 Clang 23 尚未实现这一特性，第二个 `static_assert` 被拒绝，所以这段代码不标判定。按标准只有最后一行是错误。

## 常见误解

!!! pitfall "以为 `throw e;` 保留了动态类型"
    `void report(const std::exception& e) { throw e; }` 抛出的是 `std::exception`，不是调用者传进来的 `std::runtime_error`。要保留动态类型，在 handler 里用 `throw;`，或者用 `std::rethrow_exception(std::current_exception())`。

!!! pitfall "抛出指向局部对象的指针"
    `throw &local;` 合法，但异常对象只是一个指针。回溯之后它指向的局部对象已经销毁，异常对象的生存期不覆盖它指向的东西。

## 思考题

!!! question "思考题 1"
    以下程序会调用 `std::terminate` 吗？

    ```cpp
    struct S {
        ~S() noexcept(false) {
            if (std::uncaught_exceptions() == 0) throw 1;
        }
    };
    int main() {
        try { S s; } catch (int) {}
    }
    ```

<details markdown="1">
<summary>答案</summary>

不会。`s` 是因为离开 try 块的作用域而正常析构的，没有未捕获的异常，析构函数抛出的 `1` 是一次普通的抛出，被 `catch (int)` 捕获。¶9 只管异常处理机制在处理未捕获异常时直接调用的函数。

析构函数必须写 `noexcept(false)`。否则它隐式是 `noexcept` 的（[[except.spec#8]]），查找 handler 时穿出这个函数，会按 [[except.handle#7]] 调用 `std::terminate`。
</details>

!!! question "思考题 2"
    下面的 `throw;` 重抛的是 `1` 还是 `2.0`？

    ```cpp
    try { throw 1; }
    catch (int) {
        try { throw 2.0; }
        catch (double) { }
        throw;
    }
    ```

<details markdown="1">
<summary>答案</summary>

重抛 `1`。`throw;` 重抛最近激活、仍然活动的 handler 所处理的异常（[[except.handle#10]]）。`catch (double)` 已经退出，仍然活动的是 `catch (int)`。把 `throw;` 移进 `catch (double)` 里，重抛的才是 `2.0`。
</details>

<details class="fine" markdown="1"><summary>其余条文</summary>

¶5 的拷贝要求经过几次修改。C++11 之前只要求拷贝构造函数即使被消除也必须可访问；后来为支持 `current_exception` 的复制，改为要求把操作数视为左值时选中的构造函数可用（CWG1863）；当前草案改写为从 `const T` 左值、在无关上下文中拷贝初始化。

</details>
