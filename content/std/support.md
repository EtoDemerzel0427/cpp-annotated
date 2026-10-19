---
title: 语言支持库
summary: 第 17 章导读：核心语言在背后隐式调用的函数、隐式生成的对象的类型都定义在这一章，例如 operator new、type_info、initializer_list 和比较类别类型。
status: done
covers: support.general
related: support.types, support.limits, support.arith.types, support.start.term, support.dynamic, support.rtti, support.srcloc, support.exception, support.contract, support.initlist, cmp, support.coroutine, support.runtime, support.c.headers
tags: 导读, 标准库, 语言支持
updated: 2026-10-19
---

!!! tldr
    - 读完这一章，可以回答这样的问题：`new T` 实际调用了哪个函数？为什么用 `<=>` 之前必须包含 `<compare>`？`std::exit` 会析构哪些对象？
    - 这一章的组件被核心语言条款直接引用，相当于定义在头文件里的语言特性。
    - 有些语言特性要求先包含对应的头文件，否则程序非良构；全局 `operator new` 则无需包含任何头文件就已声明，而且可以被程序替换。
    - 这一章的头文件大多要求独立实现也提供，因为没有它们，相应的语言特性就无法使用。

## 语言在背后调用的库

¶1 第 17 章 [support] 描述某些 C++ 程序执行时被隐式调用的函数、隐式生成的对象的类型，以及声明它们的头文件。

隐式是这里的关键。程序没有写 `operator new(sizeof(T))`，但 `new T` 调用了它；没有写 `throw std::bad_cast()`，但失败的 `dynamic_cast<T&>` 抛出了它；没有构造 `std::initializer_list`，但 `{1, 2, 3}` 在某些语境下生成了它；没有提到 `std::coroutine_traits`，但每个协程都要靠它找到 promise 类型。核心语言在这些地方直接点名使用库组件，所以这些组件实际上是语言的一部分。

## 本章地图

¶2 表 42 列出了各子条款及其头文件：

| 子条款 | 头文件 | 与核心语言的联系 |
|---|---|---|
| [[support.types]] 公共定义 | `<cstddef>`、`<cstdlib>` | `sizeof` 的类型 `size_t`，指针相减的类型 `ptrdiff_t`，`nullptr` 的类型 `nullptr_t`，`std::byte` |
| [[support.limits]] 实现属性 | `<cfloat>`、`<climits>`、`<limits>`、`<version>` | 查询 [[basic.fundamental]] 中由实现决定的性质；库特性测试宏 |
| [[support.arith.types]] 算术类型 | `<cstdint>`、`<stdfloat>` | 定宽整数；扩展浮点类型的别名（[[basic.extended.fp]]） |
| [[support.start.term]] 启动与终止 | `<cstdlib>` | 从 `main` 返回等于调用 `exit`（[[basic.start.main]]）；`atexit` 与静态对象析构的顺序（[[basic.start.term]]） |
| [[support.dynamic]] 动态内存管理 | `<new>` | new 表达式和 delete 表达式调用的分配与释放函数（[[new.delete]]）、`bad_alloc`、`std::launder` |
| [[support.rtti]] 类型识别 | `<typeinfo>`、`<typeindex>` | `typeid` 的结果 `type_info`；`bad_cast`、`bad_typeid` |
| [[support.srcloc]] 源码位置 | `<source_location>` | 调用点的文件名和行号 |
| [[support.exception]] 异常处理 | `<exception>` | `std::terminate`（[[except.terminate]]）、`uncaught_exceptions`、`exception_ptr` |
| [[support.contract]] 契约违反处理 | `<contracts>` | 传给契约违反处理函数的 `contract_violation`（[[basic.contract]]） |
| [[support.initlist]] 初始化列表 | `<initializer_list>` | 列表初始化生成的 `initializer_list`（[[dcl.init.list]]） |
| [[cmp]] 比较 | `<compare>` | `<=>` 的结果类型（[[expr.spaceship]]） |
| [[support.coroutine]] 协程 | `<coroutine>` | promise 类型的查找、协程句柄（[[dcl.fct.def.coroutine]]） |
| [[support.runtime]] 其他运行时支持 | `<csetjmp>`、`<csignal>`、`<cstdarg>`、`<cstdlib>` | 可变参数（[[expr.call]]）、`longjmp`、信号处理函数中能做什么 |
| [[support.c.headers]] C 头文件 | `<stdio.h>` 等 | 与 C 代码互操作 |

## 语言与库的三种耦合方式

**必须先包含头文件。** 使用 `typeid` 之前要包含 `<typeinfo>`（[[expr.typeid]]），使用 `<=>` 之前要包含 `<compare>`（[[expr.spaceship]]），列表初始化用到 `std::initializer_list` 时它必须已经声明（[[dcl.init.list]]），协程需要 `std::coroutine_traits`（[[dcl.fct.def.coroutine]]）。缺少头文件时程序非良构。

<div class="compare" markdown="1">

```cpp run error
struct P {
  int x;
  auto operator<=>(const P&) const
    = default;
};
// error: 没有包含 <compare>
```

```cpp run ok
#include <compare>
struct P {
  int x;
  auto operator<=>(const P&) const
    = default;
};
```

</div>

**隐式声明，可以替换。** 全局 `operator new` 和 `operator delete` 在每个翻译单元中都已隐式声明，不需要包含 `<new>`。程序可以提供自己的版本替换它们（[[dcl.fct.def.replace]]），但替换版本必须满足 [[new.delete]] 的要求。契约违反处理函数能否替换由实现决定（[[basic.contract.handler]]）。

**形式上是库，实际由编译器实现。** `offsetof`、`std::launder`、`std::source_location::current`、`coroutine_handle` 的各个操作都无法用普通的 C++ 代码写出来。Clang 用内建函数实现它们，例如 `__builtin_offsetof`、`__builtin_launder`。

## 读库条款要分清的几种要求

库条款用一套固定的元素描述每个函数（[[structure.specifications]]）。它们的后果不同，读这一章时要随时分辨：

| 元素 | 不满足时的后果 | 本章的例子 |
|---|---|---|
| *Mandates* | 程序非良构，必须诊断 | `std::launder<T>` 要求 `T` 不是函数类型或 `void` |
| *Constraints* | 这个声明不参与重载决议 | `std::byte` 的移位运算要求移位量是整数类型 |
| *Preconditions* | 未定义行为 | `coroutine_handle::resume` 要求协程处于挂起状态，且不在最终挂起点 |
| *Required behavior* | 对替换函数和处理函数的要求，违反则行为未定义 | 替换的 `operator new` 失败时必须抛 `bad_alloc`；`terminate_handler` 不得返回 |

*Effects* 中写 Equivalent to 时，规定的语义就是那段代码的语义，连其中的未定义行为一起照搬。

## 独立实现

独立实现（freestanding implementation）是可以在没有操作系统的环境中运行的实现，常见于内核和嵌入式开发，它只需提供标准库的一个子集（[[compliance]]）。这一章的 `<cstddef>`、`<limits>`、`<new>`、`<typeinfo>`、`<exception>`、`<initializer_list>`、`<compare>`、`<coroutine>`、`<source_location>`、`<contracts>`、`<cstdarg>` 等都在这个子集里，因为没有它们，`new`、`typeid`、`<=>`、协程这些语言特性就无法使用。
