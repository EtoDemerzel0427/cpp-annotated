---
title: 处理异常
summary: 抛出的异常由哪个 catch 子句接住：只有四种匹配方式，按出现顺序取第一个；找不到 handler 或穿过 noexcept 函数时调用 std::terminate；当前处理的异常是什么；handler 参数怎样初始化；构造函数和析构函数的 function-try-block 有哪些特殊规则。
status: done
related: except.throw, except.pre, except.ctor, except.spec, except.terminate, expr.throw, conv.ptr, conv.mem, conv.qual, conv.fctptr, class.copy.elision, propagation
tags: 异常, handler, catch, 匹配
updated: 2026-10-19
---

!!! tldr
    - catch 子句的匹配不是重载决议：只接受同一类型、无歧义的 public 基类、少数几种指针转换和 `nullptr_t`，没有整数提升、算术转换或用户定义转换。
    - 一个 try 块的 handler 按书写顺序尝试，第一个匹配的胜出；`catch (...)` 必须放在最后。
    - 异常离开 `noexcept` 函数，或者一直找不到 handler，都会调用 `std::terminate`；找不到 handler 时栈是否回溯由实现定义，主流实现不回溯。
    - 按值捕获是从异常对象拷贝，会切片；按引用捕获可以修改异常对象，修改对 `throw;` 可见。
    - 构造函数和析构函数的 function-try-block 里不能访问成员，流出 handler 末尾会自动重抛。

一个 **handler** 就是一个 catch 子句：`catch (` *exception-declaration* `)` 后接复合语句。*exception-declaration* 是括号里的声明，比如 `const std::exception& e`，也可以是 `...`。`throw` 创建的那个对象叫**异常对象**（[[g:exception-object]]，见 [[except.throw]]），本页要回答的是：异常对象沿着调用链向外传播时，哪个 handler 会接住它。

## 匹配规则（¶3）

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

这是标准例 1 的改写，也是最常见的用法：异常类组成一个继承层次，handler 按基类捕获一整类异常。标准原例写的是按值捕获 `catch (Matherr mm)`，会把派生类对象切片成 `Matherr`，实践中应当按 `const&` 捕获。

¶3 设异常对象的类型是 `E`，handler 与它匹配当且仅当下面四种情形之一成立：

| 项 | handler 的类型 | 条件 |
|---|---|---|
| ¶3.1 | cv `T` 或 cv `T&` | `E` 与 `T` 是同一类型（忽略顶层 cv） |
| ¶3.2 | cv `T` 或 cv `T&` | `T` 是 `E` 的无歧义 public 基类 |
| ¶3.3 | cv `T` 或 `const T&`，`T` 是指针或成员指针 | `E` 也是指针或成员指针，能经下列转换的组合变成 `T`：不涉及 private、protected 或歧义基类的标准指针转换（¶3.3.1）；去掉 `noexcept` 的函数指针转换（¶3.3.2）；增加 cv 的限定转换（¶3.3.3） |
| ¶3.4 | cv `T` 或 `const T&`，`T` 是指针或成员指针 | `E` 是 `std::nullptr_t` |

表里没有的转换都不参与匹配，包括整数提升、算术转换、`bool` 转换、用户定义转换，以及派生类到 private 基类的转换。

### 实测

下面用一个函数模板逐项测试，`test<E, H>` 抛出类型为 `E` 的对象，看 `catch (H)` 能否接住：

```cpp run title="match-matrix.cpp" ok
#include <cstdio>
#include <cstddef>

struct B { virtual ~B() = default; };
struct D : B {};
struct P : private B {};
struct B1 : B {}; struct B2 : B {};
struct Amb : B1, B2 {};    // 含两个 B 子对象：B 是歧义基类

template<class E, class H>
const char* test(E e) {
    try { throw e; }
    catch (H) { return "match"; }
    catch (...) { return "no match"; }
}

void fn() noexcept {}
using fp = void (*)();
using nfp = void (*)() noexcept;

int main() {
    std::puts(test<int, long>(1));                 // no match：没有算术转换
    std::puts(test<char, int>('a'));               // no match：没有整数提升
    std::puts(test<int, const int&>(1));           // match：3.1
    std::puts(test<D, B&>(D{}));                   // match：3.2
    std::puts(test<P, B&>(P{}));                   // no match：private 基类
    std::puts(test<Amb, B&>(Amb{}));               // no match：歧义基类
    std::puts(test<D*, const B*>(nullptr));        // match：3.3.1 + 3.3.3
    std::puts(test<D*, void*>(nullptr));           // match：3.3.1
    std::puts(test<int**, const int* const*>(nullptr)); // match：3.3.3
    std::puts(test<nfp, fp>(fn));                  // match：3.3.2
    std::puts(test<fp, nfp>(nullptr));             // no match：不能加 noexcept
    std::puts(test<std::nullptr_t, int*>(nullptr)); // match：3.4
    std::puts(test<int, int*>(0));                 // no match：注 1
}
```

