---
title: C 头文件
summary: <stdio.h> 这类 <name.h> 头文件在 C++ 中的地位——仅为与 C 互操作而存在；与 <cname> 的命名空间差异；<complex.h>、<tgmath.h>、<iso646.h>、<stdalign.h>、<stdbool.h> 的特殊处理
status: done
covers: *
papers: P2340R1
related: headers, library.c, cstddef.syn, cstdlib.syn, lex.key, dcl.link, cpp.predefined, stdatomic.h.syn, stdbit.h.syn, stdckdint.h.syn
tags: 标准库, C 兼容, 头文件
updated: 2026-10-18
---

C++ 标准库对 C 标准库的每个头文件 `<name.h>` 都提供了一个 `<cname>` 版本（`<stdio.h>` → `<cstdio>`），见 [[headers]]、[[library.c]]。本节规定的是**原始的 `<name.h>` 形式**在 C++ 中的含义。

## 定位：只为互操作（[support.c.headers.general]）

¶1：为了与 C 标准库兼容，C++ 标准库提供表 47 所列的 **C 头文件**（[[g:c-headers]]）：`<assert.h>`、`<complex.h>`、`<ctype.h>`、`<errno.h>`、`<fenv.h>`、`<float.h>`、`<inttypes.h>`、`<iso646.h>`、`<limits.h>`、`<locale.h>`、`<math.h>`、`<setjmp.h>`、`<signal.h>`、`<stdalign.h>`、`<stdarg.h>`、`<stdatomic.h>`、`<stdbit.h>`、`<stdbool.h>`、`<stdckdint.h>`、`<stddef.h>`、`<stdint.h>`、`<stdio.h>`、`<stdlib.h>`、`<string.h>`、`<tgmath.h>`、`<time.h>`、`<uchar.h>`、`<wchar.h>`、`<wctype.h>`。

!!! std
    The intended use of these headers is for interoperability only. ... Source files that are not intended to also be valid C should not use any of the C headers.

    这些头文件的预期用途**仅限于互操作**。……不打算同时作为合法 C 代码的源文件，**不应**使用任何 C 头文件。

注 1：C 头文件要么**没有效果**（如 `<stdbool.h>`、`<stdalign.h>`），要么对应的 `<cname>` 提供同样的设施，并且**保证**把它们定义在命名空间 `std` 中。例 1 展示了一个既是合法 C++ 又是合法 C 的头文件：用 `#ifdef __cplusplus`（[[cpp.predefined]]）包住 `extern "C"`（[[dcl.link]]），并包含 `<uchar.h>`（C 需要它来获得 `char8_t`，C++ 中 `char8_t` 是关键字）。

!!! history "从“弃用”到“仅供互操作”"
    C++98 到 C++20 期间，`<name.h>` 形式被列在附录 D 中，处于**弃用**状态。C++23 的 [[P2340R1]] 把它们移回正文的本节，取消弃用，同时把定位明确为"仅供互操作"——承认了现实：大量与 C 共享的头文件必须使用 `<name.h>`，而且 C 头文件永远不会真的被删除。

## 名字放在哪里（[support.c.headers.other]）

¶1：除 `<complex.h>`、`<iso646.h>`、`<stdalign.h>`、`<stdatomic.h>`、`<stdbit.h>`、`<stdbool.h>`、`<stdckdint.h>`、`<tgmath.h>` 之外，每个 `<name.h>` 头文件的行为都**如同**把对应 `<cname>` 放进命名空间 `std` 的每个名字放到**全局命名空间**中——但以下内容**除外**：

- 数学特殊函数（[[sf.cmath]]，如 `std::assoc_laguerre`）；
- `std::lerp` 的重载（[[c.math.lerp]]）；
- `std::byte` 的声明（[[cstddef.syn]]）及其运算（[[support.types.byteops]]）。

这些都是 C++ 特有、C 中不存在的东西，`<math.h>`、`<stddef.h>` 不把它们放进全局。这些名字是先声明在 `std` 中再用 *using-declaration* 注入全局，还是反过来，是**未指明的**。

¶2 例 1 总结了两个方向的保证：

| 头文件 | 保证 | 可能 |
|---|---|---|
| `<cstdlib>` | 名字在 `std::` 中 | 也在全局 |
| `<stdlib.h>` | 名字在全局 | 也在 `std::` 中 |

所以只包含 `<cstdlib>` 却写 `::malloc`，或者只包含 `<stdlib.h>` 却写 `std::malloc`，都是**不可移植**的——它们在主流实现上都能编译（libc++ 和 libstdc++ 的 `<cname>` 都通过包含 `<name.h>` 实现），但标准不保证。

```cpp run title="c-headers.cpp" ok
#include <stdlib.h>
#include <cstddef>
#include <stddef.h>

int main() {
    void* p = malloc(4);            // <stdlib.h>：全局名字有保证
    free(p);
    std::size_t n = 1;              // <cstddef>：std:: 有保证
    ::size_t m = 2;                 // <stddef.h>：全局有保证
    // ::byte b{};                  // error: <stddef.h> 不把 std::byte 放进全局（¶1 的例外）
    return n + m == 3 ? 0 : 1;
}
```

## 特殊的几个头文件

| 头文件 | C++ 中的规定 | 原因 |
|---|---|---|
| `<complex.h>`（[complex.h.syn]） | 如同只包含 `<complex>`；注 1：`<complex>` 在 `std` 中引入的名字**不**放进全局 | C 的 `_Complex` 与 C++ 的 `std::complex<T>` 是不同的机制 |
| `<tgmath.h>`（[tgmath.h.syn]） | 如同包含 `<cmath>` 和 `<complex>`；名字不放进全局 | 注 1：C 的类型泛型宏，在 C++ 中已由 `<cmath>` 与 `<complex>` 的"足够多"的重载提供 |
| `<iso646.h>`（[iso646.h.syn]） | **空的** | 注 1：`and`、`or`、`not`、`xor`、`bitand` 等在 C++ 中是关键字（[[lex.key]]） |
| `<stdalign.h>`（[stdalign.h.syn]） | 内容与 C 的 `<stdalign.h>` 相同 | C23 中 `alignas`/`alignof` 已是关键字，该头文件几乎不再提供实质内容 |
| `<stdbool.h>`（[stdbool.h.syn]） | 内容与 C 的 `<stdbool.h>` 相同 | C23 中 `bool`/`true`/`false` 已是关键字，该头文件几乎不再提供实质内容；在 C++ 中它们本来就是关键字 |
| `<stdatomic.h>`、`<stdbit.h>`、`<stdckdint.h>` | 由各自的条款规定（[[stdatomic.h.syn]]、[[stdbit.h.syn]]、[[stdckdint.h.syn]]） | 它们提供的是 C 风格的宏或函数与 C++ 设施之间的桥接，不能简单地"放进全局" |

## 小结

!!! summary
    - `<name.h>` 头文件仅供与 C 互操作；纯 C++ 代码应使用 `<cname>`。
    - `<cname>` 保证名字在 `std::`，`<name.h>` 保证名字在全局；另一边都只是"可能"。
    - C++ 特有的东西（`std::byte`、`std::lerp`、数学特殊函数）不进入全局。
    - `<iso646.h>` 为空；`<complex.h>`、`<tgmath.h>` 只是包含对应的 C++ 头文件，不导出全局名字。
    - C++23 起这些头文件不再被弃用。
