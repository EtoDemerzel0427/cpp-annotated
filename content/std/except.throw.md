---
title: 抛出异常
summary: 抛出异常即初始化一个动态存储期的"异常对象"；它的类型限制、存储方式（未指定）、销毁时机（最后一个"潜在销毁点"）、必须可拷贝的要求；"未捕获"与"已捕获"的精确定义；异常处理机制直接调用的函数再抛异常 ⇒ std::terminate；常量求值中的异常
status: done
papers: P3068R6
related: expr.throw, except.handle, except.ctor, except.terminate, propagation, uncaught.exceptions, basic.stc.dynamic.allocation, class.copy.elision, expr.const.core
tags: 异常, 异常对象, exception_ptr, uncaught_exceptions
updated: 2026-10-17
---

[[expr.throw]] 规定 `throw` **表达式**的语法和类型（`void`），本节规定"抛出异常"这个**动作**的语义：控制转向哪个 handler，被"抛出"的那个东西——**异常对象**（exception object）——是什么、存在哪、活多久，以及在什么时间窗口内异常算作"未捕获"。

读本节前最好先了解：[[basic.stc]]（存储期）、[[dcl.init]]（拷贝初始化）、[[class.copy.elision]]（复制消除）。

## 抛出的来源与"按类型匹配"（¶1）

¶1 抛出异常把控制转移给一个 handler。注 1 列出了标准中**会抛出异常的上下文**：

| 来源 | 例子 | 抛出的类型 |
|---|---|---|
| *throw-expression*（[[expr.throw]]） | `throw E{};` | 操作数决定 |
| 分配函数（[[basic.stc.dynamic.allocation]]） | `operator new` 失败 | 匹配 `std::bad_alloc` 的类型 |
| `dynamic_cast`（[[expr.dynamic.cast]]） | 转换到引用失败 | `std::bad_cast` |
| `typeid`（[[expr.typeid]]） | `typeid(*p)`，`p` 是指向多态类型的空指针 | `std::bad_typeid` |
| *new-expression*（[[expr.new]]） | 数组长度非法 | `std::bad_array_new_length` |
| 标准库函数 | `std::vector::at` 越界 | 见各函数的 *Throws:* |

