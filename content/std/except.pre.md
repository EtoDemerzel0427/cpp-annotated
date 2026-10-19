---
title: 异常处理·序言
summary: try 块、handler 和 function-try-block 的语法；不能跳进 try 块或 handler，但可以跳出，跳出时局部变量在声明所在的上下文中析构；function-try-block 能捕获构造函数初始化成员时抛出的异常。
status: done
related: except, except.throw, except.handle, except.ctor, stmt.label, stmt.jump, class.base.init, stmt.pre
tags: 异常, try, function-try-block
updated: 2026-10-19
---

!!! tldr
    - 只有在 try 块里执行的代码（包括从那里调用的函数）抛出异常时，这个 try 块的 handler 才会被调用。handler 不能直接调用，也不能跳进去。
    - try 块和 handler 的花括号部分是控制流受限语句：不能用 `goto` 或 `case` 从外面跳进去，但可以用 `goto`、`break`、`return`、`continue` 跳出来。
    - 跳出时，局部变量在声明它的那一层析构；析构函数抛出的异常由包住这个声明的 handler 处理。
    - function-try-block 把整个函数体连同成员初始化列表包进 try 块，用来捕获构造函数初始化成员时抛出的异常。
    - 构造函数和析构函数的 function-try-block 的 handler 执行到末尾时自动重抛，异常吞不掉。

## 语法（¶1）

```cpp run title="handler-syntax.cpp" ok
#include <cstdio>
#include <stdexcept>

int main() {
    try {
        throw std::runtime_error("boom");
    } catch ([[maybe_unused]] const std::logic_error& e) {   // 带名字的形参，属性属于 e
        std::puts("logic_error");
    } catch (const std::exception&) {                         // 无名形参
        std::puts("exception");
    } catch (...) {                                           // 匹配任何异常
        std::puts("other");
    }
}
```

¶1 `try` 后面跟一个复合语句，再跟一个或多个 **handler**（`catch` 子句）。每个 handler 的括号里是一个 *exception-declaration*，形状和函数形参声明一样：可以带名字，可以不带，也可以写 `...`。`try` 和 `catch` 后面都必须是花括号，`try f();` 不合法。

¶1 第一句说明了异常处理是什么：把控制和信息从线程执行中的某一点，转移到执行过程中此前经过的某一点所关联的 handler。由此可以得出两点：

