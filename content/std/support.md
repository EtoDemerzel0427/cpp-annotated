---
title: 语言支持库
summary: 第 17 章导读——核心语言"隐式调用的函数"和"隐式生成的对象的类型"所在之处：基础类型、实现属性、程序终止、动态内存、RTTI、源码位置、异常、契约、初始化列表、三路比较、协程与 C 运行时设施
status: done
covers: support.general
related: support.types, support.limits, support.arith.types, support.start.term, support.dynamic, support.rtti, support.srcloc, support.exception, support.contract, support.initlist, cmp, support.coroutine, support.runtime, support.c.headers
tags: 导读, 标准库, 语言支持
updated: 2026-10-18
---

第 17 章 [support] 是标准库中**离核心语言最近**的一章。¶1（[support.general]）把它的内容概括为两类东西：

!!! std
    This Clause describes the function signatures that are called implicitly, and the types of objects generated implicitly, during the execution of some C++ programs.

    本章描述在某些 C++ 程序执行期间**被隐式调用的函数签名**，以及**被隐式生成的对象的类型**。

"隐式"是理解本章的钥匙。你没有写 `operator new(sizeof(T))`，但 `new T` 调用了它；你没有写 `throw std::bad_cast()`，但失败的 `dynamic_cast<T&>` 抛出了它；你没有构造 `std::initializer_list`，但 `{1, 2, 3}` 生成了它；你没有调用 `std::coroutine_traits`，但每个协程定义都要用它找 promise 类型。核心语言在这些地方**指名道姓地引用**库组件——于是这些组件实际上是语言的一部分，只是住在头文件里。

## 本章地图

¶2 列出了各子条款及其头文件（表 42）：

| 子条款 | 头文件 | 核心语言中的"挂钩" |
|---|---|---|
| [[support.types]] 公共定义 | `<cstddef>`、`<cstdlib>` | `sizeof` → `size_t`，指针相减 → `ptrdiff_t`，`nullptr` → `nullptr_t`，`max_align_t` 界定基本对齐，`std::byte` 可访问任何对象表示 |
| [[support.limits]] 实现属性 | `<cfloat>`、`<climits>`、`<limits>`、`<version>` | 把 [[basic.fundamental]] 中由实现定义的性质暴露给程序；库特性测试宏 |
| [[support.arith.types]] 算术类型 | `<cstdint>`、`<stdfloat>` | 定宽整数；[[basic.extended.fp]] 的扩展浮点类型别名 |
| [[support.start.term]] 启动与终止 | `<cstdlib>` | `main` 返回 → `exit`（[[basic.start.main]]）；`atexit` 与静态析构交错（[[basic.start.term]]） |
| [[support.dynamic]] 动态内存管理 | `<new>` | *new-expression* / *delete-expression* 调用的分配与释放函数（[[new.delete]]）、`bad_alloc`（[[alloc.errors]]）、`std::launder`（[[ptr.launder]]） |
| [[support.rtti]] 类型识别 | `<typeinfo>`、`<typeindex>` | `typeid` → `type_info`；`bad_cast`、`bad_typeid` |
| [[support.srcloc]] 源码位置 | `<source_location>` | 编译器内建的调用点信息 |
| [[support.exception]] 异常处理 | `<exception>` | `std::terminate`（[[except.terminate]]）、`uncaught_exceptions`；`exception_ptr` 与嵌套异常（[[propagation]]） |
| [[support.contract]] 契约违反处理 | `<contracts>` | 契约违反处理函数的实参 `contract_violation`（[[basic.contract]]） |
| [[support.initlist]] 初始化列表 | `<initializer_list>` | 列表初始化生成 `initializer_list`（[[dcl.init.list]]） |
| [[cmp]] 比较 | `<compare>` | `<=>` 的结果类型（[[expr.spaceship]]、[[class.spaceship]]） |
| [[support.coroutine]] 协程 | `<coroutine>` | promise 类型的查找与协程句柄（[[dcl.fct.def.coroutine]]） |
| [[support.runtime]] 其他运行时支持 | `<csetjmp>`、`<csignal>`、`<cstdarg>`、`<cstdlib>` | 可变参数（[[expr.call]]）、`longjmp` 与析构、信号安全 |
| [[support.c.headers]] C 头文件 | `<name.h>` | 与 C 的互操作 |

