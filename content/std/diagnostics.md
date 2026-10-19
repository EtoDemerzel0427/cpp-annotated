---
title: 诊断库
summary: 第 19 章导读：<stdexcept> 异常类、assert、errno、<system_error>、<stacktrace>、<debugging> 各自解决什么问题，怎样分工，与语言里的异常和契约是什么关系。
status: done
covers: diagnostics.general
related: std.exceptions, assertions, errno, syserr, stacktrace, debugging, except, support.exception, basic.contract, res.on.exception.handling
tags: 标准库, 诊断, 错误处理, 异常
updated: 2026-10-19
---

!!! tldr
    - 第 19 章收录六组工具：预定义异常类、`assert`、`errno`、`<system_error>`、`<stacktrace>`（C++23）、`<debugging>`（C++26）。
    - 程序自己的 bug（违反前置条件）用断言或契约报告；文件不存在、超时这类环境造成的失败用异常或错误码报告。
    - `<filesystem>` 等接口通常同时提供抛 `system_error` 的版本和通过 `error_code&` 出参报告的版本，两者共用同一套错误码。
    - `throw`、`try`、`std::exception`、契约都不在这一章，分别见 [[except]]、[[support.exception]]、[[basic.contract]]。

[diagnostics] ¶1 说，本章描述 C++ 程序可以用来检测和报告错误状况的组件。¶2 的表 49 列出了六组：

| 子条款 | 头文件 | 解决的问题 |
|---|---|---|
| [[std.exceptions]] | `<stdexcept>` | 一套预定义的异常类型，分逻辑错误和运行期错误两支 |
| [[assertions]] | `<cassert>` | `assert` 宏，可以用 `NDEBUG` 关掉 |
| [[errno]] | `<cerrno>` | C 和 POSIX 风格的线程局部错误号 |
| [[syserr]] | `<system_error>` | 把操作系统或底层 API 的整数错误码包装成可移植、可比较、可扩展的类型 |
| [[stacktrace]] {{c++23}} | `<stacktrace>` | 在运行时获取当前调用栈 |
| [[debugging]] {{c++26}} | `<debugging>` | 与调试器交互：设断点、检测调试器是否在场 |

错误处理的其他部分在别处。异常的语言机制（`throw`、`try`、栈展开）在 [[except]]；`std::exception` 基类、`bad_alloc`、`exception_ptr`、`terminate` 在语言支持库 [[support.exception]]；`std::expected` 在通用工具库；契约断言 `pre`、`post`、`contract_assert` 在核心语言 [[basic.contract]]。

## 怎样分工

| 错误的性质 | 报告方式 |
|---|---|
| 程序自身的 bug，例如违反前置条件 | `assert`、契约断言；库选择检查时抛 `logic_error` 一支 |
| 环境造成的失败，例如文件不存在、超时 | 抛 `runtime_error` 一支或 `system_error`；或者用 `error_code` 出参、返回值；C 和 POSIX 接口用 `errno` |
| 事后定位问题 | `stacktrace` 记录调用路径，`<debugging>` 交给调试器 |

标准没有强制这种分工，但库的设计体现了它：

- 违反标准库函数的 *Preconditions* 是未定义行为（[[structure.specifications]]），不会抛 `logic_error`。C++26 的[[g:hardened-implementation|加固实现]]把一部分加固前置条件的违反变成契约违反。`logic_error` 一支用于库主动检查并报告的情形，例如 `vector::at` 抛的 `out_of_range`。
- 对可预期的环境失败，库往往两种方式都提供。`<filesystem>` 的大多数操作有两个重载：一个抛 `filesystem_error`（派生自 `system_error`），一个接受 `error_code&` 出参、不抛异常。
- `errno` 是与 C 兼容的遗留设施。[[syserr]] 的组件不修改 `errno`（[[syserr.general]] ¶2），两者通过 `errc` 枚举和 `generic_category()` 衔接。

## 独立实现

[[g:freestanding-implementation|独立实现]]（可以没有操作系统支持的实现）也要提供 `<cerrno>` 中的 `E*` 宏、`<system_error>` 中的 `errc` 枚举，以及整个 `<debugging>`。`errno` 本身、依赖 `std::string` 的 `<stdexcept>`、`<stacktrace>` 只在宿主实现中提供。

## C++23 以来的变化

- `<stacktrace>` 在 C++23 加入（[[P0881R7]]），格式化支持来自 [[P2693R1]]。
- `assert` 在 C++26 变成可变参数宏（[[P2264R7]]），模板实参里的逗号不再需要额外的括号。
- `<debugging>` 在 C++26 加入（[[P2546R5]]），`is_debugger_present` 后来被规定为可替换函数（[[P2810R4]]）。
- `<stdexcept>` 中所有异常类的构造函数在当前草案中都是 `constexpr`，配合 C++26 允许在常量求值中抛出异常（[[P3068R6]]）。
- `error_code` 有了 `std::formatter` 特化（[[syserr.fmt]]），这是 C++23 之后的新措辞。

截至写作时，本机 Clang 23 + libc++ 还没有提供 `<stacktrace>` 和 `<debugging>`，也不支持在常量求值中抛出异常。