- handler 只能属于已经进入、尚未退出的 try 块，异常不会跳到还没执行到的代码里。
- 查找只在同一个线程里进行（[[except.handle#6]]）。异常不会自己跨线程传播，要借助 `std::exception_ptr`（[[propagation]]）或 `std::future`。

¶2 *try-block* 是一种语句（[[stmt.pre]]），可以出现在任何能写语句的地方。function-try-block 不是语句，而是函数体的一种写法（见下文）。本章说 try 块时，两者都包括。

## 不能跳进 try 块或 handler（¶3）

<div class="compare" markdown="1">

```cpp title="goto-into-try.cpp" error
void f(int c) {
  goto l1;      // error: 跳进 try 块
  try {
    l1: ;
  } catch (...) {
    goto l1;    // error: 从 handler 跳回
  }
  switch (c) {
    try {
      case 1: ; // error: case 在 try 块里，
    } catch (...) { }  //  switch 在外面
  }
}
```

```cpp title="goto-inside-try.cpp" ok
void f() {
  try {
    goto l1;    // OK: 标号和 goto
    l1: ;       //     在同一个 try 块里
  } catch (...) {
    goto l2;    // OK: 在同一个 handler 里
    l2: ;
  }
}
```

</div>

¶3 try 块的复合语句和 handler 的复合语句都是**控制流受限语句**（control-flow-limited statement，[[stmt.label#3]]）。这意味着其中的标号只能由内部的 `goto` 使用，其中的 `case`、`default` 只能属于内部的 `switch`。所以左边三处跳转都是非良构的。

禁止跳入的理由在于，进入 try 块是有运行时含义的：查找 handler 依据的是哪些 try 块已进入、尚未退出（[[except.throw#2]]）。跳过 `try` 关键字直接落到块中间，这个状态就说不清了。跳进 handler 更没有意义，那里没有正在处理的异常，handler 的形参和 `throw;` 都无从谈起。

Clang 对这类错误的附注是 jump bypasses initialization of try block，沿用了检查跳过带初始化声明的那套机制（[[stmt.dcl]]）；标准的依据是控制流受限语句。

## 跳出 try 块（¶3）

¶3 后半段允许反方向的跳转：`goto`、`break`、`return`、`continue` 都可以把控制转出 try 块或 handler。这时 try 块里声明的每个变量，都在直接包含它的声明的那个上下文中析构。

这句话决定了析构函数抛出的异常归谁处理：是包住这个变量声明的 try 块，而不是 `goto` 目标处的 try 块。

```cpp run title="goto-out.cpp" ok
#include <cstdio>

struct T {
    const char* n;
    bool throws;
    ~T() noexcept(false) {
        std::printf("~%s\n", n);
        if (throws) { throws = false; throw n; }
    }
};

int main() {
    int round = 0;
lab:
    try {
        T t1{"t1", false};
        try {
            T t2{"t2", round == 0};    // 第一轮：t2 析构时抛出
            if (round++ == 0)
                goto lab;              // 先销毁 t2，再销毁 t1
        } catch (const char* who) {
            std::printf("handler 2 caught %s\n", who);
        }
    } catch (const char* who) {
        std::printf("handler 1 caught %s\n", who);
    }
}
```

输出：

```text
~t2
handler 2 caught t2
~t1
```

`goto lab` 先触发 `t2` 的析构。`t2` 声明在内层 try 块里，所以它的析构函数抛出的异常由 handler 2 接住。异常打断了 `goto`，控制从 handler 2 之后继续：内层 try 块结束，外层复合语句结束，`t1` 正常析构，程序没有回到 `lab`。

## function-try-block（¶4）

构造函数的成员初始化发生在函数体的 `{` 之前，函数体里的普通 try 块包不住它。function-try-block 把 `try` 放到初始化列表前面，解决的就是这个问题：

```cpp run title="ctor-ftb.cpp" ok
#include <cstdio>

struct Member {
    explicit Member(int x) { if (x < 0) throw x; }
};

struct C {
    Member m;
    explicit C(int x)
    try : m(x) {                          // 初始化列表也在 try 的范围内
        std::puts("ctor body");
    } catch (int e) {
        std::printf("ctor handler saw %d\n", e);
    }                                     // 执行到末尾：自动重抛
};

int main() {
    try {
        C c(-1);
    } catch (int e) {
        std::printf("main caught %d again\n", e);
    }
}
```

输出：

```text
ctor handler saw -1
main caught -1 again
```

¶4 function-try-block 的 handler 能捕获三类异常：函数体执行中抛出的；对构造函数，初始化基类和成员时抛出的；对析构函数，析构基类和成员时抛出的。

构造函数失败时，对象没有构造出来，调用方必须知道这件事。所以 [[except.handle]] 对构造函数和析构函数的 function-try-block 加了三条限制：

| 规则 | 出处 |
|---|---|
| handler 执行到末尾时，自动重抛当前处理的异常 | [[except.handle#14]] |
| 构造函数的 handler 里出现 `return` 语句，程序非良构 | [[except.handle#13]] |
| 在 handler 里访问这个对象的非静态成员或基类是未定义行为，它们已经析构了 | [[except.handle#11]] |

```cpp title="ctor-handler-return.cpp" error
struct M { M(int); };
struct C {
    M m;
    C(int x) try : m(x) { } catch (...) {
        return;     // error: 构造函数 function-try-block 的 handler 里不能有 return
    }
};
```

handler 能做的事因此只剩几件：记日志，把异常翻译成另一种异常抛出，清理不属于成员的资源（例如通过形参传进来的东西）。用 `throw OtherError{};` 结束 handler，或者调用 `std::exit`，都是允许的，它们不会执行到 handler 末尾。

析构函数的 handler 执行到末尾同样会重抛，但析构函数的 handler 里可以写 `return;`，这样异常就被吞掉了。不过析构函数默认是 `noexcept` 的（[[except.spec#8]]），这种写法很少见：

```cpp run title="dtor-ftb.cpp" ok
#include <cstdio>

struct Bad { ~Bad() noexcept(false) { throw 1; } };

struct H {
    Bad b;
    ~H() noexcept(false)
    try {
    } catch (int) {
        std::puts("dtor handler");   // 成员 b 析构时抛出，在这里捕获
    }                                // 执行到末尾：自动重抛
};

int main() {
    try { H h; } catch (int) { std::puts("rethrown to main"); }
}
```

对普通函数，function-try-block 和用一个 try 块包住整个函数体差不多：handler 执行到末尾，相当于函数体执行到末尾（[[except.handle#14]]）。区别是 handler 里还能访问函数形参。`main` 的 function-try-block 捕获不到静态存储期对象构造和析构时抛出的异常（[[except.handle#12]]）。

## 常见误解

!!! pitfall "以为 function-try-block 能挽救构造"
    进入 handler 时，所有已经构造的子对象都已析构（[[except.ctor#3]]），handler 末尾又会自动重抛，所以在 handler 里修好成员、让对象继续构造是做不到的。需要在失败时回退到默认值，应当在成员的初始化表达式里处理，例如调用一个内部捕获异常的工厂函数。

!!! pitfall "在构造函数的 handler 里读成员"
    ```cpp
    struct S {
        std::string name;
        Res r;
        S() try : name("x"), r(open()) {} catch (...) {
            log(name);    // UB: name 已经析构
        }
    };
    ```
    Clang 对此只给出 `-Wexceptions` 警告。handler 里需要的信息，应当来自构造函数的形参或静态数据。

## 思考题

!!! question "思考题"
    下面的代码是否良构？把 `switch` 整个放进 try 块里呢？

    ```cpp
    void f(int c) {
        switch (c) {
            case 0:
                try { case 1: break; } catch (...) { }
        }
    }
    ```

<details markdown="1">
<summary>答案</summary>

非良构。`case 1:` 位于 try 块的复合语句里，这是控制流受限语句，其中的 `case` 必须属于内部的 `switch`（[[stmt.label#3]]），而这里的 `switch` 在 try 块外面。`case 0:` 在 try 块之外，没有问题。

改成 `try { switch (c) { case 1: break; } } catch (...) {}` 后，`switch` 和 `case` 都在 try 块里，程序是良构的。
</details>

<details class="fine" markdown="1"><summary>其余条文</summary>

¶1 *exception-declaration* 里可选的属性说明符序列属于 catch 子句的形参，例如 `catch ([[maybe_unused]] const E& e)`。

¶2 注 1：本章所说的 try 块同时指 *try-block* 和 *function-try-block*。

¶3 早先的标准把这条规则写成不能用 `goto` 或 `switch` 把控制转入 try 块或 handler。现在借用 [[stmt.label]] 统一定义的控制流受限语句来表述，效果相同；同一概念也用于 `if constexpr`、`if consteval` 的分支。

¶5 本章中的 before 和 after 指 sequenced before 关系（[[intro.execution]]），即单线程内的先后顺序。异常处理本身不隐含线程同步（[[except.throw#4]] 注 2）。

</details>