随后是本章的核心约定：**传递的是一个对象，而对象的类型决定了哪些 handler 能捕获它**。注意这里说的是对象的类型，而不是"抛出表达式的静态类型的某种转换"——handler 匹配在运行时只能看到异常对象本身的类型（[[except.handle#3]]）。

```cpp run title="throw-types.cpp" ok
#include <cstdio>

struct Overflow { char op; double a, b; };

void f(double x) { throw Overflow{'+', x, 3.45e107}; }

int main() {
    try { throw "Help!"; }                  // 异常对象类型是 const char*（数组到指针转换）
    catch (const char* p) { std::puts(p); }

    try { f(1.2); }
    catch (Overflow& o) { std::printf("%c %g\n", o.op, o.a); }
}
```

## "最近的"handler（¶2）

¶2 控制转移到**最近的**、类型**匹配**的 handler。"最近"的定义是动态的：其 `try` 关键字后的复合语句（或 *ctor-initializer*）**最近被进入且尚未退出**的那个。

这是一个关于**执行历史**的定义，而不是词法嵌套：

```cpp run title="nearest.cpp" ok
#include <cstdio>

void thrower() { throw 1; }

void middle() {
    try {
        thrower();                    // 最近进入的 try 块在这里
    } catch (const char*) {           // 但类型不匹配，继续向外找
        std::puts("middle");
    }
}

int main() {
    try {
        middle();
    } catch (int) {                   // 第二近的 try 块，匹配
        std::puts("main");
    }
}
```

因为"进入且尚未退出"是运行时状态，同一个 `throw` 在不同调用路径上会落到不同的 handler。若所有已进入的 try 块都没有匹配的 handler，见 [[except.handle#8]]。

## 异常对象（¶3）

¶3 抛出异常会**初始化一个具有动态存储期的对象**，称为**异常对象**（[[g:exception-object]]）。

!!! std
    Throwing an exception initializes an object with dynamic storage duration, called the *exception object*.

    抛出异常即初始化一个动态存储期的对象，称为异常对象。

它的类型和初始化方式由 [[expr.throw#2]] 规定：

1. 对操作数做数组到指针、函数到指针转换；
2. 去掉**顶层** cv 限定；
3. 用（转换后的）操作数**拷贝初始化**异常对象（[[dcl.init.general]]）。

所以 `const int x = 1; throw x;` 抛出的是 `int`；`throw "abc";` 抛出的是 `const char*`（底层 `const` 保留）；`throw f;`（`f` 是函数）抛出的是函数指针。

¶3 还规定了三种**非良构**的异常对象类型：

- 不完整类型（[[basic.types.general]]）；
- 抽象类类型（[[class.abstract]]）；
- 指向不完整类型的指针，**除了** cv `void*`。

```cpp title="bad-exception-types.cpp" error
struct Abs { virtual void f() = 0; };
struct Inc;

void a(Abs& r) { throw r; }     // error: 异常对象类型是 Abs，抽象类
void b(Inc* p) { throw p; }     // error: 指向不完整类型的指针
void c(void* p) { throw p; }    // OK: void* 例外
```

为什么指向不完整类型的指针也不行？因为 handler 匹配需要检查指针转换（派生到基类，[[except.handle#3]]），而这要求在**抛出点**就把完整的类层次信息编码进异常的运行时类型信息里；类型不完整时这些信息不存在。`void*` 不参与派生到基类的转换，所以没有问题。

`throw r;` 中 `r` 的静态类型是 `Abs&`，但异常对象的类型是 `Abs`——**`throw` 总是按操作数的静态类型复制**，它不知道 `r` 实际引用的是哪个派生类对象。这正是"切片"陷阱的来源（见下文 `throw e;` 与 `throw;`）。

## 异常对象的存储与销毁（¶4）

### 存储方式未指定

¶4 第一句：异常对象的内存以**未指定的方式**分配，除了 [[basic.stc.dynamic.allocation]] 中的注：**全局分配函数（`operator new`）不会被调用**来为异常对象分配存储。

这意味着：

- 替换全局 `operator new` 不会影响异常对象的分配；
- 实现可以使用专门的机制。Itanium C++ ABI 用 `__cxa_allocate_exception`：通常走 `malloc`，失败时退回到一个预留的紧急缓冲区，以保证在内存耗尽时仍能抛出 `std::bad_alloc`（见 [[toolchain/exception-implementation]]）。

异常对象"具有动态存储期"只是说它的生存期不受作用域约束，而不是说它在 `new` 出来的堆上。

### 重抛：同一个异常对象

如果 handler 以**重抛**的方式退出（`throw;`，[[expr.throw#3]]），控制被传给**同一个异常对象**的另一个 handler。重抛不创建新对象，这是 `throw;` 和 `throw e;` 的根本区别。

### 潜在销毁点与"最后一个"

异常对象何时销毁？¶4 定义了两种**潜在销毁点**（points of potential destruction）：

- ¶4.1 该异常的某个**活动 handler** 以**重抛以外**的任何方式退出时——紧接在 handler 中 *exception-declaration* 所声明的对象（若有）销毁之后；
- ¶4.2 一个引用该异常对象的 `std::exception_ptr` 对象被销毁时——在 `std::exception_ptr` 的析构函数返回之前。

在所有潜在销毁点中，有一个**未指定的最后一个**，异常对象在那里被销毁；其他所有潜在销毁点都 **happens before** 这最后一个。之后实现可以以未指定的方式释放内存。

为什么要这么复杂？因为 `std::exception_ptr` 让异常对象可以**比 handler 活得更久**，甚至被另一个线程持有：

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
        p = std::current_exception();   // 现在有两个潜在销毁点：handler 退出、p 销毁
    }                                   // handler 退出：不是最后一个，对象不销毁

    std::thread t([p] {                 // 另一个线程里再持有一份 exception_ptr
        try { std::rethrow_exception(p); }
        catch (const std::exception& e) { std::printf("thread: %s\n", e.what()); }
    });
    t.join();
}                                       // 最后一个 exception_ptr 销毁时，异常对象才销毁
```

实现通常用**引用计数**（[[propagation#6]] 注 1）：handler 和每个 `exception_ptr` 各持有一个计数，计数归零的那个销毁点就是"最后一个"。由于多个线程可能同时释放引用，标准只要求"其余销毁点 happens before 最后一个"——这正是原子引用计数提供的保证。注 2 补充：除此之外，异常处理**不隐含任何线程同步**。

注 3：被抛出的异常**不会自己传播到其他线程**，除非被捕获、存储、再借助库函数重抛（[[propagation]]、[[futures]]）。线程的初始函数以异常退出 ⇒ `std::terminate`（[[except.terminate#1]] 第 10 项）。

### `std::current_exception` 可以复制

[[propagation#9]] 规定 `std::current_exception()` 返回的 `exception_ptr` 引用**当前处理的异常，或它的一个副本**；两次调用是否引用同一个对象是未指定的。`std::rethrow_exception` 也可以抛出副本（[[propagation#11]]）。

这一自由度是为了照顾那些异常对象分配在**栈上**的实现：handler 结束后栈帧就没了，要让 `exception_ptr` 活得更久只能复制到堆上。Itanium ABI 的实现把异常对象放在堆上，所以不需要复制：

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

¶5 设 `T` 是异常对象的类型。要求：**在与 `T` 无关的上下文中**，从 `const T` 类型的 lvalue 拷贝初始化一个 `T` 对象必须是良构的。若 `T` 是类类型，选中的构造函数被 odr-use（[[basic.def.odr]]），`T` 的析构函数是**潜在调用**的（[[class.dtor#14]]）。

逐词理解：

- "**从 `const T` lvalue 拷贝**"：要求 `T` 有可用的**拷贝**构造函数，而不仅仅是移动构造函数。原因就是上一小节：`std::current_exception` 和 `std::rethrow_exception` 可能复制异常对象，而它们是在运行时、在与抛出点无关的地方进行复制的，编译器必须在**抛出点**就确保这个拷贝构造函数存在（并实例化、生成代码）。
- "**与 `T` 无关的上下文**"：访问检查不能借助抛出点的权限。即使你在 `T` 的成员函数里 `throw *this;`，私有的拷贝构造函数也不算可用——因为将来复制它的是库代码。
- "**析构函数潜在调用**"：要求析构函数可访问、未被删除（[[class.dtor#14]]）。

```cpp title="move-only-throw.cpp" error
#include <memory>

struct MoveOnly {
    MoveOnly() = default;
    MoveOnly(MoveOnly&&) = default;      // 拷贝构造函数被隐式删除
};

void f() { throw MoveOnly{}; }           // 按 ¶5 非良构：不能从 const MoveOnly 拷贝初始化
void g() { throw std::make_unique<int>(1); }   // 同理
```

!!! impl "编译器现状"
    本机 Clang 23 **接受**上面的代码，不给任何诊断——这是实现与标准的差异。实践中大量代码抛出 move-only 类型并"正常工作"，那是因为 libc++abi 的 `current_exception` 从不复制。按标准这类代码是非良构的，可移植代码不应依赖它。

    这一要求的来历：C++11 之前只要求拷贝构造函数在"即使被消除"时也可访问；C++17 时代的措辞要求"拷贝初始化选中的构造函数和把操作数视为 lvalue 时选中的构造函数"都可用，以支持 `current_exception` 的复制（CWG1863）；当前草案的写法（"从 `const T` lvalue、在无关上下文中"）是 C++23 之后进一步澄清的结果。

## "未捕获"与"已捕获"（¶6–¶8）

这三段给出 `std::uncaught_exceptions()` 依据的精确定义：

- ¶6 异常在**异常对象初始化完成之后**、到**该异常的某个 handler 激活完成**（[[except.handle#9]]：handler 参数初始化完毕）之前，处于**未捕获**（uncaught）状态。注 4：因此在由它引起的整个栈回溯期间，异常都是"未捕获"的。
- ¶7 被**重抛**的异常（`throw;` 或 `std::rethrow_exception`），从重抛那一刻起到再次被捕获为止，重新处于未捕获状态。
- ¶8 handler 变为活动时，异常被视为**已捕获**（caught）。注 6：一个异常可以既有活动的 handler，又处于未捕获状态——重抛之后，原 handler 仍然活动（它还没退出），但异常又在找新的 handler 了。

注意"未捕获"区间的**起点**：异常对象初始化**完成之后**。在构造异常对象期间抛出的异常（例如 `throw std::string(...)` 时 `std::string` 构造函数抛出 `bad_alloc`）只是普通的异常——原来那个 `throw` 根本没有发生，不会有"两个异常同时飞"的问题。

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
        throw E{};                // E{} 直接初始化异常对象（复制消除），不调用拷贝构造
    } catch (E e) {               // 用拷贝构造初始化 handler 参数：激活尚未完成，仍为 1
        Probe p{"handler"};       // handler 已激活：0
    }
}
```

本机输出：

```text
unwind   uncaught=1
copy     uncaught=1
handler  uncaught=0
```

`std::uncaught_exceptions()` 的典型用途是 **scope guard**：在析构函数里比较"构造时的计数"与"析构时的计数"，判断自己是否因栈回溯而被析构，从而决定提交还是回滚：

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
        try { Transaction t; } catch (...) {}   // 在栈回溯中新开的事务：正常提交
    }
};

int main() {
    { Transaction t; }                          // commit
    try { Transaction t; throw 1; } catch (int) {}   // rollback
    try { Inner i; throw 2; } catch (int) {}    // commit——计数比较而非 bool 才能区分
}
```

C++17 之前只有 `bool std::uncaught_exception()`，它在上面第三种情况里会错误地返回 `true`（"有异常在飞"），导致回溯中新建的事务被误回滚。这就是 C++17 引入**计数**版本 `uncaught_exceptions()` 并在 C++20 移除旧函数的原因（[[uncaught.exceptions]]）。

## 异常处理机制直接调用的函数再抛异常 ⇒ terminate（¶9）

¶9 如果异常处理机制在处理一个**未捕获**的异常时，**直接调用**的函数以异常退出，调用 `std::terminate`。

"处理未捕获的异常时直接调用的函数"包括：

- 栈回溯中的析构函数（注 7）；
- 初始化 handler 参数时的拷贝构造函数（标准例 2）。

**不**包括初始化异常对象本身时调用的构造函数：那时异常对象尚未初始化完成，异常还不处于"未捕获"状态（¶6），构造函数抛出的异常只是取代了原来那次抛出。

!!! std
    If the exception handling mechanism handling an uncaught exception directly invokes a function that exits via an exception, the function `std::terminate` is invoked.

    异常处理机制在处理未捕获异常时，若它直接调用的函数以异常退出，则调用 `std::terminate`。

**为什么**不能有两个异常同时传播？因为语言没有任何办法把两个异常"合并"：handler 只能接一个对象，栈回溯只能朝一个方向走。C++ 选择了最简单、最确定的处理：直接终止。

```cpp run title="throw-during-unwind.cpp" ok
#include <cstdio>
#include <cstdlib>
#include <exception>

struct Bomb { ~Bomb() noexcept(false) { throw 2; } };

int main() {
    std::set_terminate([] { std::fputs("terminate\n", stderr); std::abort(); });
    try {
        Bomb b;
        throw 1;          // 回溯时 ~Bomb 抛出 2 ⇒ std::terminate
    } catch (...) {
        std::puts("never reached");
    }
}
```

（程序本身良构，运行时一定以 `std::terminate` 结束。）标准例 2 展示了更隐蔽的情况：handler 按值捕获时，异常处理机制要调用拷贝构造函数初始化 handler 参数——此时异常仍未捕获（¶6），若拷贝构造函数抛出，同样 terminate：

```cpp run title="copy-into-handler.cpp" ok
#include <cstdio>
#include <cstdlib>
#include <exception>

struct C {
    C() { }
    C(const C&) {
        if (std::uncaught_exceptions())
            throw 0;      // 拷贝到 handler 参数时抛出
    }
};

int main() {
    std::set_terminate([] { std::fputs("terminate\n", stderr); std::abort(); });
    try {
        throw C();        // 若 handler 参数的拷贝没有被消除，则调用 std::terminate
    } catch (C) { std::puts("caught"); }
}
```

"若没有被消除"：[[class.copy.elision#1]]（第 4 项）允许把 handler 参数视为异常对象的别名而省略拷贝（当 handler 不会改变异常对象且行为不受影响时）。本机 Clang 23 **不**消除这次拷贝，程序调用 `std::terminate`。

另一个关键词是**直接**。如果析构函数内部自己 `try { … throw … } catch (…) {}`，异常在析构函数内被处理掉、没有"以异常退出"析构函数，那就完全没问题——见上面 `Inner` 的例子。

## 重抛与 `throw e;`（[[expr.throw]] 回顾）

不带操作数的 `throw;` **重抛当前处理的异常**（[[except.handle#10]]）：重新激活现有的异常对象，不创建新对象，异常重新变为未捕获。若当前没有正在处理的异常，调用 `std::terminate`（[[expr.throw#3]]，[[except.terminate#1]] 第 8 项）。

`throw e;` 则是一次全新的抛出：按 `e` 的**静态类型**拷贝初始化一个**新的**异常对象。

```cpp run title="rethrow-vs-throw-e.cpp" ok
#include <cstdio>

struct B { virtual const char* who() const { return "B"; } };
struct D : B { const char* who() const override { return "D"; } };

int main() {
    try {
        try { throw D{}; }
        catch (B& b) { throw b; }      // 新异常对象，类型是 B：切片！
    } catch (B& b) { std::printf("throw b; -> %s\n", b.who()); }

    try {
        try { throw D{}; }
        catch (B&) { throw; }          // 重抛原来的 D 对象
    } catch (B& b) { std::printf("throw;   -> %s\n", b.who()); }
}
```

输出 `throw b; -> B` 与 `throw;   -> D`。

`throw;` 不必**词法上**出现在 handler 内：从 handler 中调用的函数里写 `throw;` 同样重抛当前处理的异常。这是"异常分派函数"惯用法的基础：

```cpp run title="dispatcher.cpp" ok
#include <cstdio>
#include <stdexcept>

int to_error_code() {          // 只能在 handler 内（直接或间接）调用
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

## 常量求值中的异常 {{c++26}}

C++26 之前，*throw-expression* 在常量求值中被求值就使表达式不是核心常量表达式——只能用来"在编译期制造错误"。C++26（[[P3068R6]]）允许在常量求值中**抛出并捕获**异常，条件见 [[expr.const.core#2]]：

- 第 24 项：构造异常对象可以出现在常量求值中，**只要**该异常对象以及 `std::current_exception`/`std::rethrow_exception` 创建的所有隐式副本都在该求值**内部**被销毁——即异常必须在常量求值内部被捕获、处理完毕，不能"逃出"到运行时；
- 第 25 项：不带操作数的 `throw;` 只有在当前处理的异常是在本次求值中构造的时候才允许。

配合这一改动，`std::exception_ptr` 的成员、`std::make_exception_ptr`、`std::rethrow_exception` 等也成为 `constexpr`（[[propagation#8]]），许多标准异常类型的成员也是。

```cpp title="constexpr-exceptions.cpp"
struct ParseError { int pos; };

constexpr int parse_digit(char c) {
    if (c < '0' || c > '9') throw ParseError{0};
    return c - '0';
}

constexpr int safe_parse(char c) {
    try { return parse_digit(c); }
    catch (ParseError) { return -1; }   // 异常在常量求值内部被捕获、销毁
}

static_assert(safe_parse('7') == 7);
static_assert(safe_parse('x') == -1);   // C++26: OK；C++23: 不是常量表达式

constexpr int bad = parse_digit('x');   // error: 异常逃出常量求值
```

!!! impl "编译器现状"
    本机 Clang 23 尚未实现这一特性：`static_assert(safe_parse('x') == -1)` 被拒绝，诊断指向 `throw` 子表达式"在常量表达式中无效"。按标准，只有最后一行是错误的。上面的代码块因此不标判定。

一个直接的好处：同一个函数在编译期和运行期可以使用同一套错误报告机制，而不必用"编译期调用一个非 `constexpr` 函数来制造错误"的老技巧。

## 陷阱

!!! pitfall "`throw` 按静态类型复制"
    `void report(const std::exception& e) { throw e; }` 抛出的是 `std::exception`，不是调用者传进来的 `std::runtime_error`。要保留动态类型，要么在 handler 里用 `throw;`，要么用 `std::rethrow_exception(std::current_exception())`，要么让异常类提供虚的 `rethrow()` 成员。

!!! pitfall "抛出指向局部对象的指针"
    `throw &local;` 合法，但异常对象是一个**指针**，栈回溯后它指向已销毁的对象。异常对象的"动态存储期"只覆盖对象本身（这里是指针），不覆盖它指向的东西。

!!! pitfall "以为 `operator new` 会被用来分配异常对象"
    用自定义全局 `operator new` 统计内存或检测泄漏时，异常对象不会被统计——标准明确说全局分配函数不用于异常对象（[[basic.stc.dynamic.allocation#5]]）。

## 思考题

!!! question "思考题 1"
    以下程序是否一定调用 `std::terminate`？

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

不会。`s` 是因为离开 try 块的作用域而被正常析构的，而不是被栈回溯析构的，此时没有未捕获的异常（`uncaught_exceptions() == 0`），析构函数抛出 `1`，这只是一次普通的抛出，被 `catch (int)` 捕获。¶9 只管"异常处理机制在处理**未捕获**异常时直接调用的函数"。

注意析构函数必须声明 `noexcept(false)`：否则析构函数隐式 `noexcept`（[[except.spec#8]]），抛出时 handler 搜索会离开非抛出函数，触发 [[except.handle#7]] 的 `std::terminate`。
</details>

!!! question "思考题 2"
    `throw;` 出现在一个 catch 子句里，而该 catch 子句**又**位于另一个 handler 内部（嵌套的 try）。它重抛的是哪个异常？

    ```cpp
    try { throw 1; }
    catch (int) {
        try { throw 2.0; }
        catch (double) { }
        throw;      // 重抛 1 还是 2.0？
    }
    ```

<details markdown="1">
<summary>答案</summary>

重抛 `1`。`throw;` 重抛**当前处理的异常**（[[except.handle#10]]）：拥有"最近激活且仍然活动的 handler"的异常。`catch (double)` 已经退出，不再活动；仍然活动的是 `catch (int)`，所以当前处理的异常是 `1`。如果把 `throw;` 移进 `catch (double)` 内部，重抛的就是 `2.0`。
</details>

!!! question "思考题 3"
    为什么 ¶5 要求在"与 `T` 无关的上下文"中检查拷贝构造函数？举一个只有加上这个限定才会被判为非良构的例子。

<details markdown="1">
<summary>答案</summary>

因为将来复制异常对象的是 `std::current_exception` 等库代码，它们对 `T` 没有任何特权。例子：

```cpp
class Err {
    Err(const Err&) = default;   // 私有拷贝构造
public:
    Err() = default;
    Err(Err&&) = default;
    void raise() { throw *this; }   // 在成员函数里，私有拷贝构造是可访问的
};
```

在 `raise` 内部，从 `const Err` lvalue 拷贝初始化是可访问的；但 ¶5 要求在**无关上下文**中检查，私有拷贝构造不可访问，所以 `throw *this;` 非良构。
</details>

## 小结

| 问题 | 答案 | 出处 |
|---|---|---|
| 异常对象的类型 | 操作数经数组/函数到指针转换、去掉顶层 cv | [[expr.throw#2]] |
| 禁止的类型 | 不完整类型、抽象类、指向不完整类型的指针（`void*` 除外） | ¶3 |
| 存在哪 | 未指定；不调用全局 `operator new` | ¶4，[[basic.stc.dynamic.allocation#5]] |
| 何时销毁 | 最后一个潜在销毁点：活动 handler 非重抛退出 / 最后一个 `exception_ptr` 销毁 | ¶4 |
| 类型要求 | 能在无关上下文中从 `const T` lvalue 拷贝初始化；析构函数潜在调用 | ¶5 |
| 未捕获区间 | 异常对象初始化完成 → handler 激活完成；重抛后再次未捕获 | ¶6–¶8 |
| 两个异常同时传播 | 不允许：`std::terminate` | ¶9 |
| 常量求值 {{c++26}} | 可以抛出，但必须在求值内部捕获并销毁 | [[expr.const.core#2]] |
