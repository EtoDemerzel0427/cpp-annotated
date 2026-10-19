---
title: 抛出异常
summary: throw 是类型为 void 的表达式；异常对象的类型取操作数的静态类型并从操作数复制初始化；throw; 重新抛出原来的异常对象，没有正在处理的异常时调用 std::terminate。
status: done
papers: P3068
related: except.throw, except.handle, except.terminate, class.copy.elision, expr.cond, expr.comma, expr.const.core, propagation
tags: 异常, throw, 常量求值
updated: 2026-10-19
---

!!! tldr
    - `throw` 是表达式，类型是 `void`，所以它能出现在 `?:` 的一个分支里。
    - `throw e` 新建一个异常对象，类型是 `e` 的静态类型去掉顶层 cv，数组和函数先退化成指针。通过基类引用抛出会切片。
    - `throw;` 重新抛出当前正在处理的异常，用的是原来那个对象，不复制、不切片。在处理器里原样转发异常应当写 `throw;`。
    - 没有正在处理的异常时执行 `throw;`，调用 `std::terminate`。
    - C++26 起，常量求值中可以抛出异常，只要它在同一次求值内被捕获。

本节只管 `throw` 作为表达式的性质：类型、异常对象怎样初始化、`throw;` 做什么。异常怎样传播、处理器怎样匹配、栈怎样展开，由第 14 章 [[except.throw]]、[[except.handle]] 负责。

## `throw` 是一个 `void` 表达式（¶1）

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

