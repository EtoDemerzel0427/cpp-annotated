---
title: 错误号
summary: <cerrno>：内容与 POSIX <errno.h> 相同，但 errno 必须是宏、每个线程一份；全套 POSIX E* 宏都在 C++ 中可用且为 freestanding；使用 errno 的正确姿势（先清零、立即读取），以及它与 <system_error> 中 errc 的对应关系和"同值枚举项"陷阱。
status: done
covers: *
related: diagnostics, syserr, intro.multithread, basic.stc.thread
tags: 标准库, errno, POSIX, C 兼容
updated: 2026-10-18
---

`errno` 是 C 语言报告错误的原始机制：失败的库函数把一个正整数写进一个全局的"错误号"，调用者事后去读。C++ 继承了它，主要是为了与 C 库和 POSIX 接口互操作。本节只有两小段规范文字，但每一句都有实际分量。

## 与 POSIX 对齐（[errno.general]）

!!! std
    The contents of the header `<cerrno>` are the same as the POSIX header `<errno.h>`, except that errno shall be defined as a macro.

    `<cerrno>` 的内容与 **POSIX** 头文件 `<errno.h>` 相同，只是 `errno` 必须被定义为**宏**。

几个要点：

- **参照的是 POSIX，不是 ISO C**。ISO C 的 `<errno.h>` 只要求 `EDOM`、`EILSEQ`、`ERANGE` 三个宏；C++ 则要求 POSIX 定义的全套 `E*` 宏（[cerrno.syn] 列出了七十多个，从 `E2BIG` 到 `EXDEV`），即使在非 POSIX 平台（如 Windows）上也要提供。注 1 说明了意图：与 POSIX 标准保持紧密一致。
- **`errno` 必须是宏**。C 允许 `errno` 是宏或者具有外部链接的标识符；C++ 只允许宏。这让实现可以把它定义成一个函数调用的解引用，从而实现线程局部存储——macOS 上它是 `(*__error())`，glibc 上是 `(*__errno_location())`。程序因此不能写 `extern int errno;`，也不能写 `std::errno`（宏没有命名空间）。
- **每个线程一份**：¶1 最后一句——为每个线程提供一个独立的 `errno` 值。一个线程中的失败不会污染另一个线程的 `errno`。（ISO C 规定初始线程的 `errno` 在程序启动时为 0，其他线程中 `errno` 的初始值是不确定的——所以在新线程里同样要先清零再使用。）

## 概要（[cerrno.syn]）

```cpp
#define errno see below

#define E2BIG see below            // freestanding
#define EACCES see below           // freestanding
// ……共七十余个 E* 宏，每个都标注 freestanding ……
#define EXDEV see below            // freestanding
```

¶1：这些宏的含义由 POSIX 标准定义（另见 ISO C 7.5）。

注意 freestanding 的标注：所有 `E*` 宏在独立实现中也必须提供，但 **`errno` 本身不是** freestanding——独立实现不一定有"线程局部的错误号"这种运行时设施，而错误码的**数值**则可以作为纯粹的常量被（例如）`<system_error>` 中同为 freestanding 的 `errc` 枚举使用。

## 正确的使用方式

C 库函数的约定（来自 ISO C）是：库函数**可以**在没有出错时把 `errno` 设为非零值，但**永远不会**把它设为 0。所以正确的模式是：

1. 调用前把 `errno` 清零；
2. 调用后**立即**检查（任何其他库调用都可能改变它，包括 `printf`）；
3. 只有当函数的返回值也表明可能出错时，`errno` 才有意义。

```cpp run title="errno-strtol.cpp" ok
#include <cerrno>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <thread>

int main() {
    errno = 0;
    long v = std::strtol("99999999999999999999", nullptr, 10);
    if (errno == ERANGE)                         // 先保存/检查，再调用其他函数
        std::printf("ERANGE, v=%ld (%s)\n", v, std::strerror(errno));

    errno = 0;
    std::thread t([] {
        errno = 0;
        (void)std::strtol("99999999999999999999", nullptr, 10);   // 只设置本线程的 errno
    });
    t.join();
    std::printf("errno in main after join = %d\n", errno);      // 0：线程局部，不受影响
}
```