本机 Clang 23（libc++abi）的输出与注释一致。下面解释其中几行。

`throw 1;` 不会被 `catch (long)` 接住，`throw 'a';` 也不会被 `catch (int)` 接住。匹配发生在运行时，运行时库手里只有异常对象的类型信息（`std::type_info` 和 ABI 附带的类层次描述），做不了重载决议。如果允许算术转换，运行时库就要为每一对算术类型实现转换，还要决定多个 handler 都能转换时选哪个。C++ 选择了更简单的模型：按顺序找第一个在类型上匹配的 handler（¶4）。

注 1 指出，`throw 0;` 不匹配指针 handler。字面量 `0` 在编译期是空指针常量，但抛出之后异常对象只是一个 `int`。要被指针 handler 接住，应当抛出 `nullptr`（¶3.4）。`throw NULL;` 的结果取决于 `NULL` 定义成 `0`、`0L` 还是 `nullptr`，不可移植。

基类必须无歧义而且是 public 的，这与抛出点的访问权限无关。即使在 `P` 的成员函数里抛出 `P`，那里 `P` 到 `B` 的转换是可访问的，`catch (B&)` 也接不住它。匹配只看类型本身的继承关系。

### 指针 handler 只能是 `T` 或 `const T&`

¶3.1 和 ¶3.2 允许任何引用，¶3.3 和 ¶3.4 却只允许按值或 `const T&`。原因是指针转换会产生一个新的指针值，例如 `D*` 转成 `B*` 时可能要调整地址。新值只能复制一份，或者绑定到 const 引用上。如果允许 `catch (B*& r)` 绑定到一个 `D*` 异常对象，`r = new B;` 就会把 `B*` 写进一个类型为 `D*` 的对象。

!!! impl "libc++abi 与 `B*&`"
    按标准，`throw (D*)p;` 不应匹配 `catch (B*& r)`：`B*&` 不是 `const T&`，`D*` 与 `B*` 也不是同一类型。本机 libc++abi 却会匹配（在上面的测试里加一行 `test<D*, B*&>` 即可看到）。Itanium ABI 在异常表里记录的是 handler 去掉引用后的类型，运行时似乎无法区分 `catch (B*)` 和 `catch (B*&)`。这是实现的不符合之处，可移植代码不要依赖它。

!!! lawyer "成员指针只有部分转换可用"
    ¶3.3 允许 `T` 是成员指针，但 ¶3.3.1 说的是标准指针转换（[[conv.ptr]]）。成员指针从 `int B::*` 到 `int D::*` 的转换属于另一条，[[conv.mem]]。按字面读法，这种转换不参与匹配，所以 `throw (int B::*)nullptr;` 不会被 `catch (int D::*)` 接住。本机实测确实不匹配。成员指针 handler 因此只能通过同类型、限定转换、成员函数指针的函数指针转换和 `nullptr_t` 匹配。

## 按书写顺序尝试（¶4–¶5）

¶4 一个 try 块的 handler 按出现顺序尝试，第一个匹配的胜出，而不是最佳匹配胜出。注 2 指出，这样就可能写出永远执行不到的 handler，比如把派生类的 handler 放在基类的 handler 之后。

¶5 `catch (...)` 匹配任何异常。如果有它，它必须是这个 try 块的最后一个 handler。

<div class="compare" markdown="1">

```cpp ok
struct B {};
struct D : B {};
void f() {
  try {
  } catch (B&) {
  } catch (D&) {  // 永远到不了
  }
}
```

```cpp error
void g() {
  try {
  } catch (...) {
  } catch (int) {  // error
  }
}
```

</div>

左边是良构的，Clang 23 只给出警告 `exception of type 'D &' will be caught by earlier handler`。右边违反 ¶5，Clang 报 `catch-all handler must come last`。

`catch (...)` 里拿不到异常对象的名字，但可以用 `throw;` 重抛，或者用 `std::current_exception()` 取得一个 `exception_ptr`（[[propagation]]）。

