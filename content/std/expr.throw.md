---
title: 抛出异常
summary: "throw-expression 的类型是 void；异常对象的类型由操作数的静态类型（退化、去顶层 cv）决定并从操作数复制初始化；throw e 与 throw; 的区别（切片 vs 保留原对象）；没有当前处理的异常时 throw; 调用 std::terminate；C++26 起常量求值中可以抛出并捕获异常"
status: done
papers: P3068
related: except.throw, except.handle, except.terminate, class.copy.elision, expr.cond, expr.comma, expr.const.core, propagation
tags: 异常, throw, 常量求值
updated: 2026-10-18
---

`throw` 在 C++ 中是一个**表达式**，而不是语句。这一点有实际意义：它可以出现在条件运算符的一个分支里（[[expr.cond#2]]）、逗号表达式里、甚至 C++11 constexpr 函数唯一的 `return` 语句里。本节规定 *throw-expression* 作为表达式的性质——类型、异常对象如何初始化、无操作数的 `throw;` 做什么；而异常的传播、处理器匹配、栈展开、异常对象的生命周期等由第 14 章 [[except.throw]]、[[except.handle]] 负责。

## 文法与类型（¶1）

```text
throw-expression:
    throw assignment-expression(opt)
```

*throw-expression* 与赋值表达式、*yield-expression* 同属 *assignment-expression* 这一级（[[expr.assign]]），所以 `throw a, b` 是 `(throw a), b`，`throw x = y` 抛出的是赋值的结果。

¶1 *throw-expression* 的类型是 **`void`**。它永远不会正常完成求值（要么转移控制到处理器，要么调用 `std::terminate`），所以给它任何"值"都没有意义。`void` 类型使它可以出现在任何允许 `void` 表达式的地方，而 [[expr.cond]] ¶2.1 专门为它开了口子：条件运算符的一边是 *throw-expression* 时，结果取另一边的类型和值类别。

```cpp run title="throw-expression.cpp" ok
#include <stdexcept>
#include <type_traits>

int x = 0;
static_assert(std::is_void_v<decltype(throw 1)>);
static_assert(std::is_same_v<decltype((true ? x : throw 1)), int&>);   // 仍是 lvalue

int checked_div(int a, int b) {
    return b != 0 ? a / b : throw std::domain_error("division by zero");
}

int main() { return checked_div(6, 3) == 2 ? 0 : 1; }
```

## 带操作数的 `throw`（¶2）

¶2 带操作数的 *throw-expression* **抛出一个异常**（[[except.throw]]）。确定异常对象的步骤是：

1. 对操作数做**数组到指针**和**函数到指针**转换；
2. 异常对象的类型 = 转换后操作数的类型，**去掉顶层 cv 限定**；
3. 异常对象从（转换后的）操作数**复制初始化**（[[dcl.init.general]]）。

几个直接推论：

```cpp run title="throw-type.cpp" ok
#include <cstdio>

void fn() {}

int main() {
    try { throw "Help!"; }                       // const char[6] → const char*
    catch (const char* p) { std::puts(p); }

    try { const int c = 1; throw c; }            // 去掉顶层 const：异常对象类型是 int
    catch (int& e) { std::puts("caught int&"); } // 可以用非 const 引用捕获

    try { throw fn; }                            // 函数 → 函数指针
    catch (void (*)()) { std::puts("caught function pointer"); }
}
```

### 异常对象的类型取**静态类型**

"操作数的类型"指的是表达式的**静态类型**。通过基类引用抛出派生类对象，异常对象是**基类**类型——发生切片：

```cpp run title="throw-static-type.cpp" ok
#include <cstdio>

struct Base { virtual ~Base() = default; virtual const char* name() const { return "Base"; } };
struct Derived : Base { const char* name() const override { return "Derived"; } };

int main() {
    try {
        Derived d;
        Base& r = d;
        throw r;                       // 异常对象类型为 Base（从 r 复制初始化）：切片
    } catch (Base& e) {
        std::puts(e.name());           // 输出 "Base"
    }
}
```

这是为什么"虚克隆 + 虚抛出"（在基类里声明 `virtual void raise() const { throw *this; }`、派生类重写）的惯用法存在：只有在静态类型已知是派生类的地方写 `throw *this`，才能抛出完整的派生类对象。C++11 的 `std::exception_ptr`（[[propagation]]）让多数此类场景有了更好的解决方案。

### 复制初始化、移动与消除

"从操作数复制初始化"遵循一般的初始化规则：

- 操作数是 prvalue（如 `throw MyError(...)`）时，C++17 起保证直接在异常对象的存储中构造，**没有**复制或移动（[[dcl.init]]）；
- 操作数是**自动存储期局部变量的名字**（不是函数参数、不是 `catch` 参数），且其作用域不越出最内层的 `try` 块时，该名字是**隐式可移动实体**，先尝试**移动**（[[class.copy.elision]] ¶1.2 还允许把复制/移动整个省略）；
- 否则复制。

```cpp run title="throw-move.cpp" ok
#include <string>
#include <cstdio>

struct Err {
    std::string msg;
    Err(std::string m) : msg(std::move(m)) {}
    Err(const Err& o) : msg(o.msg) { std::puts("copy"); }
    Err(Err&& o) noexcept : msg(std::move(o.msg)) { std::puts("move"); }
};

int main() {
    try {
        Err e("boom");
        throw e;                 // 输出 "move"（或被消除而什么都不输出）
    } catch (const Err&) {}
}
```

### 对异常类型的要求

[[except.throw]] 对异常对象的类型 `T` 有两条编译期要求：

- `T` 不能是**不完整类型**、**抽象类**，或指向不完整类型（`cv void` 除外）的指针（[[except.throw#3]]）；
- 从 `const T` 左值**复制初始化** `T` 必须良构（[[except.throw#5]]）——即使这次 `throw` 实际用的是移动。理由是异常对象可能被 `std::current_exception` 等机制复制（[[propagation]]），实现需要一个可用的复制构造函数。

```cpp title="throw-requirements.cpp" error
struct Incomplete;
struct Abstract { virtual void f() = 0; };

void f(Incomplete* p, Abstract& a) {
    throw p;          // error: 指向不完整类型的指针
    throw a;          // error: 异常对象类型 Abstract 是抽象类
}
```

!!! warning "编译器现状：只可移动的异常类型"
    按当前草案的 [[except.throw#5]]，`throw std::make_unique<int>(1);` 非良构（`std::unique_ptr` 不能从 `const` 左值复制）。这是较新的措辞；本站测试的 Clang 23 仍然接受只可移动的异常类型。可移植的代码不应抛出只可移动的对象。

## 无操作数的 `throw;`：重新抛出（¶3）

¶3 不带操作数的 *throw-expression* **[[g:rethrow|重新抛出]]当前正在处理的异常**（currently handled exception，[[except.handle#10]]）：

- 如果**没有**正在处理的异常，调用 `std::terminate`（[[except.terminate]]）；
- 否则，以**原有的异常对象**重新激活该异常，**不创建新的异常对象**；该异常不再被视为"已捕获"。

"使用原有对象"是 `throw;` 与 `throw e;` 的本质区别：

```cpp run title="rethrow.cpp" ok
#include <cstdio>

struct Base { virtual ~Base() = default; virtual const char* name() const { return "Base"; } };
struct Derived : Base { const char* name() const override { return "Derived"; } };

int main() {
    try {
        try { throw Derived{}; }
        catch (Base& e) { throw e; }   // 新异常对象，类型 Base（静态类型）：切片
    } catch (Base& e) { std::puts(e.name()); }      // "Base"

    try {
        try { throw Derived{}; }
        catch (Base&) { throw; }       // 原对象，动态类型仍是 Derived
    } catch (Base& e) { std::puts(e.name()); }      // "Derived"
}
```

在处理器中想"原样传递"异常，**永远写 `throw;`**。`throw e;` 不仅可能切片，还多了一次复制。

"当前正在处理的异常"不局限于语法上位于 `catch` 块内：在 `catch` 块调用的函数里写 `throw;` 同样有效（这正是"异常分派函数"惯用法的基础）。反之，在没有活动处理器时执行 `throw;`，程序终止：

```cpp run title="rethrow-terminate.cpp" ok
#include <exception>
#include <cstdio>

void handle_current() {      // 只能在 catch 块（直接或间接）中调用
    try { throw; }           // 重新抛出"当前正在处理的异常"
    catch (int i) { std::printf("int %d\n", i); }
    catch (...)   { std::puts("other"); }
}

int main() {
    try { throw 42; } catch (...) { handle_current(); }   // 输出 "int 42"
    // handle_current();     // 若在这里调用：没有正在处理的异常 → std::terminate
}
```

这里的 `std::terminate` 是**明确定义的行为**（不是 UB）：程序以实现定义的方式终止（默认调用 `std::abort`）。

## 常量求值中的异常 {{c++26}}

C++23 及以前，常量求值中**求值**任何 *throw-expression* 都使表达式不是常量表达式——`throw` 只能出现在未被求值的分支里（如前面的 `checked` 例子）。C++26 由 [[P3068]] 放宽：现在只要异常对象（及其所有通过 `std::current_exception`/`std::rethrow_exception` 产生的副本）在同一次常量求值内**被销毁**，即在内部被捕获、处理完毕，就允许构造异常对象（[[expr.const.core]] ¶2.24）。相应地，`throw;` 只要重新抛出的是本次求值内构造的异常，也可以出现（¶2.25）。

```cpp title="throw-constexpr.cpp" ok
struct NotDigit { char c; };

constexpr int parse_digit(char c) {
    if (c < '0' || c > '9') throw NotDigit{c};
    return c - '0';
}

constexpr int safe_parse(char c) {
    try { return parse_digit(c); }
    catch (const NotDigit&) { return -1; }   // C++26：在常量求值中捕获
}

static_assert(safe_parse('7') == 7);
static_assert(safe_parse('x') == -1);   // C++26 起 OK；C++23 非常量
```

!!! warning "编译器现状"
    截至写作时，本站测试的 Clang 23 尚未实现 [[P3068]]，上例第二个 `static_assert` 会被拒绝（"subexpression not valid in a constant expression"）。判定标签按标准给出。

逃逸出常量求值的异常仍然使表达式不是常量——编译期的未捕获异常就是编译错误，这正是它作为"编译期断言"的价值。

## 实现视角

!!! impl
    - **Itanium C++ ABI**（GCC/Clang 在 Linux/macOS）：`throw x` 编译为 `__cxa_allocate_exception(sizeof(T))`（通常从堆上分配，失败时退回到运行库预留的紧急缓冲区）→ 在其中构造异常对象 → `__cxa_throw(obj, &typeid(T), destructor)`，后者启动两阶段的表驱动栈展开（先搜索处理器，再逐帧清理）。`throw;` 编译为 `__cxa_rethrow()`，它找到当前线程"已捕获异常"栈顶的对象重新抛出；栈为空时调用 `std::terminate`。
    - **MSVC**：`throw` 编译为 `_CxxThrowException(obj, &ThrowInfo)`，基于 SEH 实现；异常对象通常在**栈上**（抛出点的栈帧仍未销毁，处理器在其"上方"运行）。
    - "零开销"异常：两种 ABI 在不抛出时都没有运行期开销（不需要在每个 `try` 处登记），代价是抛出时很慢（查表、展开），以及二进制中的展开表。
    - `throw` 作为表达式，类型为 `void`，编译器知道其后的代码不可达，可据此优化（类似 `[[noreturn]]` 函数调用）。

## 陷阱

!!! pitfall "在 catch 中写 `throw e;` 以'重新抛出'"
    这会创建新的异常对象，类型为 `e` 的静态类型——可能切片，并且多一次复制。用 `throw;`。

!!! pitfall "通过基类引用 `throw`"
    异常对象的类型由静态类型决定，`throw base_ref;` 抛出的是切片后的基类对象。

!!! pitfall "在 catch 块之外调用依赖 `throw;` 的辅助函数"
    没有当前处理的异常 → `std::terminate`。

!!! pitfall "抛出指向局部对象的指针"
    异常对象是指针的副本，指向的局部对象在栈展开时就被销毁了。抛出值、按引用捕获。

## 思考题

!!! question "思考题 1"
    `throw x, y;` 抛出的是什么？`throw (x, y);` 呢？

<details markdown="1">
<summary>答案</summary>

*throw-expression* 的操作数是 *assignment-expression*，而逗号运算符的优先级更低，所以 `throw x, y;` 是 `(throw x), y;`：抛出 `x`，`y` 永远不会被求值。`throw (x, y);` 的操作数是括号表达式 `(x, y)`，抛出 `y`（左操作数 `x` 被求值并丢弃）。
</details>

!!! question "思考题 2"
    下面的程序输出什么？

    ```cpp
    try {
        try { throw 1; }
        catch (int& i) { i = 2; throw; }
    } catch (int i) { std::printf("%d\n", i); }
    ```

<details markdown="1">
<summary>答案</summary>

输出 `2`。`catch (int& i)` 绑定到异常对象本身；修改 `i` 就是修改异常对象。`throw;` 重新抛出**同一个**异常对象（¶3："no new exception object is created"），外层按值捕获时复制的是已被修改的对象。若内层写成 `throw i;`，会创建新的异常对象，结果同样是 2，但机制不同。若内层是 `catch (int i)`（按值），修改的只是副本，外层输出 `1`。
</details>

## 小结

| 方面 | 规则 | 依据 |
|---|---|---|
| 类型 | `void` | ¶1 |
| 异常对象类型 | 操作数退化后的**静态类型**，去顶层 cv | ¶2 |
| 初始化 | 从操作数复制初始化（prvalue 直接构造；局部变量先尝试移动） | ¶2、[[class.copy.elision]] |
| 类型要求 | 完整、非抽象、非指向不完整类型的指针；可从 `const T` 左值复制 | [[except.throw]] |
| `throw;` | 重新抛出当前处理的异常（同一对象）；没有则 `std::terminate` | ¶3 |
| 常量求值 | C++26 起允许，只要异常在求值内被捕获销毁 | [[expr.const.core]] |
