---
title: 异常处理·序言
summary: try 块与 function-try-block 的语法和语义；handler 只能被其 try 块内（含被调用函数）抛出的异常激活；try 块与 handler 的复合语句是控制流受限语句，不能从外面跳进去；跳出时按声明的上下文析构
status: done
related: except, except.throw, except.handle, except.ctor, stmt.label, stmt.jump, class.base.init, stmt.pre
tags: 异常, try, function-try-block
updated: 2026-10-17
---

本节是第 14 章的文法与总纲：它给出 `try`/`catch` 的文法，规定 handler 在什么情况下可能被激活，限制跳转进入 try 块，并说明 function-try-block 能捕获什么。真正的匹配规则、异常对象和栈回溯分别在 [[except.handle]]、[[except.throw]]、[[except.ctor]]。

## 异常处理的定义与文法（¶1）

¶1 第一句是整个异常机制的定义：异常处理提供一种手段，把控制和信息从线程执行中的某一点，转移到与执行之前经过的某一点相关联的 handler。这里有两个关键点：

- 之前经过（previously passed）：handler 只能属于已经进入、尚未退出的 try 块。异常不会向前跳到还没执行到的代码里。
- 同一线程：[[except.handle#6]] 明确说 handler 搜索只在同一线程的动态外层 try 块中进行。异常不会自己跨线程传播，要跨线程须借助 `std::exception_ptr`（[[propagation]]）或 `std::future`。

第二句规定，只有在它的 try 块内执行的代码（或从 try 块调用的函数）抛出异常时，handler 才会被调用。换句话说，handler 不是普通的函数，不能直接调用，也不能跳入。

文法要点：

```text
try-block:          try compound-statement handler-seq
function-try-block: try ctor-initializer(opt) compound-statement handler-seq
handler:            catch ( exception-declaration ) compound-statement
exception-declaration:
    attribute-specifier-seq(opt) type-specifier-seq declarator
    attribute-specifier-seq(opt) type-specifier-seq abstract-declarator(opt)
    ...
```

- `try` 后面必须是复合语句（带花括号），`catch` 后面也是；`try f();` 不合法。
- *handler-seq* 至少有一个 handler。
- *exception-declaration* 与函数形参声明的形状相同：可以带名字（`catch (E& e)`），可以不带（`catch (E&)`），也可以是 `...`。
- *exception-declaration* 里可选的属性说明符序列属于 catch 子句的形参，也就是 [[except.handle]] 所说的 handler 的参数，例如 `catch ([[maybe_unused]] const E& e)`。

```cpp run title="handler-syntax.cpp" ok
#include <cstdio>
#include <stdexcept>

int main() {
    try {
        throw std::runtime_error("boom");
    } catch ([[maybe_unused]] const std::logic_error& e) {   // 属性属于形参 e
        std::puts("logic_error");
    } catch (const std::exception&) {                         // 无名形参
        std::puts("exception");
    } catch (...) {                                           // 匹配任意异常
        std::puts("other");
    }
}
```

## try 块是语句（¶2）

¶2 *try-block* 是一种语句（[[stmt.pre]]），因此可以出现在任何语句可以出现的地方。注 1 约定：本章说"try 块"时同时指 *try-block* 和 *function-try-block*。

*function-try-block* 则不是语句，它是 *function-body* 的一种形式（[[dcl.fct.def.general]]），只能用作整个函数体。

## 不能跳进 try 块与 handler（¶3 前半）

¶3 try 块的复合语句和 handler 的复合语句都是控制流受限语句（control-flow-limited statement，[[stmt.label#3]]）。根据那里的定义，这意味着两条规则：

1. 其中的 `case`/`default` 标号只能属于其内部的 `switch`；
2. 其中声明的标号只能由其内部的 `goto` 引用。

所以从外面 `goto` 进 try 块或 handler、从 handler 里 `goto` 回 try 块、让 `switch` 的 `case` 落在 try 块里，都是非良构的。

```cpp title="goto-into-try.cpp" error
void f(int c) {
    goto l1;            // error: l1 声明在 try 块的复合语句里
    try {
        l1: ;
    } catch (...) {
        goto l1;        // error: 从 handler 跳进 try 块也不行
    }
    switch (c) {
        try {
            case 1: ;   // error: case 标号必须属于 try 块内部的 switch
        } catch (...) { }
    }
}
```

```cpp title="goto-inside-try.cpp" ok
void f() {
    try {
        goto l1;        // OK: 标号和 goto 都在同一个 try 块里
        l1: ;
    } catch (...) {
        goto l2;        // OK: 标号和 goto 都在同一个 handler 里
        l2: ;
    }
}
```

为什么要禁止跳入？try 块不只是一个作用域，进入它在运行时是有语义的：handler 搜索依据的是哪些 try 块已进入但尚未退出（[[except.throw#2]]）。如果跳过 `try` 关键字直接落到块中间，实现就无法确定此时是否处于 try 块中。跳进 handler 更说不通，因为那里没有当前处理的异常，`throw;` 和 handler 参数都没有意义。在 Itanium 实现中，是否处于 try 块中体现为调用点落在 LSDA 表中的哪一段（见 [[toolchain/exception-implementation]]），跳转进入本身并不是技术障碍，但在语义上没有意义，所以语言直接禁止。

!!! note "与 C++23 之前的措辞对比"
    在 C++23 之前，这条规则写成"不能用 `goto` 或 `switch` 把控制转入 try 块或 handler"。现在的写法借用了 [[stmt.label]] 统一定义的控制流受限语句，同一概念也用于 `if constexpr`、`if consteval` 的分支和展开语句体。效果相同。

!!! lawyer
    Clang 的诊断把这类错误描述为跳转绕过了 try 块的初始化，因为实现上它沿用了检查跳过带初始化的声明的那套机制（[[stmt.dcl]]）。标准的依据则是控制流受限语句。

## 跳出 try 块：按声明的上下文析构（¶3 后半）

反方向是允许的：`goto`、`break`、`return`、`continue` 都可以把控制转出 try 块或 handler。此时 try 块里声明的每个变量都在直接包含其声明的上下文中析构。

这句话的要点在于析构时 handler 的归属：如果一个变量的析构函数抛出异常，能接住它的是包住该变量声明的那些 try 块的 handler，而不是 `goto` 目标处的 handler。

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

运行结果（本机 Clang 23）：

```text
~t2
handler 2 caught t2
~t1
```

`goto lab` 触发 `t2` 的析构；`t2` 的析构函数抛出的异常由 handler 2 接住，因为 `t2` 是在内层 try 块里声明的。异常打断了 `goto`，控制流不再继续执行它，而是从 handler 2 之后继续：内层 try 块结束，外层 try 块的复合语句结束，`t1` 正常析构。这与标准例 2 的叙述一致："销毁 `t2` 时抛出的异常会执行 handler 2；销毁 `t1` 时抛出的异常会执行 handler 1"。

## function-try-block（¶4）

¶4 *function-try-block* 把 *handler-seq* 关联到 *ctor-initializer*（如果有）和函数体的复合语句。它能捕获：

- 函数体执行中抛出的异常（这一点普通 try 块也做得到）；
- 对构造函数：初始化子对象（基类、成员，即 *mem-initializer* 和默认成员初始化器）时抛出的异常；
- 对析构函数：析构子对象时抛出的异常。

function-try-block 之所以存在，完全是为了后两项：成员初始化发生在函数体的 `{` 之前，普通 try 块包不住它。

```cpp run title="ctor-ftb.cpp" ok
#include <cstdio>

struct Member {
    explicit Member(int x) { if (x < 0) throw x; }
};

struct C {
    Member m;
    explicit C(int x)
    try : m(x) {                          // ctor-initializer 也在 try 的范围内
        std::puts("ctor body");
    } catch (int e) {
        std::printf("ctor handler saw %d\n", e);
        // 控制流到达构造函数 handler 末尾：隐式 throw;（[except.handle]/14）
    }
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

构造函数的 function-try-block 无法吞掉异常：对象没能构造出来，调用方必须知道这一点。这由 [[except.handle]] 的三条规则保证：

| 规则 | 出处 |
|---|---|
| 构造函数/析构函数的 function-try-block 的 handler 执行到末尾时，自动重抛当前处理的异常 | [[except.handle#14]] |
| 构造函数的 function-try-block 的 handler 里出现 `return` 语句 ⇒ 非良构 | [[except.handle#13]] |
| 在构造/析构函数的 function-try-block 的 handler 里引用该对象的非静态成员或基类 ⇒ UB（它们已经被销毁了） | [[except.handle#11]] |

```cpp title="ctor-handler-return.cpp" error
struct M { M(int); };
struct C {
    M m;
    C(int x) try : m(x) { } catch (...) {
        return;     // error: 构造函数 function-try-block 的 handler 中不能有 return
    }
};
```

handler 能做的事情只有记日志、把异常翻译成另一种异常抛出，以及清理非成员资源（例如通过构造函数形参传入的东西）。

!!! tip "析构函数的 function-try-block"
    析构函数的 handler 执行到末尾也会自动重抛（[[except.handle#14]]），但析构函数的 handler 里可以写 `return;`，这样异常就被吞掉了。这是标准中析构函数从子对象析构抛出的异常中静默恢复的唯一方式。不过析构函数默认是 `noexcept` 的（[[except.spec#8]]），所以这种写法本来就少见。

```cpp run title="dtor-ftb.cpp" ok
#include <cstdio>

struct Bad { ~Bad() noexcept(false) { throw 1; } };

struct H {
    Bad b;
    ~H() noexcept(false)
    try {
    } catch (int) {
        std::puts("dtor handler");   // 子对象 b 的析构抛出，在这里被捕获
    }                                // 到达末尾：自动重抛
};

int main() {
    try { H h; } catch (int) { std::puts("rethrown to main"); }
}
```

对普通函数，function-try-block 的 handler 与普通 try 块包住整个函数体几乎相同（流出 handler 末尾等价于流出函数体末尾，[[except.handle#14]]）；区别只在形参的作用域：function-try-block 的 handler 里可以访问函数形参。`main` 的 function-try-block 有特殊限制：它捕获不到静态存储期对象构造/析构时抛出的异常（[[except.handle#12]]）。

## 之前与之后（¶5）

¶5 本章中的 "before" 与 "after" 指 sequenced before 关系（[[intro.execution]]）。[[basic.life]] 使用的是 happens-before，这里用的则是单线程内的顺序，因为异常处理本身是一个线程内部的过程（[[except.throw#4]] 注 2：异常处理不隐含任何线程同步）。

## 陷阱

!!! pitfall "function-try-block 不能挽救构造函数"
    很多人以为在构造函数 handler 里修好成员就能让对象继续构造，这做不到：进入 handler 时所有已构造的子对象都已析构（[[except.ctor#3]]），handler 末尾又会自动重抛。如果想在失败时回退到默认值，应当在成员的初始化表达式里用普通 try 块或工厂函数处理，而不是 function-try-block。

!!! pitfall "构造函数 handler 里访问成员"
    ```cpp
    struct S {
        std::string name;
        Res r;
        S() try : name("x"), r(open()) {} catch (...) {
            log(name);    // UB: name 已经被析构（[except.handle]/11）
        }
    };
    ```
    Clang 对此会给出 `-Wexceptions` 警告（"cannot refer to a non-static member from the handler of a constructor function try block"），但这只是警告。需要信息的话，应使用构造函数的形参或静态数据。

## 思考题

!!! question "思考题 1"
    下面的代码是否良构？如果把 `switch` 放进 try 块内部呢？

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

非良构。`case 1:` 位于 try 块的复合语句中，而该复合语句是控制流受限语句（¶3），其中的 `case` 标号必须与其内部的 `switch` 关联（[[stmt.label#3]]）。这里关联的 `switch` 在 try 块外部，所以违规。`case 0:` 没有问题，它在 try 块外。

如果改成 `try { switch (c) { case 1: break; } } catch (...) {}`，`switch` 与 `case` 都在 try 块内，就是良构的。
</details>

!!! question "思考题 2"
    构造函数的 function-try-block 的 handler 不能写 `return`，那么它能不能用 `throw;` 以外的方式结束？例如抛出一个不同的异常，或者调用 `std::exit`？

<details markdown="1">
<summary>答案</summary>

可以。¶4 / [[except.handle#14]] 只规定控制流到达 handler 末尾时自动重抛；handler 用 `throw OtherError{};` 抛出另一个异常完全合法，这就是异常翻译的惯用法。调用 `std::exit`、`std::terminate` 或进入死循环也都合法，因为它们根本不会到达 handler 末尾。被禁止的只有 `return`（[[except.handle#13]]，必须诊断）。
</details>

## 小结

!!! summary
    - try 块是语句；function-try-block 是函数体的一种形式，能额外捕获子对象初始化（构造函数）/析构（析构函数）中的异常。
    - try 块和 handler 的复合语句是控制流受限语句：不能 `goto`/`case` 进去，但可以用 `goto`/`break`/`return`/`continue` 出来。
    - 跳出时局部变量在其声明所在的上下文中析构，析构抛出的异常由包围该声明的 handler 处理。
    - 构造/析构函数 function-try-block 的 handler：末尾自动重抛；构造函数 handler 不能 `return`；访问成员是 UB。
