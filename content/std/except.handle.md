---
title: 处理异常
summary: handler 的类型限制与调整；handler 匹配的四种情形（同类型、无歧义 public 基类、有限的指针转换、nullptr_t）——没有其他转换；按出现顺序尝试；catch(...)；noexcept 边界与找不到 handler 时的 std::terminate；活动 handler 与"当前处理的异常"；function-try-block 的特殊规则；handler 参数的初始化
status: done
related: except.throw, except.pre, except.ctor, except.spec, except.terminate, expr.throw, conv.ptr, conv.mem, conv.qual, conv.fctptr, class.copy.elision, propagation
tags: 异常, handler, catch, 匹配
updated: 2026-10-17
---

本节是第 14 章的心脏：给定一个异常对象，**哪个 handler 会接住它**，handler 的参数如何初始化，什么时候算"正在处理"一个异常，以及搜索失败时会发生什么。

C++ 的 handler 匹配看起来像函数调用的实参—形参匹配，但规则**严格得多**：没有整数提升、没有算术转换、没有用户定义转换。理解这一点的关键是：匹配在**运行时**进行，只能依据异常对象的**动态类型信息**（`std::type_info` 及 ABI 附加的类层次描述），不可能在运行时做重载决议。

## handler 的类型限制与调整（¶1–¶2）

¶1 *exception-declaration* 描述了能让该 handler 被进入的异常类型。它**不得**表示：

- 不完整类型、抽象类类型、右值引用类型；
- 指向不完整类型的指针或引用——**除了** "指向 cv `void` 的指针"。

```cpp title="bad-handlers.cpp" error
struct Abs { virtual void f() = 0; };
struct Inc;

void f() {
    try {} catch (int&&) {}     // error: 右值引用
    try {} catch (Abs) {}       // error: 抽象类（按值）
    try {} catch (Inc&) {}      // error: 引用不完整类型
    try {} catch (Inc*) {}      // error: 指向不完整类型的指针
}
```

```cpp title="ok-handlers.cpp" ok
struct Abs { virtual void f() = 0; };

void f() {
    try {} catch (Abs&) {}      // OK: 抽象类的引用
    try {} catch (const Abs*) {}// OK: 指向完整（抽象）类型的指针
    try {} catch (void*) {}     // OK: void* 例外
}
```

为什么禁止右值引用？异常对象总是 lvalue（它有名字般的身份，可能被多个 handler、多个 `exception_ptr` 访问），把它绑定到 `T&&` 会暗示"可以从中移走"，而实际上 `throw;` 之后别的 handler 还要用它。要修改异常对象，用 `T&` 即可。