## "语言依赖库"的几种形态

本章组件与核心语言的耦合程度不同，大致可以分为三档：

1. **必须先声明才能用语言特性**。`typeid` 要求 `std::type_info` 已声明（[[expr.typeid]]）；`<=>` 要求比较类别类型已声明（[[expr.spaceship]]）；列表初始化要求 `std::initializer_list` 已声明（[[dcl.init.list]]）；协程定义要求 `std::coroutine_traits` 可用（[[dcl.fct.def.coroutine]]）。忘记包含头文件，程序非良构。
2. **隐式声明、可以替换**。全局 `operator new`/`operator delete` 在每个翻译单元中都**隐式声明**，无需包含 `<new>`；程序可以提供**替换函数**（[[dcl.fct.def.replace]]），但必须遵守本章规定的 *Required behavior*（[[new.delete]]）。契约违反处理函数（[[basic.contract.handler]]）的可替换性则由实现定义。
3. **由编译器内建实现的库接口**。`offsetof`（`__builtin_offsetof`）、`std::launder`（`__builtin_launder`）、`std::source_location::current`（`__builtin_source_location`）、`coroutine_handle` 的各操作（`__builtin_coro_*`）——它们形式上是库，实际上不可能用普通 C++ 写出来。

## 阅读本章需要的库条款术语

库条款用一套固定的"元素"描述函数（[[structure.specifications]]），每个元素的法律后果不同，读本章时要随时分辨：

| 元素 | 违反时的后果 | 本章例子 |
|---|---|---|
| *Mandates* | 程序**非良构**（必须诊断） | `std::launder` 要求 `T` 不是函数或 `void`（[[ptr.launder]]） |
| *Constraints* | 该声明**不参与重载决议** | `std::byte` 的移位运算要求 `is_integral_v<IntType>`（[[support.types]]） |
| *Preconditions* | **未定义行为** | `rethrow_exception` 要求非空（[[propagation]]）；`coroutine_handle::resume` 要求协程挂起且不在最终挂起点（[[support.coroutine]]） |
| *Effects* / *Returns* | 规定行为与结果；"Equivalent to" 连 UB 一起照搬 | `byte` 运算等价于 `unsigned int` 运算 |
| *Required behavior* | 对**替换函数和处理函数**的要求，违反则 UB | `operator new` 失败必须抛 `bad_alloc`；`terminate_handler` 不得返回 |
| *Default behavior* | 库自带版本的行为 | `operator new` 的 new_handler 循环 |
| *Remarks* | 附加的规范性说明 | 可替换性、信号安全性 |
| *Recommended practice* | 对实现的建议，非强制 | `source_location` 的行列号取值、`contract_violation::comment()` 的内容 |

此外，本章很多头文件被标注为 **freestanding**（独立实现也必须提供）：`<cstddef>`、`<limits>`、`<new>`、`<typeinfo>`、`<exception>`、`<initializer_list>`、`<compare>`、`<coroutine>`、`<source_location>`、`<contracts>`、`<cstdarg>` 等，正因为它们是语言特性的一部分。

## 小结

!!! summary
    - 第 17 章是"住在头文件里的核心语言"：核心语言条款直接引用这里的类型与函数。
    - 部分语言特性要求先包含对应头文件，否则非良构；全局分配函数则隐式声明并可替换。
    - 许多组件由编译器内建实现，库只是接口。
    - 阅读本章时始终区分 Mandates（非良构）、Constraints（退出重载决议）、Preconditions（UB）、Required behavior（约束替换版本）。
