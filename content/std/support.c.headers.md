---
title: C 头文件
summary: <stdio.h> 这类 <name.h> 头文件在 C++ 中只为与 C 互操作而存在；它们把名字放进全局命名空间，<cname> 则保证名字在 std 中；<complex.h>、<tgmath.h>、<iso646.h> 等几个有特殊规定。
status: done
covers: *
papers: P2340R1
related: headers, library.c, cstddef.syn, cstdlib.syn, lex.key, dcl.link, cpp.predefined, stdatomic.h.syn, stdbit.h.syn, stdckdint.h.syn
tags: 标准库, C 兼容, 头文件
updated: 2026-10-19
---

!!! tldr
    - `<stdio.h>` 这类 `<name.h>` 头文件只为与 C 互操作而提供；不需要同时是合法 C 的代码应当用 `<cstdio>` 这类 `<cname>`。
    - `<cname>` 保证名字在 `std` 中，`<name.h>` 保证名字在全局命名空间中；另一边都只是可能。
    - C++ 特有的 `std::byte`、`std::lerp` 和数学特殊函数，不会被 `<name.h>` 放进全局。
    - `<iso646.h>` 是空的；`<complex.h>`、`<tgmath.h>` 只是包含对应的 C++ 头文件，不往全局放名字。

C 标准库的每个头文件 `<name.h>`，C++ 都提供一个对应的 `<cname>`，例如 `<stdio.h>` 对应 `<cstdio>`（[[headers]]、[[library.c]]）。本节规定原来的 `<name.h>` 形式在 C++ 中是什么意思。

## 只为互操作 [support.c.headers.general]

¶1 为了与 C 标准库兼容，C++ 标准库提供表 47 列出的 **C 头文件**（[[g:c-headers]]）：`<assert.h>`、`<complex.h>`、`<ctype.h>`、`<errno.h>`、`<fenv.h>`、`<float.h>`、`<inttypes.h>`、`<iso646.h>`、`<limits.h>`、`<locale.h>`、`<math.h>`、`<setjmp.h>`、`<signal.h>`、`<stdalign.h>`、`<stdarg.h>`、`<stdatomic.h>`、`<stdbit.h>`、`<stdbool.h>`、`<stdckdint.h>`、`<stddef.h>`、`<stdint.h>`、`<stdio.h>`、`<stdlib.h>`、`<string.h>`、`<tgmath.h>`、`<time.h>`、`<uchar.h>`、`<wchar.h>`、`<wctype.h>`。

!!! std
    The intended use of these headers is for interoperability only.

这些头文件的用途仅限于互操作：一个 C++ 源文件如果也要能作为 C 编译，就需要包含它们。不打算同时作为合法 C 的源文件，不应当使用任何 C 头文件。

例 1 是一个既是合法 C++ 也是合法 C 的头文件：

```cpp
#include <uchar.h>      // C 需要它来得到 char8_t；C++ 中 char8_t 是关键字
#include <stddef.h>     // size_t
#ifdef __cplusplus      // 见 [cpp.predefined]
extern "C"              // 见 [dcl.link]
#endif
void f(char8_t s[], size_t n);
```

作为 C++ 编译时，它声明了一个具有 C 语言链接的函数；作为 C 编译时，它只是一个普通的函数原型。注 1 说明，纯 C++ 代码不需要 C 头文件：它们要么没有效果（如 `<stdbool.h>`、`<stdalign.h>`），要么对应的 `<cname>` 提供同样的设施，而且保证定义在 `std` 中。

!!! history
    C++98 到 C++20，`<name.h>` 形式都列在附录 D 中，处于弃用状态。C++23 的 [[P2340R1]] 把它们移回正文的本节，取消了弃用，同时写明它们只为互操作而存在。这是承认现实：与 C 共享的头文件必须用 `<name.h>`，这些头文件实际上也永远不会被删除。

## 名字放在哪里 [support.c.headers.other]

```cpp run title="c-headers.cpp" ok
#include <stdlib.h>
#include <cstddef>
#include <stddef.h>

int main() {
  void* p = malloc(4);   // <stdlib.h>：全局名字有保证
  free(p);
  std::size_t n = 1;     // <cstddef>：std 中的名字有保证
  ::size_t m = 2;        // <stddef.h>：全局名字有保证
  return n + m == 3 ? 0 : 1;
}
```

¶1 除了几个特殊的头文件（见下一节），每个 `<name.h>` 的行为，都如同把对应的 `<cname>` 放进 `std` 的每个名字也放进全局命名空间。这些名字是先声明在 `std` 中、再用 using 声明引入全局，还是反过来，是未指定的。

有四类名字除外，它们是 C++ 特有的，`<name.h>` 不把它们放进全局：

- 数学特殊函数，例如 `std::assoc_laguerre`（[[sf.cmath]]）；
- `std::lerp` 的重载（[[c.math.lerp]]）；
- `std::byte` 的声明（[[cstddef.syn]]）；
- `std::byte` 的运算函数（[[support.types.byteops]]）。

```cpp error
#include <stddef.h>
#include <cstddef>
::byte b{};   // error: <stddef.h> 不把 std::byte 放进全局
```

¶2 例 1 总结了两个方向的保证：

| 头文件 | 保证 | 可能 |
|---|---|---|
| `<cstdlib>` | 名字在 `std` 中 | 也在全局 |
| `<stdlib.h>` | 名字在全局 | 也在 `std` 中 |

所以只包含 `<cstdlib>` 却写 `::malloc`，或者只包含 `<stdlib.h>` 却写 `std::malloc`，都不可移植。它们在主流实现上都能编译，因为 libc++ 和 libstdc++ 的 `<cname>` 都是通过包含 `<name.h>` 实现的，但标准不保证。

## 几个特殊的头文件

| 头文件 | C++ 中的规定 | 说明 |
|---|---|---|
| `<complex.h>`（[complex.h.syn]） | 如同只包含 `<complex>`；`<complex>` 放进 `std` 的名字不会出现在全局 | C 的 `_Complex` 和 C++ 的 `std::complex<T>` 是不同的机制 |
| `<tgmath.h>`（[tgmath.h.syn]） | 如同包含 `<cmath>` 和 `<complex>`；名字不放进全局 | C 用类型泛型宏实现的功能，`<cmath>` 和 `<complex>` 已经用足够多的重载提供了 |
| `<iso646.h>`（[iso646.h.syn]） | 空的 | `and`、`or`、`not`、`xor`、`bitand` 等在 C++ 中是关键字（[[lex.key]]） |
| `<stdalign.h>`（[stdalign.h.syn]） | 内容与 C 的 `<stdalign.h>` 相同 | C23 中 `alignas`、`alignof` 已经是关键字，这个头文件几乎没有内容了 |
| `<stdbool.h>`（[stdbool.h.syn]） | 内容与 C 的 `<stdbool.h>` 相同 | C23 和 C++ 中 `bool`、`true`、`false` 都是关键字 |
| `<stdatomic.h>`、`<stdbit.h>`、`<stdckdint.h>` | 由各自的条款规定 | 见 [[stdatomic.h.syn]]、[[stdbit.h.syn]]、[[stdckdint.h.syn]] |
