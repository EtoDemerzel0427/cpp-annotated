---
title: 异常处理
summary: 第 14 章导读：一次异常从抛出、查找 handler、栈回溯到异常对象销毁的全过程，以及各节分别规定哪一步。
status: done
related: except.pre, except.throw, except.ctor, except.handle, except.spec, except.special, expr.throw, expr.unary.noexcept, support.exception, toolchain/exception-implementation
tags: 导读, 异常
updated: 2026-10-19
---

!!! tldr
    - 异常是 C++ 里唯一一种能跨越任意多层函数调用、并且沿途自动调用析构函数的控制转移。
    - 一次异常由三件事组成：初始化一个异常对象，找到类型匹配的 handler，栈回溯销毁途经的自动对象。
    - handler 按运行时类型匹配，只允许少数几种转换，不做一般的隐式转换。
    - 异常处理机制自身出错（回溯中析构函数抛出、找不到 handler、穿出 `noexcept` 函数）一律调用 `std::terminate`。
    - 主流实现在不抛异常的路径上没有额外指令，代价全部放在真正抛出的时候。

## 一次异常的完整过程

```cpp run title="lifecycle.cpp" ok
#include <cstdio>
#include <exception>

struct Res {
    const char* n;
    ~Res() { std::printf("~%s (uncaught=%d)\n", n, std::uncaught_exceptions()); }
};
struct Err { int code; };

void inner() {
    Res r{"inner"};
    throw Err{42};
}

void middle() {
    Res r{"middle"};
    inner();
}

int main() {
    try {
        Res r{"try"};
        middle();
    } catch (const Err& e) {
        std::printf("caught %d (uncaught=%d)\n", e.code, std::uncaught_exceptions());
    }
}
```

输出：

```text
~inner (uncaught=1)
~middle (uncaught=1)
~try (uncaught=1)
caught 42 (uncaught=0)
```

`return` 只能退出一层函数。`longjmp` 能退出多层，却不调用析构函数（[[csetjmp.syn]]）。异常两样都做到了，过程分五步：

1. **抛出**：`throw Err{42}` 初始化一个**异常对象**，它的存储由实现另行管理，不经过 `operator new`（[[except.throw]]）。从这时起异常处于未捕获状态，`std::uncaught_exceptions()` 返回 1。
2. **查找**：沿调用链向外，找最近进入、尚未退出、并且有类型匹配的 handler 的 try 块（[[except.handle]]）。如果查找穿出一个 `noexcept` 函数，直接调用 `std::terminate`。
3. **回溯**：控制离开每一层时，销毁这一层已经构造完成的自动对象，这叫**栈回溯**（[[except.ctor]]）。
4. **捕获**：handler 的参数 `e` 初始化完成后，handler 变为活动的，异常变为已捕获。
5. **销毁**：handler 以重抛以外的方式退出时，异常对象被销毁；如果还有 `std::exception_ptr` 引用它，就等最后一个引用消失。

## 各节分工

| 节 | 回答的问题 |
|---|---|
| [[except.pre]] | `try`、`catch` 和 function-try-block 的语法；为什么不能用 `goto` 跳进 try 块 |
| [[except.throw]] | 异常对象是什么类型、存在哪里、何时销毁；什么时候算未捕获 |
| [[except.ctor]] | 栈回溯销毁哪些对象；构造到一半抛出时哪些子对象要析构 |
| [[except.handle]] | handler 怎样匹配；当前处理的异常；找不到 handler 时怎么办 |
| [[except.spec]] | `noexcept` 说明；哪些函数隐式是 `noexcept` 的 |
| [[except.special]] | 所有调用 `std::terminate` 的情形，以及此时是否回溯栈 |

建议按 [[except.pre]] → [[except.throw]] → [[except.handle]] → [[except.ctor]] → [[except.spec]] → [[except.special]] 的顺序读。先弄清异常对象和 handler 匹配，栈回溯和 `noexcept` 都建立在这两者之上。

## 零开销设计留下的痕迹

Itanium C++ ABI（GCC 和 Clang 在 Linux、macOS 上使用的 ABI）在正常执行路径上不插入任何指令，只在只读数据段里放一张表，记录每个调用点抛出时该执行哪段清理代码。真正抛出时，运行时库查表、解析栈帧信息、扫描两遍栈，比一次普通返回慢几个数量级（细节见 [[toolchain/exception-implementation]]）。标准里有几条看似奇怪的规则正是为这种实现留的余地：

- 异常对象的存储方式未指定（[[except.throw#4]]）。实现可以准备一块紧急缓冲区，内存耗尽时仍能抛出 `std::bad_alloc`。
- 找不到 handler 时是否回溯栈由实现定义（[[except.terminate#2]]）。两阶段实现在搜索阶段就知道没有 handler，于是不回溯，直接终止，保留完整的崩溃现场。
- 查找穿出 `noexcept` 函数时，栈可以只回溯一部分（[[except.terminate#2]]）。编译器因此可以省掉 `noexcept` 函数里的清理代码。
- handler 匹配不做一般的类型转换（[[except.handle#3]]）。匹配在运行时依据类型信息完成，运行时没法做重载决议。

## 与其他章节的交汇

| 交汇点 | 规则所在 |
|---|---|
| 抛出异常的表达式；`noexcept` 运算符 | [[expr.throw]]，[[expr.unary.noexcept]] |
| 异常说明是函数类型的一部分，影响函数指针转换和虚函数覆盖 | [[dcl.fct#13]]，[[conv.fctptr]] |
| `new` 表达式中构造函数抛出时归还内存 | [[expr.new]]，[[except.ctor]] |
| 静态或线程存储期变量的动态初始化抛出时调用 `std::terminate` | [[basic.start.dynamic]]，[[except.terminate]] |
| 协程体内未捕获的异常交给 `promise.unhandled_exception()` | [[dcl.fct.def.coroutine]] |
| 常量求值中抛出并捕获异常 {{c++26}} | [[expr.const.core#2]] |
| `std::exception_ptr`、`std::nested_exception`、`std::terminate` 的库接口 | [[support.exception]] |
