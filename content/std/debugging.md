---
title: 调试
summary: C++26 的 <debugging>：breakpoint()（语义由实现定义，意图是把控制交给调试器）、breakpoint_if_debugging()、is_debugger_present()（可替换函数，"要求的行为"与"默认行为"之分）；全部 freestanding 且 noexcept；与 __builtin_debugtrap 等编译器内建函数、断言和契约违约处理的关系，以及实现支持现状。
status: draft
covers: *
since: c++26
papers: P2546R5, P2810R4
related: diagnostics, assertions, basic.contract, dcl.fct.def.replace, structure.specifications, stacktrace
tags: 标准库, 调试器, breakpoint, C++26
updated: 2026-10-18
---

{{c++26}} 几乎每个大型 C++ 项目都有一个自己的 `DEBUG_BREAK()` 宏：Windows 上展开为 `__debugbreak()`，GCC/Clang 上是 `__builtin_trap()` 或 `__builtin_debugtrap()`，或者 `raise(SIGTRAP)`，或者内联汇编 `int3`/`brk`。再配上一个"当前是否有调试器附加"的检测函数——Windows 有 `IsDebuggerPresent()`，Linux 要去读 `/proc/self/status` 的 `TracerPid`，macOS 要用 `sysctl` 查 `P_TRACED` 标志。[[P2546R5]] 把这两件事标准化为 `<debugging>`。

## 概述（[debugging.general]）

¶1：[debugging] 描述**内省**并**与程序执行交互**的功能。注 1：这些调试功能与一个可能正在**跟踪**（trace）C++ 程序执行的程序——例如调试器——交互。

这是标准中少有的直接承认"程序之外还有一个调试器"的地方。从抽象机的角度看，调试器是不存在的；所以本节的规定几乎全部是**由实现定义**的，规范性内容很薄，主要价值在于提供一个可移植的**名字**。

## 概要（[debugging.syn]）

```cpp
// all freestanding
namespace std {
  void breakpoint() noexcept;
  void breakpoint_if_debugging() noexcept;
  bool is_debugger_present() noexcept;
}
```

整个头文件都是 **freestanding** 的：嵌入式开发恰恰是最需要"停在这里交给调试器（JTAG/SWD 探针）"的场景。三个函数都是 `noexcept`。

## `breakpoint()`（[debugging.utility] ¶1）

!!! std
    The semantics of this function are implementation-defined.

    该函数的语义**由实现定义**。

规范性文字只有这一句。意图全在注 1 中（非规范）：

- 在有调试器时调用它，程序执行**暂时停止**，控制交给调试器，直到调试器终止程序，或者**如同该函数未被调用一样**恢复程序执行；
- 特别地，**无意**让对它的调用支持以别的方式恢复程序；
- 若没有调试器，程序的执行**可能异常终止**。

"如同未被调用一样恢复"是它与 `__builtin_trap()` 的关键区别：`__builtin_trap()` 生成的是"不可返回"的陷阱指令（编译器认为它之后的代码不可达），调试器即使继续执行也无法正常恢复；而 `breakpoint()` 对应的是**可恢复**的断点陷阱。在 Clang 中这对应 `__builtin_debugtrap()`——在本机 arm64 上它编译为 `brk #0xf000`，调试器（LLDB）能识别并让程序在其后继续。

"没有调试器时可能异常终止"：在 POSIX 系统上，断点指令会产生 `SIGTRAP`，默认动作是终止进程并产生 core dump。所以**不应**在生产代码中无条件调用 `breakpoint()`。

## `breakpoint_if_debugging()`（¶2）

效果等价于：

```cpp
if (is_debugger_present()) breakpoint();
```

这是日常使用中最常用的那个：在断言失败、契约违反、"不可能到达"的分支中调用它，开发者在调试器里运行时直接停在现场，没有调试器时则什么都不做、继续执行后续的错误处理（打印日志、终止……）。

## `is_debugger_present()`（¶3–¶5）

这个函数的规格采用了标准库中用于可替换函数的"两种行为"写法（[[structure.specifications]] ¶5）：

- **要求的行为**（*Required behavior*，¶3）：该函数**没有前置条件**——这约束的是**任何**定义，包括程序自己提供的替换版本；
- **默认行为**（*Default behavior*，¶4）：由实现定义——这描述的是实现提供的那个定义。

注 2 说明了意图：实现应当使用**即时的（不缓存的）查询**来判断程序是否正被调试器跟踪，并只在真的被调试器跟踪时返回 `true`。在 Windows 上可以调用 `::IsDebuggerPresent()`；在兼容 ISO/IEC 23360:2021（Linux Standard Base）的系统上，可以检查是否存在跟踪进程，并尽力判断该跟踪进程是否是调试器。

"不缓存"很重要：调试器可以在程序运行中途附加或分离。

### 可替换（¶5）

!!! std
    *Remarks*: This function is replaceable ([dcl.fct.def.replace]).

    该函数是**可替换的**（[[g:replaceable-function]]）。

和全局 `operator new` 一样，程序可以提供一个具有相同签名的定义来取代实现的版本（[[dcl.fct.def.replace]]）：不得是 `inline` 的、必须附属于全局模块、具有 C++ 语言链接；替换发生在程序启动之前。这一点由 [[P2810R4]] 加入，动机包括：

- 实现的检测方法不适用于某些环境（例如自定义的调试代理、模拟器、嵌入式探针）；
- 测试中需要强制打开或关闭"有调试器"的分支；
- 某些安全敏感的程序希望禁用这项检测。