!!! warning "MSVC 的 `/EHa`"
    MSVC 用 `/EHa` 编译时，`catch (...)` 还会捕获结构化异常（SEH），比如访问违例；默认的 `/EHsc` 不会。这是 MSVC 的扩展，与标准无关。

## handler 能声明的类型（¶1–¶2）

¶1 *exception-declaration* 不能是不完整类型、抽象类类型或右值引用类型，也不能是指向不完整类型的指针或引用。指向 cv `void` 的指针例外。

```cpp title="bad-handlers.cpp" error
struct Abs { virtual void f() = 0; };
struct Inc;

void f() {
    try {} catch (int&&) {}     // error: 右值引用
    try {} catch (Abs) {}       // error: 抽象类，按值
    try {} catch (Inc&) {}      // error: 不完整类型的引用
    try {} catch (Inc*) {}      // error: 指向不完整类型的指针
    try {} catch (Abs&) {}      // OK：抽象类的引用
    try {} catch (void*) {}     // OK：void* 例外
}
```

不完整类型被排除，是因为运行时需要完整的类型信息才能判断继承关系。右值引用被排除，是因为异常对象总是左值：`throw;` 之后别的 handler 还要用它，不应该从中移走资源。需要修改异常对象时用 `T&`。

¶2 类型为数组或函数的 handler 调整为对应的指针类型，与函数形参的调整（[[dcl.fct]]）相同。抛出数组或函数时，异常对象本来就是退化后的指针（[[expr.throw]]），两边正好对得上：

```cpp run title="array-handler.cpp" ok
#include <cstdio>

void callback() {}

int main() {
    int a[3] = {1, 2, 3};
    try { throw a; }                       // 异常对象类型为 int*
    catch (int x[3]) { std::printf("%d\n", x[1]); }   // 调整为 int*

    try { throw callback; }                // 异常对象类型为 void(*)()
    catch (void f()) { std::puts("function -> pointer"); }
}
```

反过来，数组引用或函数引用类型的 handler 永远不会匹配任何异常对象（注 1），因为异常对象不可能是数组或函数。

## 没有 handler 匹配时（¶6–¶8）

¶6 一个 try 块的 handler 都不匹配时，搜索在同一线程中动态外层的 try 块里继续。动态外层指调用链上更早进入、尚未退出的 try 块。

¶7 如果搜索离开了一个具有非抛出异常说明（[[except.spec]]，例如 `noexcept`）的函数的函数体，调用 `std::terminate`。注 3 和例 2 强调，实现不能仅仅因为某个表达式可能从 `noexcept` 函数中抛出就拒绝它：

```cpp run title="noexcept-boundary.cpp" ok
#include <cstdio>
#include <cstdlib>
#include <exception>

extern void f();             // 潜在抛出

void g() noexcept {
    f();                     // 良构，即使 f 会抛出
    throw 42;                // 良构，效果相当于调用 std::terminate
}

void f() {}

int main() {
    std::set_terminate([] { std::fputs("terminate\n", stderr); std::abort(); });
    g();
}
```

Clang 23 对 `throw 42;` 给出警告 `'g' has a non-throwing exception specification but can still throw`，但不报错。程序运行后打印 `terminate`。

C++ 没有把这做成编译期检查，因为编译器无法知道一个没写 `noexcept` 的函数是否真的会抛出。C 函数、旧代码、虚函数调用大多没有准确的异常说明，如果要求 `noexcept` 函数只能调用 `noexcept` 函数，代码就几乎写不下去了。`noexcept` 是一个运行时承诺：违反它的后果是确定的终止，编译器可以据此优化调用方。

这条规则说的是搜索离开函数体。异常在 `noexcept` 函数内部被捕获就没有问题：

```cpp title="noexcept-internal-catch.cpp" ok
void may_throw();

void safe() noexcept {
    try { may_throw(); }
    catch (...) {}           // 异常没有离开函数体
}
```

¶8 一直找不到匹配的 handler 时，调用 `std::terminate`。在此之前栈是否回溯（[[g:stack-unwinding]]，即沿调用链析构各层的自动对象）由实现定义，见 [[except.terminate]]。

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

本机（Clang 23，libc++abi，`-O0` 和 `-O2`）只输出 `terminate`，两个局部对象都没有析构。Itanium ABI 先做一遍只读的搜索，搜索失败就直接终止，这样 core dump 里保留着抛出点的完整调用栈。依赖未捕获异常来触发析构的代码不可移植；需要清理时，在 `main` 和每个线程的入口函数里放一个 `catch (...)`。

## 当前处理的异常（¶9–¶10）

