---
title: 调试
summary: C++26 的 <debugging> 提供三个函数：breakpoint() 把控制交给调试器，breakpoint_if_debugging() 只在有调试器时这样做，is_debugger_present() 检测调试器且可以由程序替换；三者都是 freestanding、noexcept。
status: done
covers: *
since: c++26
papers: P2546R5, P2810R4
related: diagnostics, assertions, basic.contract, dcl.fct.def.replace, structure.specifications, stacktrace
tags: 标准库, 调试器, breakpoint, C++26
updated: 2026-10-19
---

!!! tldr
    - `std::breakpoint()` 的语义由实现定义，意图是暂停程序、把控制交给调试器，调试器继续后程序如同没有调用过它一样往下执行。
    - 没有调试器时，`breakpoint()` 可能让程序异常终止，所以日常应当用 `std::breakpoint_if_debugging()`。
    - `std::is_debugger_present()` 是可替换函数：程序可以提供自己的定义，例如在测试里强制打开调试分支。
    - 整个头文件都是 freestanding 的，三个函数都是 `noexcept`。
    - 本机 libc++ 还没有 `<debugging>`，可以暂用 Clang 的 `__builtin_debugtrap()` 或 MSVC 的 `__debugbreak()`。

{{c++26}} 很多大型项目都有一个自己的 `DEBUG_BREAK()` 宏：Windows 上展开为 `__debugbreak()`，GCC/Clang 上是 `__builtin_debugtrap()`、`raise(SIGTRAP)` 或一段内联汇编。再配一个检测调试器的函数：Windows 有 `IsDebuggerPresent()`，Linux 要读 `/proc/self/status` 的 `TracerPid`，macOS 要用 `sysctl` 查 `P_TRACED` 标志。[[P2546R5]] 把这两件事标准化为 `<debugging>`。

## 一个例子

```cpp
#include <cstdio>
#include <cstdlib>
#include <debugging>

[[noreturn]] void fatal(const char* what) {
    std::fprintf(stderr, "fatal: %s\n", what);
    std::breakpoint_if_debugging();   // 在调试器里运行：停在这里，查看现场
    std::abort();                     // 没有调试器，或调试器选择继续：照常终止
}
```

`<debugging>` 本身不做任何检查，它是给断言、错误处理这类设施用的出口。在调试器里运行时，程序停在出错的现场；没有调试器时什么也不做，继续执行后面的错误处理。C++26 的契约违反处理函数（[[basic.contract]]）也是一个自然的调用点。

本机 Clang 23 + libc++ 不提供 `<debugging>`（`#include` 报 file not found，`<version>` 里的 `__cpp_lib_debugging` 被注释掉），所以这个例子没有判定，也没有在本机验证。

## 概述 [debugging.general]

¶1 本条款描述内省和与程序执行交互的功能。注 1 说，这些功能与一个可能正在跟踪程序执行的程序交互，例如调试器。

抽象机里没有调试器，所以本条款几乎所有规定都由实现定义，规范内容很少。它的价值在于给出一个可移植的名字和一份清楚的意图说明。

```cpp
// all freestanding
namespace std {
  void breakpoint() noexcept;
  void breakpoint_if_debugging() noexcept;
  bool is_debugger_present() noexcept;
}
```

整个头文件都是 freestanding 的。嵌入式开发恰恰最需要停在某处、把控制交给经 JTAG/SWD 探针连接的调试器。

## `breakpoint()` [debugging.utility]

!!! std
    The semantics of this function are implementation-defined.

¶1 规范内容只有这一句：语义由实现定义。意图写在注 1 里：

- 有调试器时，程序暂停，控制交给调试器，直到调试器终止程序，或者让程序如同没有调用过这个函数一样恢复执行；
- 不打算支持以其他方式恢复；
- 没有调试器时，程序可能异常终止。

如同没有调用过一样恢复，是它和 `__builtin_trap()` 的区别。编译器认为 `__builtin_trap()` 不会返回，它之后的代码不可达，调试器即使让程序继续也无法正常恢复。`breakpoint()` 对应的是可以恢复的断点陷阱，在 Clang 里就是 `__builtin_debugtrap()`：本机 arm64 上它编译为 `brk #0xf000`，LLDB 能识别它并让程序在其后继续。

没有调试器时可能终止：在 POSIX 系统上，断点指令产生 `SIGTRAP`，默认动作是终止进程。本机直接运行一个调用 `__builtin_debugtrap()` 的程序，进程以 Trace/BPT trap 结束。

## `breakpoint_if_debugging()`

¶2 效果等价于：

```cpp
if (is_debugger_present()) breakpoint();
```

这是日常最常用的一个：放在断言失败、契约违反、不应到达的分支里，有调试器就停下，没有就继续。

## `is_debugger_present()`

这个函数的规格分成两部分，这是标准库描述可替换函数的写法（[[structure.specifications]]）：

