---
title: 错误号
summary: <cerrno> 的内容与 POSIX <errno.h> 相同，errno 必须是宏、每个线程一份；正确读取 errno 的方法，以及它与 std::errc 的对应关系。
status: done
covers: *
related: diagnostics, syserr, intro.multithread, basic.stc.thread
tags: 标准库, errno, POSIX, C 兼容
updated: 2026-10-19
---

!!! tldr
    - `<cerrno>` 与 POSIX 的 `<errno.h>` 内容相同，所以 C++ 要求提供全套 POSIX 错误号宏，而不只是 ISO C 的三个。
    - `errno` 必须是宏，每个线程有自己的一份：一个线程里的失败不会改动另一个线程的 `errno`。
    - 库函数从不把 `errno` 设为 0，成功的调用却可能把它改成非零值。所以要先清零，再调用，按返回值判断是否失败，最后立即读取 `errno`。
    - `std::errc` 的每个枚举项与对应的 `E*` 宏值相同；有的平台上两个宏同值，对应的两个枚举项也就相等。

`errno` 是 C 语言报告错误的机制：库函数失败时把一个正整数写进 `errno`，调用者事后去读。C++ 保留它，主要是为了调用 C 库和 POSIX 接口。

## 一个例子

```cpp run title="errno-strtol.cpp" ok
#include <cerrno>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <thread>

int main() {
    errno = 0;                                   // 1. 先清零
    long v = std::strtol("99999999999999999999", nullptr, 10);
    int e = errno;                               // 2. 立即保存
    if (e == ERANGE)                             // 3. 返回值 LONG_MAX 有歧义，看 errno
        std::printf("ERANGE, v=%ld (%s)\n", v, std::strerror(e));

    std::thread t([] { errno = EDOM; });         // 改的是新线程自己的 errno
    t.join();
    std::printf("%d\n", errno == ERANGE);        // 1：本线程的 errno 不受影响
}
```

本机输出 `ERANGE, v=9223372036854775807 (Result too large)` 和 `1`。

这三步来自 ISO C 对库函数的约定：库函数从不把 `errno` 设为 0；只要函数的说明没有规定它对 `errno` 的用法，函数即使成功也可以把 `errno` 改成非零值。所以：

1. 调用前清零，否则读到的可能是更早某次调用留下的值；
2. 调用后立即保存，因为下一次库调用（包括 `printf`）可能改写它；
3. 只在返回值表明可能失败时才看 `errno`。`strtol` 溢出时返回 `LONG_MAX`，而这也是一个合法的转换结果，只有 `errno` 能区分两者。

## 与 POSIX 对齐、每线程一份 [errno.general]

!!! std
    The contents of the header `<cerrno>` are the same as the POSIX header `<errno.h>`, except that errno shall be defined as a macro.

¶1 这一句有三层意思。

第一，参照的是 POSIX，不是 ISO C。ISO C 的 `<errno.h>` 只要求 `EDOM`、`EILSEQ`、`ERANGE` 三个宏，C++ 则要求 POSIX 的全套 `E*` 宏，在 Windows 这样的非 POSIX 平台上也要提供。注 1 说明这样做是为了与 POSIX 保持一致。

第二，`errno` 必须是宏。C 允许它是宏，也允许是一个有外部链接的标识符，C++ 只允许宏。宏可以展开成对一个函数返回值的解引用，函数返回本线程那份 `errno` 的地址：macOS 上是 `(*__error())`，glibc 上是 `(*__errno_location())`。因此程序不能自己写 `extern int errno;`，也不能写 `std::errno`，宏没有命名空间。

第三，每个线程有一个独立的 `errno` 值。ISO C 规定初始线程的 `errno` 在程序启动时为 0，其他线程的初值是不确定的，所以在新线程里同样要先清零再用。

## 概要 [cerrno.syn]

```cpp
#define errno see below

#define E2BIG see below            // freestanding
#define EACCES see below           // freestanding
// …… 共七十多个 E* 宏，每个都标注 freestanding
#define EXDEV see below            // freestanding
```