¶1 *throw-expression* 的类型是 `void`。它永远不会正常结束求值，要么把控制交给处理器，要么调用 `std::terminate`，给它一个值没有意义。[[expr.cond#2]] 专门为它开了口子：条件运算符的一边是 *throw-expression* 时，结果取另一边的类型和值类别。

```text
throw-expression:
    throw assignment-expression(opt)
```

*throw-expression* 属于 *assignment-expression* 这一级（[[expr.assign]]），所以 `throw a, b` 是 `(throw a), b`：抛出 `a`，`b` 永远不会被求值。`throw (a, b)` 才抛出 `b`。

## 异常对象从操作数初始化（¶2）

¶2 带操作数的 *throw-expression* 抛出一个异常。**异常对象**（[[g:exception-object]]）是 `throw` 新建的那个对象，处理器捕获的就是它。它按以下三步确定：

1. 对操作数做数组到指针、函数到指针转换；
2. 异常对象的类型是转换后操作数的类型去掉顶层 cv 限定；
3. 异常对象从转换后的操作数复制初始化（[[dcl.init.general]]）。

```cpp run title="throw-type.cpp" ok
#include <cstdio>

void fn() {}

int main() {
    try { throw "Help!"; }                       // const char[6] → const char*
    catch (const char* p) { std::puts(p); }

    try { const int c = 1; throw c; }            // 去掉顶层 const：异常对象是 int
    catch (int& e) { std::puts("caught int&"); } // 可以用非 const 引用捕获

    try { throw fn; }                            // 函数 → 函数指针
    catch (void (*)()) { std::puts("caught function pointer"); }
}
```

### 类型取静态类型

操作数的类型指表达式的**静态类型**（[[g:static-type]]），也就是编译期看到的类型，而不是运行时对象的实际类型。通过基类引用抛出派生类对象，异常对象是基类类型，派生部分被切掉：

```cpp run title="throw-static-type.cpp" ok
#include <cstdio>

struct Base { virtual ~Base() = default; virtual const char* name() const { return "Base"; } };
struct Derived : Base { const char* name() const override { return "Derived"; } };

int main() {
    try {
        Derived d;
        Base& r = d;
        throw r;                       // 异常对象类型是 Base：切片
    } catch (Base& e) {
        std::puts(e.name());           // 输出 Base
    }
}
```

想通过基类接口抛出完整的派生类对象，常见做法是在基类里声明虚函数 `virtual void raise() const { throw *this; }`，每个派生类重写它，这样 `*this` 的静态类型就是派生类。很多这类需求现在可以用 `std::exception_ptr`（[[propagation]]）解决。

### 复制、移动与消除

复制初始化走一般的初始化规则：

- 操作数是 prvalue（如 `throw MyError(...)`）时，C++17 起直接在异常对象的存储里构造，没有复制或移动。
- 操作数是一个局部变量的名字，且它的作用域不越出最内层的 `try` 块时，它是**隐式可移动实体**（[[g:implicitly-movable-entity]]），先尝试移动。[[class.copy.elision#1.2]] 还允许把这次移动整个省掉。
- 其他情况复制。

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
        throw e;                 // 输出 move（或被消除，什么也不输出）
    } catch (const Err&) {}
}
```

### 对异常类型的要求

[[except.throw]] 对异常对象的类型 `T` 还有两条编译期要求：

- `T` 不能是不完整类型、抽象类，或者指向不完整类型（`cv void` 除外）的指针（[[except.throw#3]]）。
- 从 `const T` 左值复制初始化 `T` 必须良构（[[except.throw#5]]），即使这次 `throw` 用的是移动。异常对象可能被 `std::current_exception` 复制，实现需要一个可用的复制构造函数。

```cpp title="throw-requirements.cpp" error
struct Incomplete;
struct Abstract { virtual void f() = 0; };

void f(Incomplete* p, Abstract& a) {
    throw p;          // error：指向不完整类型的指针
    throw a;          // error：异常对象类型 Abstract 是抽象类
}
```

!!! warning "编译器现状：只可移动的异常类型"
    按当前草案的 [[except.throw#5]]，`throw std::make_unique<int>(1);` 非良构，因为 `std::unique_ptr` 不能从 `const` 左值复制。本机 Clang 23 仍然接受它。可移植的代码不应抛出只可移动的对象。

## `throw;` 重新抛出原来的对象（¶3）

```cpp run title="rethrow.cpp" ok
#include <cstdio>

struct Base { virtual ~Base() = default; virtual const char* name() const { return "Base"; } };
struct Derived : Base { const char* name() const override { return "Derived"; } };

int main() {
    try {
        try { throw Derived{}; }
        catch (Base& e) { throw e; }   // 新异常对象，类型是 Base：切片
    } catch (Base& e) { std::puts(e.name()); }      // Base

    try {
        try { throw Derived{}; }
        catch (Base&) { throw; }       // 原对象，动态类型仍是 Derived
    } catch (Base& e) { std::puts(e.name()); }      // Derived
}
```

¶3 不带操作数的 *throw-expression* [[g:rethrow|重新抛出]]**当前正在处理的异常**（[[g:currently-handled-exception]]），即最近一个已进入、尚未退出的处理器所捕获的那个异常（[[except.handle#10]]）。

- 没有正在处理的异常时，调用 `std::terminate`（[[except.terminate]]）。
- 否则以原有的异常对象重新激活这个异常，不创建新对象；这个异常不再视为已被捕获。

所以在处理器里原样转发异常，应当写 `throw;`。`throw e;` 会按 `e` 的静态类型新建一个异常对象，可能切片，还多一次复制。

正在处理的异常不限于语法上位于 `catch` 块内。在 `catch` 块调用的函数里写 `throw;` 同样有效，常见的异常分派函数就建立在这一点上：

```cpp run title="rethrow-terminate.cpp" ok
#include <exception>
#include <cstdio>

void handle_current() {      // 只能在 catch 块中（直接或间接）调用
    try { throw; }           // 重新抛出当前正在处理的异常
    catch (int i) { std::printf("int %d\n", i); }
    catch (...)   { std::puts("other"); }
}

int main() {
    try { throw 42; } catch (...) { handle_current(); }   // 输出 int 42
    // handle_current();     // 在这里调用：没有正在处理的异常 → std::terminate
}
```

没有正在处理的异常时调用 `std::terminate` 是有定义的行为，不是 UB：程序以实现定义的方式终止，默认调用 `std::abort`。

## 常量求值中的异常 {{c++26}}

C++23 及以前，常量求值中只要求值了任何 *throw-expression*，表达式就不是常量表达式，`throw` 只能放在没被求值的分支里。C++26 的 [[P3068]] 放宽了这条限制：只要异常对象，以及 `std::current_exception` 等产生的所有副本，都在同一次常量求值内销毁，就可以构造它（[[expr.const.core#2.24]]）。`throw;` 重新抛出本次求值内构造的异常也可以（[[expr.const.core#2.25]]）。

```cpp title="throw-constexpr.cpp"
struct NotDigit { char c; };

constexpr int parse_digit(char c) {
    if (c < '0' || c > '9') throw NotDigit{c};
    return c - '0';
}

constexpr int safe_parse(char c) {
    try { return parse_digit(c); }
    catch (const NotDigit&) { return -1; }   // 在常量求值中捕获
}

static_assert(safe_parse('7') == 7);
static_assert(safe_parse('x') == -1);   // C++26 起 OK
```

!!! warning "编译器现状"
    本机 Clang 23 尚未实现 [[P3068]]，会拒绝上例第二个 `static_assert`，所以上例没有标注判定。按标准它是良构的。

逃出常量求值的异常仍然使表达式不是常量。编译期没被捕获的异常就是编译错误，`throw` 因此可以充当编译期断言。

## 实现视角

!!! impl
    - Itanium C++ ABI（GCC、Clang 在 Linux、macOS 上使用）：`throw x` 先调用 `__cxa_allocate_exception` 分配存储（通常在堆上，失败时用运行库预留的紧急缓冲区），在其中构造异常对象，再调用 `__cxa_throw` 启动表驱动的两阶段栈展开：先找处理器，再逐帧清理。`throw;` 编译为 `__cxa_rethrow()`，没有已捕获的异常时调用 `std::terminate`。
    - MSVC 把 `throw` 编译为 `_CxxThrowException`，基于 SEH 实现。
    - 两种 ABI 在不抛出异常时都没有运行期开销，代价是抛出时要查表和展开，比较慢，二进制里也多了展开表。
    - `throw` 之后的代码不可达，编译器可以据此优化，与调用 `[[noreturn]]` 函数类似。

## 常见误解

!!! pitfall "在 catch 中用 `throw e;` 转发"
    这会新建一个异常对象，类型是 `e` 的静态类型，可能切片，并多一次复制。应当写 `throw;`。

!!! pitfall "抛出指向局部对象的指针"
    异常对象只是指针的副本，它指向的局部对象在栈展开时已经销毁。应当按值抛出、按引用捕获。

## 思考题

!!! question "思考题"
    下面的程序输出什么？

    ```cpp
    try {
        try { throw 1; }
        catch (int& i) { i = 2; throw; }
    } catch (int i) { std::printf("%d\n", i); }
    ```

<details markdown="1">
<summary>答案</summary>

输出 `2`。`catch (int& i)` 绑定到异常对象本身，修改 `i` 就是修改异常对象。`throw;` 重新抛出同一个对象（¶3），外层按值捕获时复制的是修改后的值。

内层改写成 `throw i;` 也输出 2，但机制不同：它从 `i` 复制出一个新的异常对象。内层改成按值捕获 `catch (int i)` 时，修改的只是副本，外层输出 `1`。
</details>

## 小结

| 方面 | 规则 | 依据 |
|---|---|---|
| 类型 | `void` | ¶1 |
| 异常对象类型 | 操作数退化后的静态类型，去掉顶层 cv | ¶2 |
| 初始化 | 从操作数复制初始化；prvalue 直接构造，局部变量先尝试移动 | ¶2、[[class.copy.elision]] |
| 类型要求 | 完整、非抽象、不指向不完整类型；能从 `const T` 左值复制 | [[except.throw]] |
| `throw;` | 重新抛出当前处理的异常（同一个对象）；没有则 `std::terminate` | ¶3 |
| 常量求值 | C++26 起允许，只要异常在本次求值内被捕获销毁 | [[expr.const.core]] |
