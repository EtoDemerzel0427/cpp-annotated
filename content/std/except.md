---
title: 异常处理
summary: 第 14 章导读——try 块与 handler 的语法、异常对象的诞生与销毁、栈回溯、handler 匹配、异常说明（noexcept）、std::terminate 的全部触发场景，以及它们在 Itanium ABI 上的实现
status: done
related: except.pre, except.throw, except.ctor, except.handle, except.spec, except.special, expr.throw, expr.unary.noexcept, support.exception, toolchain/exception-implementation
tags: 导读, 异常
updated: 2026-10-17
---

第 14 章 [except] 规定 C++ 的**异常处理**（exception handling）：一种把**控制**和**信息**从执行中的某一点，转移到此前经过、仍未退出的某个 handler 的机制。它是 C++ 里唯一一种能**跨越任意多层函数调用**、并且沿途**自动调用析构函数**的非局部控制转移——`return` 只能退一层，`longjmp` 能退多层却不管析构（[[csetjmp.syn]]）。

本章很短（六节），但它和标准的许多别的部分紧密咬合：

- 抛出异常的**表达式**在 [[expr.throw]]；`noexcept` **运算符**在 [[expr.unary.noexcept]]；
- 异常说明是**函数类型**的一部分（[[dcl.fct#13]]），因此影响函数指针转换（[[conv.fctptr]]）、重载、虚函数覆盖；
- 异常对象的存储、`std::exception_ptr`、`std::uncaught_exceptions`、`std::terminate` 的库接口在 [[support.exception]]；
- 构造函数抛出异常时"已经构造好的子对象"由 [[class.base.init]]、[[dcl.init.aggr]] 等定义，栈回溯（[[except.ctor]]）据此决定析构谁；
- 常量求值中允许抛出并捕获异常 {{c++26}}（[[expr.const.core#2]] 第 24、25 项）。

## 本章地图

| 节 | 条款 | 回答的问题 |
|---|---|---|
| 14.1 | [[except.pre]] | `try` 块、handler、function-try-block 的语法；不能用 `goto`/`switch` 跳进 try 块；跳出 try 块时析构什么 |
| 14.2 | [[except.throw]] | 抛出异常 = 初始化一个**异常对象**；它存在哪、何时销毁、类型有什么要求；"未捕获"的精确定义；异常处理机制自己调用的函数再抛异常 ⇒ `std::terminate` |
| 14.3 | [[except.ctor]] | **栈回溯**：按构造完成的逆序销毁自动对象；构造/析构半途抛出时哪些子对象要析构；委托构造函数；`new` 表达式归还内存 |
| 14.4 | [[except.handle]] | handler **匹配**规则（只有四种情形，没有一般的隐式转换！）；按顺序尝试；`catch(...)`；"当前处理的异常"；function-try-block 的特殊规则；找不到 handler 时怎么办 |
| 14.5 | [[except.spec]] | **异常说明**：`noexcept(常量表达式)`；潜在抛出的表达式；析构函数、释放函数、预置特殊成员的隐式异常说明；何时"需要"计算异常说明 |
| 14.6 | [[except.special]] | `std::terminate` 的所有触发场景；在这些场景下是否回溯栈 |

建议阅读顺序：[[except.pre]] → [[except.throw]] → [[except.handle]] → [[except.ctor]] → [[except.spec]] → [[except.special]]。先理解"异常对象"和"handler 匹配"，栈回溯与 noexcept 就是在这两者之上的细节。

## 一次异常的完整生命

用一个例子把各节串起来：

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
    throw Err{42};                 // [except.throw]：初始化异常对象，类型 Err
}                                  // [except.ctor]：栈回溯销毁 r（此时异常"未捕获"）

void middle() noexcept(false) {
    Res r{"middle"};
    inner();
}

int main() {
    try {
        Res r{"try"};
        middle();
    } catch (const Err& e) {       // [except.handle]：Err 与 Err 同类型 ⇒ 匹配
        std::printf("caught %d (uncaught=%d)\n", e.code, std::uncaught_exceptions());
    }                              // handler 退出：异常对象被销毁（[except.throw]/4.1）
}
```

输出：

```text
~inner (uncaught=1)
~middle (uncaught=1)
~try (uncaught=1)
caught 42 (uncaught=0)
```

时间线是：

1. **抛出**：`throw Err{42}` 以拷贝初始化的方式创建**异常对象**（[[except.throw#3]]），存储方式未指定（不走 `operator new`）。从此刻起异常处于"未捕获"状态（[[except.throw#6]]）。
2. **查找**：沿调用链向外寻找"最近的、类型匹配的"handler（[[except.throw#2]]、[[except.handle#3]]）。途中如果穿过 `noexcept` 函数的边界，直接 `std::terminate`（[[except.handle#7]]）。
3. **回溯**：控制离开每一层时，销毁该层已经构造好的自动对象（[[except.ctor#2]]）。
4. **激活**：handler 的参数初始化完成，handler 变为**活动的**（active），异常变为"已捕获"（[[except.handle#9]]、[[except.throw#8]]）。
5. **结束**：handler 以非重抛的方式退出，异常对象销毁（除非还有 `std::exception_ptr` 引用它，[[except.throw#4]]）。

## 设计哲学：零开销与"错误路径很贵"

C++ 的异常是按照"**不抛就不付钱**"（zero-overhead / zero-cost）的思路设计的：主流实现（Itanium C++ ABI，见 [[toolchain/exception-implementation]]）在正常路径上**不执行任何额外指令**，只在只读数据段里放一张"调用点 → 清理代码"的表；一旦真的抛出，运行时库查表、解析 DWARF 栈帧信息、两遍扫描栈，代价比普通返回高好几个数量级。标准里很多看似奇怪的规则都源于这一取舍：

- **异常对象的存储方式未指定**（[[except.throw#4]]）——实现可以使用专门的堆、线程局部的紧急缓冲区，以便在内存耗尽时仍能抛出 `std::bad_alloc`。
- **找不到 handler 时是否回溯栈由实现定义**（[[except.handle#8]]）——两阶段实现在"搜索"阶段就知道没有 handler，于是不回溯直接 terminate，保留完整的崩溃现场。
- **`noexcept` 违约时栈可以只回溯一部分**（[[except.terminate#2]]）——让编译器在 `noexcept` 函数里省掉清理代码。
- **handler 匹配不做一般的类型转换**（[[except.handle#3]]）——匹配必须在运行时由类型信息（`std::type_info`）完成，不可能在运行时做重载决议。

## 异常与标准其他部分的交汇

| 交汇点 | 规则所在 |
|---|---|
| 构造函数抛出异常时，`new` 表达式归还内存 | [[expr.new]]，[[except.ctor#5]] |
| 静态/线程存储期变量的动态初始化抛出 ⇒ `std::terminate` | [[basic.start.dynamic]]，[[except.terminate#1]] |
| 契约违约处理函数抛出异常 {{c++26}} | [[basic.contract.eval]]，[[except.terminate#1]] |
| 协程体内未捕获的异常交给 `promise.unhandled_exception()` | [[dcl.fct.def.coroutine]] |
| 常量求值中抛出、捕获异常 {{c++26}} | [[expr.const.core#2]] |
| `dynamic_cast` 到引用失败、`typeid(*nullptr_poly)` 抛异常 | [[expr.dynamic.cast]]，[[expr.typeid]] |
| `std::exception_ptr`、`std::nested_exception` | [[propagation]]，[[except.nested]] |

## 小结

!!! summary
    - 一次异常 = **一个异常对象** + **一次 handler 搜索** + **一次栈回溯**；三者分别由 [[except.throw]]、[[except.handle]]、[[except.ctor]] 规定。
    - handler 匹配只有四种情形：同类型、无歧义的 public 基类、指针/成员指针的有限转换、`nullptr_t` 到指针（[[except.handle#3]]）。
    - 异常说明（`noexcept`）是函数类型的一部分；违反它不是 UB 而是 `std::terminate`（[[except.spec]]、[[except.handle#7]]）。
    - 异常处理机制自身出错时一律 `std::terminate`，场景清单在 [[except.terminate]]。
    - 实现细节（两阶段回溯、personality routine、LSDA）见 [[toolchain/exception-implementation]]。
