---
title: 诊断库
summary: 第 19 章导读：C++ 标准库报告与诊断错误的六件工具（<stdexcept> 异常类、assert 宏、errno、<system_error> 的错误码/错误状况/错误类别、C++23 的 <stacktrace>、C++26 的 <debugging>）各自解决什么问题、如何分工，以及它们与核心语言异常、契约（contracts）的关系。
status: done
covers: diagnostics.general
related: std.exceptions, assertions, errno, syserr, stacktrace, debugging, except, support.exception, basic.contract, res.on.exception.handling
tags: 标准库, 诊断, 错误处理, 异常
updated: 2026-10-18
---

[diagnostics] ¶1 一句话交代了本章的职责：

!!! std
    This Clause describes components that C++ programs may use to detect and report error conditions.

    本章描述 C++ 程序可用来检测和报告错误状况的组件。

这里的组件并不是错误处理的全部。异常的核心语言机制（`throw`、`try`、栈回溯）在 [[except]]；`std::exception` 基类、`bad_alloc`、`exception_ptr`、`terminate` 在语言支持库 [[support.exception]]；`std::expected` 在通用工具库；契约（`pre`/`post`/`contract_assert`）在核心语言 [[basic.contract]]。本章收录的是剩下的、偏向库的部分：

| 子条款 | 头文件 | 解决的问题 | 本站页面 |
|---|---|---|---|
| [std.exceptions] | `<stdexcept>` | 一套预定义的异常类型，分为逻辑错误和运行期错误两类 | [[std.exceptions]] |
| [assertions] | `<cassert>` | `assert` 宏：可以用 `NDEBUG` 关掉的断言 | [[assertions]] |
| [errno] | `<cerrno>` | C/POSIX 风格的线程局部错误号 | [[errno]] |
| [syserr] | `<system_error>` | 把来自操作系统或底层 API 的整数错误码包装成可移植、可比较、可扩展的类型 | [[syserr]] |
| [stacktrace] {{c++23}} | `<stacktrace>` | 在运行时获取当前调用栈 | [[stacktrace]] |
| [debugging] {{c++26}} | `<debugging>` | 与调试器交互：断点、检测调试器 | [[debugging]] |

（¶2 的表 49 列出了这六项。）

## 一张错误处理的地图

这六件工具对应着不同的错误性质和不同的报告渠道：

```text
         错误的性质                         报告渠道
  ┌──────────────────────┐
  │ 程序自身的 bug        │──► assert / contract_assert / 契约（终止或调试器介入）
  │ （前置条件被违反）    │──► logic_error 族（"本可预防"，但选择抛出）
  ├──────────────────────┤
  │ 环境造成的失败        │──► runtime_error 族、system_error（异常）
  │ （文件不存在、超时）  │──► error_code 出参 / 返回值（不抛异常的重载）
  │                      │──► errno（C 与 POSIX 接口）
  ├──────────────────────┤
  │ 事后定位问题          │──► stacktrace（记录调用路径）、debugging（交给调试器）
  └──────────────────────┘
```

下面几条是经验性的分工原则。标准本身并不强制，但库的设计体现了它们：

- **前置条件违反是 bug，不属于这里说的错误**。违反标准库规格中的 *Preconditions* 是未定义行为（[[structure.specifications]]），而不是抛 `logic_error`；C++26 的强化实现（[[g:hardened-implementation]]）把一部分 *Hardened preconditions* 的违反变成契约违反。`logic_error` 族主要用于库选择检查并报告的情形，如 `vector::at` 的 `out_of_range`。
- 对可预期的环境失败，两条路都提供：`<filesystem>` 的绝大多数操作都提供两个重载——一个抛 `filesystem_error`（派生自 `system_error`），一个接受 `error_code&` 出参、不抛异常。两条路共用同一套 `error_code` 数据。
- `errno` 是与 C 兼容的遗产，`<system_error>` 在设计时刻意不修改 `errno`（[[syserr.general]] ¶2），二者通过 `errc` 枚举与 `generic_category()` 衔接。

## 与 freestanding 的关系

独立实现（[[g:freestanding-implementation]]）需要提供的部分：`<cerrno>` 中的 `E*` 宏、`<system_error>` 中的 `errc` 枚举、整个 `<debugging>`。`errno` 本身、`<stdexcept>`（依赖 `std::string`）、`<stacktrace>` 都只在宿主实现中提供。

## 本章与 C++26 的变化

本章是 C++23/26 中变动较多的一章：

- `<stacktrace>` 在 C++23 加入（[[P0881R7]]），其格式化支持由 [[P2693R1]] 加入。
- `assert` 在 C++26 变成可变参数宏（[[P2264R7]]），解决了模板实参中的逗号问题。
- `<debugging>` 在 C++26 加入（[[P2546R5]]），`is_debugger_present` 随后被规定为可替换函数（[[P2810R4]]）。
- `<stdexcept>` 中所有异常类的构造函数在当前草案中都是 `constexpr` 的，这与 C++26 允许在常量求值中抛出异常（[[P3068R6]]）相配合。
- `error_code` 有了 `std::formatter` 特化（[[syserr.fmt]]，C++23 之后加入草案）。

各页面会说明本机 Clang 23 + libc++ 对这些新特性的支持情况：截至本文编写时，libc++ 尚未提供 `<stacktrace>` 与 `<debugging>`，也不支持在常量求值中抛出异常。