¶2 handler 的类型若是"`T` 的数组"或函数类型 `T`，**调整**为"指向 `T` 的指针"——与函数形参的调整（[[dcl.fct]]）一样。因为抛出数组或函数时异常对象本来就已经退化为指针（[[expr.throw#2]]），这条调整让写法对得上：

```cpp run title="array-handler.cpp" ok
#include <cstdio>

void callback() {}

int main() {
    int a[3] = {1, 2, 3};
    try { throw a; }                         // 异常对象类型 int*
    catch (int x[3]) { std::printf("%d\n", x[1]); }      // handler 调整为 int*

    try { throw callback; }                  // 异常对象类型 void(*)()
    catch (void f()) { std::puts("function -> pointer"); } // handler 调整为 void(*)()
}
```

而**数组的引用**或**函数的引用**类型的 handler 永远不会匹配任何异常对象（注 1）：异常对象不可能是数组或函数类型。

## 匹配规则（¶3）

¶3 是本节最重要的一段。类型为 `E` 的异常对象与 handler 匹配，当且仅当下列四种情形之一成立：

!!! std
    A *handler* is a match for an exception object of type `E` if (3.1) The *handler* is of type *cv* `T` or *cv* `T&` and `E` and `T` are the same type (ignoring the top-level *cv-qualifiers*), or …

| 项 | handler 类型 | 条件 |
|---|---|---|
| ¶3.1 | cv `T` 或 cv `T&` | `E` 与 `T` 是同一类型（忽略顶层 cv） |
| ¶3.2 | cv `T` 或 cv `T&` | `T` 是 `E` 的**无歧义 public 基类** |
| ¶3.3 | cv `T` 或 `const T&`，`T` 是指针或成员指针 | `E` 是指针或成员指针，可以通过以下一个或多个转换变成 `T`：<br>¶3.3.1 不涉及 private/protected/歧义类的标准指针转换；<br>¶3.3.2 函数指针转换（去掉 `noexcept`）；<br>¶3.3.3 限定转换（加 cv） |
| ¶3.4 | cv `T` 或 `const T&`，`T` 是指针或成员指针 | `E` 是 `std::nullptr_t` |

**就这些**。整数提升、算术转换、`bool` 转换、用户定义转换、派生类到 private 基类、甚至 `int` 到 `const int&` 之外的任何东西，统统不参与匹配。

### 本机实测矩阵

用一个模板 `test<Thrown, Handler>` 实测（libc++abi，Clang 23）：

```cpp run title="match-matrix.cpp" ok
#include <cstdio>
#include <cstddef>

struct B { virtual ~B() = default; };
struct D : B {};
struct P : private B {};
struct B1 : B {}; struct B2 : B {};
struct Amb : B1, B2 {};          // 两个 B 子对象：B 是歧义基类

template<class Thrown, class H>
const char* test(Thrown t) {
    try { throw t; }
    catch (H) { return "match"; }
    catch (...) { return "no match"; }
}

void fn() noexcept {}

int main() {
    std::printf("%-28s %s\n", "int      -> long",          test<int, long>(1));           // 没有算术转换
    std::printf("%-28s %s\n", "int      -> const int&",    test<int, const int&>(1));     // 3.1
    std::printf("%-28s %s\n", "D        -> B&",            test<D, B&>(D{}));             // 3.2
    std::printf("%-28s %s\n", "D        -> B (sliced)",    test<D, B>(D{}));              // 3.2
    std::printf("%-28s %s\n", "P        -> B&",            test<P, B&>(P{}));             // private 基类
    std::printf("%-28s %s\n", "Amb      -> B&",            test<Amb, B&>(Amb{}));         // 歧义基类
    std::printf("%-28s %s\n", "D*       -> const B*",      test<D*, const B*>(nullptr));  // 3.3.1 + 3.3.3
    std::printf("%-28s %s\n", "D*       -> B* const&",     test<D*, B* const&>(nullptr)); // 3.3
    std::printf("%-28s %s\n", "D*       -> void*",         test<D*, void*>(nullptr));     // 3.3.1
    std::printf("%-28s %s\n", "P*       -> B*",            test<P*, B*>(nullptr));        // private
    std::printf("%-28s %s\n", "int**    -> const int* const*", test<int**, const int* const*>(nullptr)); // 3.3.3
    std::printf("%-28s %s\n", "fp noexcept -> fp",         test<void(*)() noexcept, void(*)()>(fn)); // 3.3.2
    std::printf("%-28s %s\n", "fp       -> fp noexcept",   test<void(*)(), void(*)() noexcept>(nullptr));
    std::printf("%-28s %s\n", "nullptr_t -> int*",         test<std::nullptr_t, int*>(nullptr)); // 3.4
    std::printf("%-28s %s\n", "int(0)   -> int*",          test<int, int*>(0));           // 注 1
}
```

输出：

```text
int      -> long             no match
int      -> const int&       match
D        -> B&               match
D        -> B (sliced)       match
P        -> B&               no match
Amb      -> B&               no match
D*       -> const B*         match
D*       -> B* const&        match
D*       -> void*            match
P*       -> B*               no match
int**    -> const int* const* match
fp noexcept -> fp            match
fp       -> fp noexcept      no match
nullptr_t -> int*            match
int(0)   -> int*             no match
```

与标准逐项一致。几个值得展开的点：

**`int` 不匹配 `long`**。函数调用里 `void f(long); f(1);` 再自然不过，但 `throw 1;` 永远不会被 `catch (long)` 接住。原因：如果允许算术转换，运行时库就得为每一对算术类型实现转换逻辑，而且会引出"多个 handler 都能转换时选哪个"的问题；C++ 选择了"按顺序找第一个**类型上**匹配的"这一简单模型（¶4）。

**`throw 0` 不匹配指针 handler**（注 1）。字面量 `0` 在编译期是空指针常量，但抛出后异常对象的类型就是 `int`——运行时已经没有"字面量 0"这个概念了。`throw nullptr;` 才能被指针 handler 接住（¶3.4）。`throw NULL;` 的结果取决于 `NULL` 的定义（可能是 `0`、`0L` 或 `nullptr`），是一个可移植性陷阱。

**基类必须无歧义且 public**。这与"派生类到基类的转换在抛出点是否可访问"无关——即使在 `P` 的成员函数里抛出 `P`（那里 `P` 到 `B` 的转换是可访问的），`catch (B&)` 也接不住。匹配看的是**类型本身**的继承关系，而不是任何上下文的访问权。

**指针 handler 只能是 `T` 或 `const T&`**。¶3.3/¶3.4 要求 handler 类型为 cv `T` 或 `const T&`：转换后得到的是一个新的指针值（例如派生类指针调整到基类子对象的地址），只能绑定到 `const` 引用或按值复制，不能用非 `const` 引用 `B*&` 绑定——否则通过 `B*&` 赋值会修改一个 `D*` 类型的异常对象，类型系统就被打破了。

!!! impl "libc++abi 与 `B*&`"
    按标准，`throw (D*)p;` 不应匹配 `catch (B*& r)`（`B*&` 不是 `const T&`，而 `D*` 与 `B*` 又不是同一类型）。但本机 libc++abi **会匹配**（在上面的测试中加一行 `test<D*, B*&>` 即可验证）。合理的推测是：Itanium ABI 在 LSDA 中记录的是 handler 类型去掉引用后的 `type_info`，运行时难以区分 `catch (B*)`、`catch (B* const&)` 与 `catch (B*&)`。这属于实现的不符合之处，可移植代码不要依赖它。

!!! lawyer "成员指针的基类→派生类转换"
    ¶3.3 允许 `T` 是成员指针类型，但能用的转换只有 ¶3.3.1 的"标准**指针**转换"（[[conv.ptr]]）、函数指针转换和限定转换。成员指针的"基类成员 → 派生类成员"转换属于 [[conv.mem]]，严格说不是"指针转换"。本机实测 `throw (int B::*)nullptr` **不**匹配 `catch (int D::*)`，与这种字面读法一致。按这种读法，成员指针 handler 只能通过同类型、限定转换、（成员函数指针的）函数指针转换和 `nullptr_t` 匹配。这一点建议对照 [[conv.ptr]] 与 [[conv.mem]] 自行判断。

### ¶3 的例子：类层次

标准例 1 展示了最常见的用法——按异常类层次组织 handler：

```cpp run title="matherr.cpp" ok
#include <cstdio>

class Matherr { public: virtual ~Matherr() = default; };
class Overflow   : public Matherr {};
class Underflow  : public Matherr {};
class Zerodivide : public Matherr {};

void g(int k) {
    if (k == 0) throw Overflow{};
    if (k == 1) throw Underflow{};
    throw Zerodivide{};
}

int main() {
    for (int k = 0; k < 3; ++k) {
        try {
            g(k);
        } catch (const Overflow&) {
            std::puts("Overflow");
        } catch (const Matherr&) {        // 接住 Underflow 与 Zerodivide
            std::puts("other Matherr");
        }
    }
}
```

标准原例按值捕获（`catch (Matherr mm)`），会把派生类对象**切片**成 `Matherr`；实践中应当按 `const&` 捕获。

## 按出现顺序尝试（¶4）

¶4 一个 try 块的 handler **按出现顺序**尝试。第一个匹配的胜出，**不是**"最佳匹配"胜出。

注 2：这使得写出永远执行不到的 handler 成为可能——例如把派生类的 handler 放在其基类的 handler 之后。这不是错误，但编译器通常会警告：

```cpp title="unreachable-handler.cpp" ok
struct B {};
struct D : B {};

void f() {
    try {
    } catch (B&) {
    } catch (D&) {      // 永远到不了这里；Clang: -Wexceptions 警告
    }
}
```

本机 Clang 23 的警告：`exception of type 'D &' will be caught by earlier handler`。这是良构的——标准只要求按顺序尝试。

## `catch (...)`（¶5）

¶5 *exception-declaration* 为 `...` 的 handler 匹配**任何**异常。若出现，它必须是其 try 块的**最后一个** handler（违反则非良构）：

```cpp title="catch-all-last.cpp" error
void f() {
    try {
    } catch (...) {
    } catch (int) {     // error: catch-all 之后不能再有 handler
    }
}
```

`catch (...)` 中无法直接访问异常对象，但可以用 `throw;` 重抛、用 `std::current_exception()` 获取 `exception_ptr`，或调用一个"在 handler 内 `throw;` 再分类捕获"的分派函数（见 [[except.throw]]）。

!!! warning "`catch (...)` 与平台异常"
    在 MSVC 上，若使用 `/EHa` 编译选项，`catch (...)` 还会捕获结构化异常（SEH，如访问违例）；默认的 `/EHsc` 不会。这是 MSVC 的扩展行为，与标准无关。

## 向外继续搜索（¶6）

¶6 若一个 try 块的 handler 中没有匹配的，搜索在**同一线程**中**动态外层**的 try 块中继续。"动态外层"即调用链上更早进入且尚未退出的 try 块（[[except.throw#2]]）。

## 碰到 `noexcept` 边界（¶7）

¶7 若 handler 搜索**离开**一个具有**非抛出异常说明**（[[except.spec]]）的函数的函数体，调用 `std::terminate`。

!!! std
    If the search for a handler exits the function body of a function with a non-throwing exception specification, the function `std::terminate` is invoked.

    若 handler 搜索离开了具有非抛出异常说明的函数的函数体，调用 `std::terminate`。

注 3 与标准例 2 强调：实现**不得**仅仅因为一个表达式在执行时（可能）会从 `noexcept` 函数中抛出，就**拒绝**它：

```cpp run title="noexcept-boundary.cpp" ok
#include <cstdio>
#include <cstdlib>
#include <exception>

extern void f();                    // 潜在抛出

void g() noexcept {
    f();                            // 良构，即使 f 会抛出
    throw 42;                       // 良构：效果相当于调用 std::terminate
}

void f() { }

int main() {
    std::set_terminate([] { std::fputs("terminate\n", stderr); std::abort(); });
    g();
}
```

Clang 对 `throw 42;` 会给出 `-Wexceptions` 警告（"'g' has a non-throwing exception specification but can still throw"），但不会报错。

为什么不做成编译期检查（像 Java 的 checked exception 那样）？因为 C++ 无法在编译期知道一个不带 `noexcept` 的函数是否真的会抛出——大量 C 函数、旧代码、虚函数调用都没有准确的异常说明。若要求 `noexcept` 函数只能调用 `noexcept` 函数，几乎没法写；C++03 的动态异常说明正是因为这类问题而失败的（见 [[except.spec]] 的历史部分）。`noexcept` 被设计成一个**运行时契约 + 优化提示**：违反它的后果确定（terminate），编译器可以据此优化调用方。

注意措辞是"搜索**离开**函数体"：异常若在 `noexcept` 函数**内部**被捕获，没有任何问题：

```cpp title="noexcept-internal-catch.cpp" ok
void may_throw();

void safe() noexcept {
    try { may_throw(); }
    catch (...) { /* 吞掉 */ }      // 异常没有离开函数体：完全合法
}
```

## 找不到 handler（¶8）

¶8 若找不到匹配的 handler，调用 `std::terminate`；在此之前**是否回溯栈由实现定义**（[[except.terminate#2]]）。

在 Itanium ABI 的两阶段模型下，第一阶段（搜索）就能确定没有 handler，此时**不进行回溯**、直接调用 `std::terminate`——于是 core dump 中保留了抛出点的完整调用栈，这对调试极为有用。本机验证：

```cpp run title="no-handler.cpp" impl
#include <cstdio>
#include <cstdlib>
#include <exception>

struct D {
    const char* n;
    ~D() { std::printf("~%s\n", n); std::fflush(stdout); }
};

void g() { D d{"g-local"}; throw 1; }

int main() {
    std::set_terminate([] { std::puts("terminate"); std::fflush(stdout); std::_Exit(0); });
    D m{"main-local"};
    g();                     // 没有任何 handler
}
```

本机（libc++abi）只输出 `terminate`：`g-local` 和 `main-local` 都**没有**被析构。依赖"未捕获的异常也会触发析构函数"的代码是不可移植的；若需要保证清理，在 `main`（以及每个线程的入口函数）里放一个 `catch (...)`。

## 活动 handler 与当前处理的异常（¶9–¶10）

¶9 handler 在其 catch 子句的**参数初始化完成**时变为**活动的**（active）。注 4：此时栈已经回溯完毕。此外，因抛出而进入 `std::terminate` 时，一个**隐式 handler** 被视为活动的（这让 `std::terminate` 的处理函数里可以用 `std::current_exception()` 拿到导致终止的异常）。catch 子句退出时，handler 不再活动。

¶10 拥有**最近激活且仍活动**的 handler 的那个异常，称为**当前处理的异常**（[[g:currently-handled-exception]]，currently handled exception）。`throw;` 重抛它，`std::current_exception()` 返回它。

handler 可以嵌套（handler 内部又有 try/catch），所以同一时刻可能有多个活动 handler，"当前处理的异常"像一个栈的栈顶：

```cpp run title="currently-handled.cpp" ok
#include <cstdio>
#include <exception>

void show() {
    try { throw; }                               // 重抛当前处理的异常
    catch (int i)    { std::printf("int %d\n", i); }
    catch (double d) { std::printf("double %g\n", d); }
}

int main() {
    try { throw 1; }
    catch (int) {
        show();                                  // int 1
        try { throw 2.5; }
        catch (double) { show(); }               // double 2.5：内层 handler 最近激活
        show();                                  // int 1：内层 handler 已退出
    }
}
```

`terminate` 处理函数利用隐式 handler 的例子（libstdc++ 的 verbose terminate handler 能打印未捕获异常的类型，用的也是"终止时仍能取得当前异常"这一点）：

```cpp run title="terminate-handler.cpp" ok
#include <cstdio>
#include <cstdlib>
#include <exception>
#include <stdexcept>

int main() {
    std::set_terminate([] {
        if (auto p = std::current_exception()) {
            try { std::rethrow_exception(p); }
            catch (const std::exception& e) { std::fprintf(stderr, "uncaught: %s\n", e.what()); }
            catch (...) { std::fputs("uncaught: unknown\n", stderr); }
        }
        std::abort();
    });
    throw std::runtime_error("disk on fire");
}
```

## function-try-block 的特殊规则（¶11–¶14）

### 不能在构造/析构函数的 handler 里访问成员（¶11）

¶11 在对象的构造函数或析构函数的 function-try-block 的 handler 中，**引用该对象的任何非静态成员或基类**，行为未定义。原因见 [[except.ctor#3]]：进入 handler 之前，已构造的子对象已经全部被析构了。本机 Clang 23 对下例给出 `-Wexceptions` 警告，但仍然接受（标准不要求诊断 UB）。

```cpp title="ctor-handler-member.cpp" ub
#include <cstdio>
#include <string>

struct Thrower { Thrower() { throw 0; } };

struct S {
    std::string name;
    Thrower t;
    S() try : name("widget"), t() {
    } catch (...) {
        std::puts(name.c_str());   // UB: name 已经被析构
    }
};
```

### `main` 与线程入口的 function-try-block（¶12）

¶12 静态存储期对象的析构函数中、或与静态存储期非块变量相关的构造函数中抛出的异常，**不会**被 `main` 的 function-try-block 捕获。线程存储期的对应情形不会被线程初始函数的 function-try-block 捕获。

道理很简单：这些构造发生在 `main` 开始**之前**、析构发生在 `main` 返回**之后**，`main` 的 try 块根本没有"处于进入状态"。它们抛出的异常直接导致 `std::terminate`（[[except.terminate#1]] 第 5、6 项）：

```cpp run title="static-init-throw.cpp" ok
#include <cstdio>

struct S { S() { throw 1; } };
S s;                                       // 在 main 之前构造，抛出 ⇒ std::terminate

int main() try {
    return 0;
} catch (...) {
    std::puts("never: main 的 handler 捕获不到");
    return 1;
}
```

本机运行输出 `libc++abi: terminating due to uncaught exception of type int` 并以 SIGABRT 结束。

### 构造函数 handler 不能 `return`（¶13）

¶13 构造函数的 function-try-block 的 handler 中出现 `return` 语句，程序**非良构**。见 [[except.pre]] 的例子。

### 流出 handler 末尾（¶14）

¶14 控制到达构造函数或析构函数的 function-try-block 的 handler **末尾**时，**重抛**当前处理的异常。对其他函数，流出 function-try-block 的 handler 末尾等价于流出函数体的复合语句末尾（[[stmt.return]]）——对返回非 `void` 的函数，那是 UB（`main` 除外，等价于 `return 0;`）。

```cpp title="ftb-flow-off.cpp" ub
int parse(const char* s) try {
    return s[0] - '0';
} catch (...) {
    // 流出末尾 ⇒ 等价于流出 parse 的函数体末尾：返回 int 的函数这样做是 UB
}
```

## handler 参数的初始化（¶15–¶16）

¶15 *exception-declaration* 声明的变量（类型 cv `T` 或 cv `T&`）从类型为 `E` 的异常对象初始化：

- ¶15.1 若 `T` 是 `E` 的基类：从一个指代异常对象中**对应基类子对象**的 `T` 类型 lvalue **拷贝初始化**；
- ¶15.2 否则：从一个指代异常对象的 `E` 类型 lvalue 拷贝初始化。

变量的生命周期在 handler 退出时结束，晚于 handler 内初始化的所有自动对象的销毁。

几点推论：

- **按值捕获 = 拷贝**。即使异常对象是临时的，也是从 **lvalue** 拷贝——不会移动（[[class.copy.elision#1]] 注 2：异常对象总是 lvalue，不可能从中移动）。按值捕获一个只有移动构造函数的类型是非良构的。
- **按值捕获基类 = 切片**（¶15.1）。
- **拷贝可以被消除**：[[class.copy.elision#1]] 第 4 项允许把 *exception-declaration* 当作异常对象的别名，前提是除了构造/析构函数的执行之外程序的含义不变。本机 Clang 不做这种消除。
- **初始化期间异常仍是"未捕获"的**（[[except.throw#6]]），拷贝构造函数若抛出 ⇒ `std::terminate`（[[except.throw#9]]）。
- 对指针 handler（¶3.3），参数是转换后的指针值的副本。

¶16（注 5）：handler 声明的是**对象**时，修改它不影响异常对象；声明的是**引用**时，修改引用的对象就是修改异常对象——这对之后的 `throw;` 可见：

```cpp run title="modify-exception.cpp" ok
#include <cstdio>

struct E { int v; };

int main() {
    try {
        try { throw E{1}; }
        catch (E& e) { e.v = 2; throw; }      // 修改异常对象本身
    } catch (E e) { std::printf("%d\n", e.v); }   // 2

    try {
        try { throw E{1}; }
        catch (E e) { e.v = 2; throw; }       // 修改的是副本
    } catch (E e) { std::printf("%d\n", e.v); }   // 1
}
```

## 陷阱

!!! pitfall "按值捕获多态异常"
    `catch (std::exception e)` 会切片，`e.what()` 返回的是 `std::exception::what()`（通常是 "std::exception"），而且多付出一次拷贝。总是用 `catch (const std::exception& e)`。

!!! pitfall "以为 handler 匹配像重载决议"
    `throw 'a';` 不会被 `catch (int)` 接住；`throw std::string("x");` 不会被 `catch (const char*)` 接住；`throw 1.0f;` 不会被 `catch (double)` 接住。唯一的"转换"是派生到 public 基类，和少量指针转换。

!!! pitfall "依赖未捕获异常时的析构"
    找不到 handler 时栈是否回溯由实现定义；主流实现**不回溯**。若需要 RAII 清理（刷新日志、删除临时文件），必须在入口函数里加 `catch (...)`。

## 思考题

!!! question "思考题 1"
    下面哪个 handler 会被选中？

    ```cpp
    struct B {};
    struct D : B {};
    try { throw D{}; }
    catch (const B&) { /* #1 */ }
    catch (D&)       { /* #2 */ }
    ```

<details markdown="1">
<summary>答案</summary>

#1。handler 按出现顺序尝试（¶4），`const B&` 已经匹配（¶3.2：`B` 是 `D` 的无歧义 public 基类），所以 #2 永远到不了——即使对函数重载而言 `D&` 是"更好的"匹配。
</details>

!!! question "思考题 2"
    `throw (char*)buf;` 能否被 `catch (const char* const& p)` 捕获？能否被 `catch (const char*& p)` 捕获？

<details markdown="1">
<summary>答案</summary>

`const char* const&` 可以：`T = const char*` 是指针类型，handler 形式是 `const T&`，`char*` 经限定转换得到 `const char*`（¶3.3.3）。

`const char*&` 按标准不可以：它是 `T&`（非 const 引用），不满足 ¶3.3 要求的 cv `T` 或 `const T&`；而 ¶3.1 要求 `E` 与 `T` 同类型，`char*` 与 `const char*` 不同。（与 `B*&` 的情况类似，某些运行时库实际上可能匹配，见上文的实现说明。）

如果允许绑定，`p = "literal";` 就会把一个 `const char*` 写进类型为 `char*` 的异常对象，之后 `catch (char* q)` 就能通过 `q` 修改字符串字面量——这正是 [[conv.qual]] 禁止 `char**` → `const char**` 的同一个理由。
</details>

!!! question "思考题 3"
    设 `main` 只做一件事：调用 `f()`。比较 `void f() noexcept { throw 1; }` 与 `void f() { throw 1; }` 在标准层面的区别。

<details markdown="1">
<summary>答案</summary>

两者都调用 `std::terminate`，但依据不同、对栈回溯的规定也不同：

- `noexcept` 版本：handler 搜索离开非抛出函数的函数体（¶7），是否回溯、回溯多少由实现定义（[[except.terminate#2]]，可以"部分回溯"）。
- 无 `noexcept` 版本：找不到 handler（¶8），是否回溯由实现定义（只能是"回溯"或"不回溯"，不能部分回溯）。

在 Itanium 实现中（本机 Clang 实测），前者 `f` 有一个"捕获一切并调用 terminate"的着陆点，搜索阶段把它当作 handler，于是回溯一直进行到 `f` 的帧为止（`f` 自己的局部对象不析构）；后者搜索阶段找不到任何 handler，直接 terminate，完全不回溯。
</details>

## 小结

!!! summary
    - handler 类型不能是不完整类型、抽象类、右值引用、指向不完整类型的指针/引用（`void*` 除外）；数组/函数类型的 handler 调整为指针。
    - 匹配只有四种：同类型；无歧义 public 基类；指针/成员指针经有限转换（标准指针转换、去 `noexcept`、加 cv），handler 须为 `T` 或 `const T&`；`nullptr_t` 到指针。**没有**算术转换和用户定义转换。
    - 按出现顺序取第一个匹配者；`catch (...)` 必须在最后。
    - 搜索离开 `noexcept` 函数 ⇒ `std::terminate`；找不到 handler ⇒ `std::terminate`，是否回溯由实现定义。
    - 参数初始化完成时 handler 变为活动；最近激活且仍活动的 handler 的异常是"当前处理的异常"。
    - 构造/析构函数的 function-try-block：handler 中访问成员是 UB；构造函数 handler 不能 `return`；到达末尾自动重抛。