¶1 这些宏的含义由 POSIX 定义。

所有 `E*` 宏都标了 freestanding，也就是独立实现（可以不依赖操作系统运行的实现，见 [[intro.compliance]]）也必须提供；`errno` 本身则不是。错误号只是一组整数常量，同样是 freestanding 的 `std::errc`（[[syserr]]）需要用到它们；线程局部的 `errno` 则需要运行时支持。

## 与 `std::errc` 的对应

`<system_error>` 的 `enum class errc` 为几乎每个 `E*` 宏起了一个名字，并且每个枚举项的值与对应宏的值相同（[[system.error.syn#1]]）：`errc::no_such_file_or_directory` 的值就是 `ENOENT`。

POSIX 允许某些错误号取相同的值，例如 `EAGAIN` 与 `EWOULDBLOCK`、`ENOTSUP` 与 `EOPNOTSUPP`。于是对应的两个枚举项在这些平台上相等，写进同一个 `switch` 就会编译失败：

```cpp run title="errc-duplicates.cpp" impl
#include <system_error>

int classify(std::errc e) {
    switch (e) {
    case std::errc::resource_unavailable_try_again: return 1;   // EAGAIN
    case std::errc::operation_would_block:          return 2;   // EWOULDBLOCK
    // macOS、Linux 上两者相等：error: duplicate case value
    default: return 0;
    }
}

int main() {}
```

本机 macOS 上 `EAGAIN` 和 `EWOULDBLOCK` 都是 35，Clang 报 duplicate case value；`ENOTSUP`（45）与 `EOPNOTSUPP`（102）不相等。Linux 上这两对都相等。可移植的代码既不能假设这些枚举项互不相同，也不能假设它们相同。

!!! tip "不依赖 errno 的替代品"
    C++17 的 `std::from_chars` / `to_chars`（[[charconv]]）不使用 `errno`，而是在返回的结构体里带回 `std::errc`；`<filesystem>` 用 `error_code` 出参或 `filesystem_error` 异常。直接调用 C 或 POSIX 接口时，可以立即用 `std::error_code(errno, std::generic_category())` 把错误号保存成值（见 [[syserr]]）。

## 常见误解

!!! pitfall "在检查之前调用了别的函数"
    `if (fopen(...) == nullptr) { log("failed"); if (errno == ENOENT) ... }` 中，`log` 内部的 I/O 可能已经改写了 `errno`。应当先 `int e = errno;` 保存下来。

!!! pitfall "用 `errno != 0` 判断调用是否失败"
    成功的调用也可能把 `errno` 改成非零值。必须先看返回值，只有返回值表明失败，或者像 `strtol` 那样有歧义时，才去看 `errno`。

!!! pitfall "以为 C++ 标准库函数会设置 errno"
    除了从 C 继承的函数，标准库一般不规定对 `errno` 的影响；`<system_error>` 的组件明确规定不改变 `errno`（[[syserr.general#2]]）。

## 思考题

!!! question "思考题 1"
    为什么 C++ 要求 `errno` 必须是宏，而 C 允许它是一个有外部链接的标识符？

<details markdown="1">
<summary>答案</summary>

宏让实现可以统一地提供线程局部的 `errno`：展开成对某个返回本线程地址的函数的调用。它也禁止了程序用 `extern int errno;` 自行声明 `errno`，在线程局部的实现下这样的声明是错的。
</details>

!!! question "思考题 2"
    协程在 `co_await` 之后可能在另一个线程上恢复。在 `co_await` 之前设置、之后读取 `errno` 会怎样？

<details markdown="1">
<summary>答案</summary>

`errno` 是线程局部的，挂起前后的代码可能运行在不同线程上，读到的是不同的 `errno` 对象。挂起前设置的错误号在恢复后可能消失，或者变成另一个线程的值。在协程里应当在挂起点之前把 `errno` 转换成 `error_code` 之类的值保存下来。
</details>