¶9 catch 子句的参数初始化完成时，这个 handler 成为**活动的**（[[g:active-handler]]）。注 4 指出，此时栈已经回溯完毕。catch 子句退出时，handler 不再活动。因抛出而进入 `std::terminate` 时，也有一个隐式的 handler 被视为活动的。

¶10 最近激活、仍然活动的 handler 所处理的异常，叫做**当前处理的异常**（[[g:currently-handled-exception]]）。`throw;` 重抛的、`std::current_exception()` 返回的都是它。

handler 里还可以有 try/catch，所以同一时刻可能有多个活动的 handler。当前处理的异常相当于一个栈的栈顶：

```cpp run title="currently-handled.cpp" ok
#include <cstdio>

void show() {
    try { throw; }                         // 重抛当前处理的异常
    catch (int i)    { std::printf("int %d\n", i); }
    catch (double d) { std::printf("double %g\n", d); }
}

int main() {
    try { throw 1; }
    catch (int) {
        show();                            // int 1
        try { throw 2.5; }
        catch (double) { show(); }         // double 2.5：内层 handler 最近激活
        show();                            // int 1：内层 handler 已经退出
    }
}
```

隐式 handler 让 terminate 处理函数也能取得导致终止的异常。libstdc++ 默认的处理函数能打印未捕获异常的类型，用的就是这一点：

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
    throw std::runtime_error("disk on fire");   // 打印 uncaught: disk on fire
}
```

## handler 参数的初始化（¶15–¶16）

¶15 设 handler 声明的变量类型为 cv `T` 或 cv `T&`，异常对象类型为 `E`：

- ¶15.1 如果 `T` 是 `E` 的基类，变量从一个指代异常对象中对应基类子对象的 `T` 类型左值复制初始化；
- ¶15.2 否则，变量从一个指代异常对象的 `E` 类型左值复制初始化。

这个变量的生命期在 handler 退出时结束，晚于 handler 内部所有自动对象的销毁。

由此可以得到几点推论：

- 按值捕获就是一次拷贝。源是左值，不会调用移动构造函数，所以按值捕获一个只能移动的类型是非良构的。
- 按值捕获基类会切片（¶15.1）。
- 这次拷贝可以省略：[[class.copy.elision#1]] 允许把 handler 的变量当作异常对象的别名。本机 Clang 不做这种省略。
- 拷贝期间异常还没有被捕获，拷贝构造函数如果抛出，就调用 `std::terminate`（[[except.throw]]）。

¶16 注 5 说明了按值与按引用的区别：handler 声明的是对象时，修改它不影响异常对象；声明的是引用时，修改的就是异常对象本身，之后 `throw;` 重抛的也是修改后的对象。

```cpp run title="modify-exception.cpp" ok
#include <cstdio>

struct E { int v; };

int main() {
    try {
        try { throw E{1}; }
        catch (E& e) { e.v = 2; throw; }        // 修改异常对象
    } catch (E e) { std::printf("%d\n", e.v); }  // 2

    try {
        try { throw E{1}; }
        catch (E e) { e.v = 2; throw; }         // 修改副本
    } catch (E e) { std::printf("%d\n", e.v); }  // 1
}
```

## function-try-block（¶11–¶14）

**function-try-block** 是把整个函数体包在 try 里的写法：`void f() try { ... } catch (...) { ... }`。用在构造函数上时，它还能捕获成员初始化列表中抛出的异常，见 [[except.pre]]。

¶11 在构造函数或析构函数的 function-try-block 的 handler 里，访问该对象的任何非静态成员或基类，行为未定义。进入 handler 之前，已经构造的子对象都已析构（[[except.ctor]]），没有东西可以访问了。

```cpp title="ctor-handler-member.cpp" ub
#include <cstdio>
#include <string>

struct Thrower { Thrower() { throw 0; } };

struct S {
    std::string name;
    Thrower t;
    S() try : name("widget"), t() {
    } catch (...) {
        std::puts(name.c_str());   // UB: name 已经析构
    }
};
```

Clang 23 对此给出警告 `cannot refer to a non-static member from the handler of a constructor function try block`，但仍然接受。标准不要求诊断 UB。

¶13 构造函数的 function-try-block 的 handler 里出现 `return` 语句，程序非良构。Clang 报 `return in the catch of a function try block of a constructor is illegal`。

¶14 控制到达构造函数或析构函数的 function-try-block 的 handler 末尾时，当前处理的异常被重抛。构造失败的对象不存在，构造函数不可能当作成功返回，所以 handler 只能把异常换成另一个，或者让原来的继续传播。

```cpp run title="ctor-rethrow.cpp" ok
#include <cstdio>