注意 `breakpoint()` 和 `breakpoint_if_debugging()` **不是**可替换的。

```cpp
#include <cstdlib>
#include <debugging>

// 程序提供的替换定义（整个程序只能有一个）：由环境变量控制，便于在 CI 中测试调试分支
bool std::is_debugger_present() noexcept {
    return std::getenv("FORCE_DEBUGGER") != nullptr;
}
```

## 与断言、契约的配合

`<debugging>` 本身不做任何检查，它是给其他诊断设施用的"出口"：

```cpp
#include <debugging>
#include <cstdio>
#include <cstdlib>

[[noreturn]] void fatal(const char* what) {
    std::fprintf(stderr, "fatal: %s\n", what);
    std::breakpoint_if_debugging();   // 在调试器中运行：停在这里，查看现场
    std::abort();                     // 否则（或调试器选择继续）：照常终止
}
```

C++26 的契约违约处理函数（`handle_contract_violation`，见 [[basic.contract]]）是另一个自然的调用点：自定义的违约处理函数可以先调用 `std::breakpoint_if_debugging()`，再记录违约信息。

!!! warning "实现状况"
    截至本文编写时，**本机 Clang 23 + libc++ 不提供 `<debugging>`**（`#include <debugging>` 报"file not found"；`<version>` 中 `__cpp_lib_debugging` 处于注释状态），上面的例子未能在本机验证。在实现跟进之前，可以用编译器内建函数近似 `breakpoint()`：Clang 的 `__builtin_debugtrap()`、MSVC 的 `__debugbreak()`；`is_debugger_present()` 则需要按平台自行实现（Windows：`IsDebuggerPresent()`；Linux：读取 `/proc/self/status` 的 `TracerPid`；macOS：`sysctl` 查询 `kinfo_proc` 的 `P_TRACED` 标志）。

```cpp run title="debugtrap.cpp" ok
// 编译期可用性检查：本机 libc++ 尚无 <debugging>，退回到 Clang 内建函数
#if __has_include(<debugging>)
#  include <debugging>
inline void debug_break() noexcept { std::breakpoint(); }
#else
inline void debug_break() noexcept { __builtin_debugtrap(); }   // arm64: brk #0xf000；x86: int3
#endif

int main(int argc, char**) {
    if (argc > 99) debug_break();   // 仅演示可用性；无调试器时调用它会以 SIGTRAP 终止
}
```

## 陷阱

!!! pitfall "无条件的 `breakpoint()`"
    没有调试器时，`breakpoint()` 可能直接终止程序（注 1）。留在代码里的 `breakpoint()` 在 CI 或生产环境中就是一个崩溃点。几乎总是应该用 `breakpoint_if_debugging()`。

!!! pitfall "把 `is_debugger_present()` 当作安全机制"
    反调试检测很容易被绕过（调试器可以伪造状态，程序也可以替换这个函数）。它是一个**开发便利**工具，不是安全边界。

!!! pitfall "以为调试器\"继续\"后一切照常"
    注 1 的意图是恢复执行"如同函数未被调用"。但编译器是否把 `breakpoint()` 当作有副作用的不透明调用、周围的代码是否被重排，是实现的事；在高度优化的代码中，在断点处观察到的变量值可能已被优化掉。

## 思考题

!!! question "思考题"
    1. 为什么标准不规定 `breakpoint()` 的任何行为，却仍然值得把它标准化？
    2. 一个程序提供了 `bool std::is_debugger_present() noexcept { return true; }`。调用 `std::breakpoint_if_debugging()` 会发生什么？
    3. 为什么把 `<debugging>` 设计成 freestanding，而 `<stacktrace>` 不是？

<details markdown="1">
<summary>展开查看答案与解析</summary>

1. 因为价值在于**可移植的名字与意图**：每个平台、每个编译器都有自己的断点原语，项目被迫维护一层宏。标准给出一个统一的拼写和一份清晰的意图说明（注 1），实现负责把它映射到平台原语。抽象机里没有调试器，标准也无法规定调试器的行为——只能交给实现定义。
2. `breakpoint_if_debugging()` 等价于 `if (is_debugger_present()) breakpoint();`（¶2），它调用的是被替换后的版本，于是总会调用 `breakpoint()`。若此时没有调试器，按注 1，程序可能异常终止。替换函数要遵守的只有"要求的行为"（¶3：没有前置条件），返回值是否真实反映调试器状态并不受约束。
3. 断点和调试器检测只需要几条指令或一次系统查询，不需要堆分配、不需要文件系统，嵌入式环境恰恰最需要它（经由硬件调试探针）。`<stacktrace>` 需要分配内存、`std::string`、读取调试信息，依赖宿主环境的设施。
</details>

## 小结

!!! summary
    - `<debugging>` 全部 freestanding、`noexcept`，{{c++26}} 引入。
    - `breakpoint()`：语义由实现定义；意图是可恢复地把控制交给调试器；无调试器时可能终止程序。
    - `breakpoint_if_debugging()`：`if (is_debugger_present()) breakpoint();`——日常应使用这个。
    - `is_debugger_present()`：要求的行为是"无前置条件"，默认行为由实现定义（应即时查询）；它是**可替换函数**。
    - 本机 libc++ 尚未提供；可暂用 `__builtin_debugtrap()`/`__debugbreak()` 加平台检测代码近似。