!!! tip "现代替代品"
    C++17 的 `std::from_chars`/`to_chars`（[[charconv]]）完全不使用 `errno`，而是在返回的结构体中带回 `std::errc`；`<filesystem>` 用 `error_code` 出参或 `filesystem_error` 异常。新代码中需要 `errno` 的地方，基本只剩直接调用 C/POSIX 接口的场合——此时可以用 `std::error_code(errno, std::generic_category())` 把它立即转换成值类型保存下来（见 [[syserr]]）。

## 与 `errc` 的对应

`<system_error>` 中的 `enum class errc`（[[system.error.syn]]）为几乎每个 `E*` 宏提供了一个有名字的枚举项，且 [[system.error.syn]] ¶1 规定**每个枚举项的值与对应宏的值相同**：`errc::no_such_file_or_directory` 的值就是 `ENOENT`。

这带来一个平台相关的坑：POSIX 允许某些错误号取相同的值（例如 `EAGAIN` 与 `EWOULDBLOCK`，`ENOTSUP` 与 `EOPNOTSUPP`），于是对应的两个 `errc` 枚举项在某些平台上相等：

```cpp run title="errc-duplicates.cpp" error
#include <system_error>

int classify(std::errc e) {
    switch (e) {
    case std::errc::resource_unavailable_try_again: return 1;   // EAGAIN
    case std::errc::operation_would_block:          return 2;   // EWOULDBLOCK
    // macOS/Linux 上二者都等于 35/11：error: duplicate case value
    default: return 0;
    }
}

int main() {}
```

在本机 macOS 上，`EAGAIN == EWOULDBLOCK == 35`，而 `ENOTSUP`（45）与 `EOPNOTSUPP`（102）不相等；Linux 上二者都相等。可移植代码不能假设这些枚举项互不相同，也不能假设它们相同。

## 陷阱

!!! pitfall "在检查前调用了别的函数"
    `if (fopen(...) == nullptr) { log("failed"); if (errno == ENOENT) ... }`——`log` 内部的 I/O 可能已经改写了 `errno`。先 `int e = errno;` 保存。

!!! pitfall "成功也可能改变 errno"
    不能用"`errno != 0`"来判断一个调用是否失败。必须先看返回值，只有在返回值表明失败（或像 `strtol` 那样返回值有歧义）时才看 `errno`。

!!! pitfall "C++ 标准库函数与 errno"
    除了从 C 继承的函数，C++ 标准库组件一般不规定对 `errno` 的影响；`<system_error>` 明确规定不改变 `errno`（[[syserr.general]] ¶2）。不要假设 `std::` 中的 C++ 函数会设置 `errno`。

## 思考题

!!! question "思考题"
    1. 为什么 C++ 要求 `errno` 必须是宏，而 C 允许它是一个外部链接的标识符？
    2. 协程在 `co_await` 之后可能在另一个线程上恢复执行。在 `co_await` 前后读取 `errno` 会发生什么？

<details markdown="1">
<summary>展开查看答案与解析</summary>

1. 宏让实现有统一的方式提供线程局部的 `errno`（展开为对某个返回线程局部地址的函数的调用），并且禁止程序以 `extern int errno;` 的方式自行声明它——那样的声明在线程局部实现下是错误的。C++11 起标准要求每线程一个 `errno`，宏是实现这一点最可移植的方式。
2. `errno` 是线程局部的。`co_await` 之前和之后的代码可能运行在不同线程上，于是读到的是**不同**的 `errno` 对象：挂起前设置的错误号在恢复后可能"消失"或被替换成另一个线程的值。在协程中，应当在挂起点之前把 `errno` 转换为 `error_code` 等值类型保存下来。
</details>

## 小结

!!! summary
    - `<cerrno>` = POSIX `<errno.h>`，全套 `E*` 宏都有，且都是 freestanding；`errno` 本身不是 freestanding。
    - `errno` 必须是宏，每线程一份（非初始线程中的初值不确定，使用前先清零）。
    - 使用模式：先清零，调用，按返回值判断是否失败，立即读取 `errno`。
    - `errc` 枚举项的值等于对应的 `E*` 宏；某些枚举项在特定平台上同值，`switch` 中同时列出会编译失败。