struct U {
    U() try { throw 7; }
    catch (int) { std::puts("U handler"); }   // 末尾自动重抛
};

int main() {
    try { U u; }
    catch (int i) { std::printf("rethrown %d\n", i); }
}
```

对其他函数，流出 function-try-block 的 handler 末尾，等价于流出函数体末尾（[[stmt.return]]）。返回类型不是 `void` 的函数这样做是 UB，`main` 除外：

```cpp title="ftb-flow-off.cpp" ub
int parse(const char* s) try {
    return s[0] - '0';
} catch (...) {
    // 流出末尾：返回 int 的函数这样做是 UB
}
```

¶12 静态存储期对象的构造函数（对应非块变量）或析构函数抛出的异常，不会被 `main` 的 function-try-block 捕获。线程存储期的对应情形，也不会被线程初始函数的 function-try-block 捕获。这些构造发生在 `main` 开始之前，析构发生在 `main` 返回之后，那时 `main` 的 try 块并不处于已进入的状态。异常直接导致 `std::terminate`（[[except.terminate]]）：

```cpp run title="static-init-throw.cpp" ok
#include <cstdio>

struct S { S() { throw 1; } };
S s;                          // 在 main 之前构造，抛出后调用 std::terminate

int main() try {
    return 0;
} catch (...) {
    std::puts("never");       // main 的 handler 捕获不到
    return 1;
}
```

本机运行输出 `libc++abi: terminating due to uncaught exception of type int`，以 SIGABRT 结束。

## 常见误解

!!! pitfall "按值捕获多态异常"
    `catch (std::exception e)` 会切片，`e.what()` 调用的是 `std::exception::what()`，还多了一次拷贝。应当写 `catch (const std::exception& e)`。

!!! pitfall "handler 匹配像重载决议"
    `throw std::string("x");` 不会被 `catch (const char*)` 接住，`throw 1.0f;` 不会被 `catch (double)` 接住。可用的转换只有派生类到 public 基类，以及少数指针转换。

!!! pitfall "未捕获的异常也会触发析构"
    找不到 handler 时栈是否回溯由实现定义，主流实现不回溯。刷新日志、删除临时文件这类清理，要靠入口函数里的 `catch (...)`。

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

#1。handler 按出现顺序尝试（¶4），`const B&` 已经匹配（¶3.2，`B` 是 `D` 的无歧义 public 基类），所以 #2 永远执行不到。如果这是重载决议，`D&` 会是更好的匹配。
</details>

!!! question "思考题 2"
    `throw (char*)buf;` 能否被 `catch (const char* const& p)` 捕获？能否被 `catch (const char*& p)` 捕获？

<details markdown="1">
<summary>答案</summary>

`const char* const&` 可以。`T = const char*` 是指针类型，handler 的形式是 `const T&`，`char*` 经限定转换得到 `const char*`（¶3.3.3）。

`const char*&` 按标准不可以。它是非 const 引用，不满足 ¶3.3 要求的 cv `T` 或 `const T&`；按 ¶3.1，`char*` 与 `const char*` 又不是同一类型。如果允许绑定，`p = "literal";` 就会把 `const char*` 写进类型为 `char*` 的异常对象，之后 `catch (char* q)` 就能通过 `q` 修改字符串字面量。[[conv.qual]] 禁止 `char**` 隐式转换到 `const char**`，理由相同。（与 `B*&` 一样，某些运行时库实际上可能匹配，见上文的实现说明。）
</details>

!!! question "思考题 3"
    `main` 只调用 `f()`。比较 `void f() noexcept { throw 1; }` 与 `void f() { throw 1; }` 在标准层面的区别。

<details markdown="1">
<summary>答案</summary>

两者都调用 `std::terminate`，但依据不同，对栈回溯的规定也不同。

`noexcept` 版本依据 ¶7：搜索离开了非抛出函数的函数体。是否回溯由实现定义，而且可以只回溯一部分（[[except.terminate#2]]）。没有 `noexcept` 的版本依据 ¶8：找不到 handler，同样由实现定义，但只能完全回溯或完全不回溯。

在 Itanium 实现中，`noexcept` 函数带有一个捕获一切并调用 terminate 的着陆点，搜索阶段把它当作 handler，于是回溯进行到 `f` 的帧为止，`f` 自己的局部对象不析构。后者在搜索阶段找不到任何 handler，直接终止，完全不回溯。
</details>