- ¶3 *Required behavior*：没有前置条件。这一条约束任何定义，包括程序自己提供的替换版本。
- ¶4 *Default behavior*：由实现定义。这一条只描述实现提供的那个定义。

注 2 说明意图：实现应当每次都即时查询（不缓存），只在程序确实被调试器跟踪时返回 `true`。Windows 上可以调用 `::IsDebuggerPresent()`；在兼容 Linux Standard Base（ISO/IEC 23360:2021）的系统上，可以检查是否存在跟踪进程，并尽量判断它是不是调试器。不缓存是因为调试器可以在程序运行中途附加或分离。

### 可以替换（¶5）

¶5 规定这个函数是**可替换的**（replaceable，[[g:replaceable-function]]）。和全局 `operator new` 一样，程序可以提供一个签名相同的定义，取代实现的版本（[[dcl.fct.def.replace]]）：它不能是 inline 的，必须附属于全局模块。这一点由 [[P2810R4]] 加入，用途包括：

- 实现的检测方法不适用于某些环境，例如自定义的调试代理、模拟器、嵌入式探针；
- 测试中需要强制打开或关闭有调试器时的分支；
- 某些安全敏感的程序希望禁用这项检测。

```cpp
#include <cstdlib>
#include <debugging>

// 程序提供的替换定义，整个程序只能有一个：由环境变量控制，便于在 CI 里测试调试分支
bool std::is_debugger_present() noexcept {
    return std::getenv("FORCE_DEBUGGER") != nullptr;
}
```

`breakpoint()` 和 `breakpoint_if_debugging()` 不可替换。

## 在实现跟进之前

可以用编译器内建函数近似 `breakpoint()`：Clang 的 `__builtin_debugtrap()`，MSVC 的 `__debugbreak()`。`is_debugger_present()` 需要按平台自己实现：Windows 调用 `IsDebuggerPresent()`，Linux 读 `/proc/self/status` 的 `TracerPid`，macOS 用 `sysctl` 查 `kinfo_proc` 的 `P_TRACED` 标志。

```cpp run title="debugtrap.cpp" ok
// 本机 libc++ 还没有 <debugging>，退回到 Clang 内建函数
#if __has_include(<debugging>)
#  include <debugging>
inline void debug_break() noexcept { std::breakpoint(); }
#else
inline void debug_break() noexcept { __builtin_debugtrap(); }   // arm64: brk #0xf000；x86: int3
#endif

int main(int argc, char**) {
    if (argc > 99) debug_break();   // 只演示能编译；没有调试器时真的调用会以 SIGTRAP 终止
}
```

## 常见误解

!!! pitfall "无条件调用 `breakpoint()`"
    没有调试器时 `breakpoint()` 可能直接终止程序。留在代码里的 `breakpoint()` 到了 CI 或生产环境就是一个崩溃点。几乎总是应该用 `breakpoint_if_debugging()`。

!!! pitfall "把 `is_debugger_present()` 当作安全机制"
    调试器可以伪造状态，程序也可以替换这个函数，反调试检测很容易绕过。它是开发时的便利工具，不是安全边界。

!!! pitfall "以为调试器继续之后一切照常"
    注 1 的意图是如同没有调用过一样恢复执行。但编译器怎样对待周围的代码由实现决定，在高度优化的代码里，在断点处看到的变量可能已经被优化掉了。

## 思考题

!!! question "思考题 1"
    标准不规定 `breakpoint()` 的任何行为，为什么仍然值得把它标准化？

<details markdown="1">
<summary>答案</summary>

价值在于可移植的名字和意图。每个平台、每个编译器都有自己的断点原语，项目只能自己维护一层宏。标准给出统一的写法和清楚的意图说明（注 1），实现负责映射到平台原语。抽象机里没有调试器，标准也无法规定调试器的行为，只能交给实现定义。
</details>

!!! question "思考题 2"
    一个程序提供了 `bool std::is_debugger_present() noexcept { return true; }`。调用 `std::breakpoint_if_debugging()` 会发生什么？

<details markdown="1">
<summary>答案</summary>

`breakpoint_if_debugging()` 等价于 `if (is_debugger_present()) breakpoint();`（[[debugging.utility#2]]），调用的是替换后的版本，所以总会调用 `breakpoint()`。如果此时没有调试器，按注 1，程序可能异常终止。替换函数只需遵守 ¶3 的要求（没有前置条件），返回值是否真实反映调试器状态不受约束。
</details>

!!! question "思考题 3"
    为什么 `<debugging>` 是 freestanding 的，而 `<stacktrace>` 不是？

<details markdown="1">
<summary>答案</summary>

设置断点和检测调试器只需要几条指令或一次系统查询，不需要堆分配和文件系统，而嵌入式环境经由硬件调试探针最需要它。`<stacktrace>`（[[stacktrace]]）要分配内存、返回 `std::string`、读取调试信息，依赖宿主环境的设施。
</details>
