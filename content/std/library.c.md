---
title: C 标准库
summary: C++ 标准库包含 C 标准库的设施，签名为类型安全做了调整，语义和前置条件（包括 restrict 隐含的不重叠要求）沿用 C 标准；C 函数在常量求值中按 C 附录 F 的语义计算，引发 FE_INEXACT 以外的浮点异常就不是常量表达式。
status: done
papers: P0533R9, P1383R2
related: library, headers, extern.names, extern.types, using.linkage, expr.const, intro.refs
tags: 库, C 兼容, constexpr, 浮点
updated: 2026-10-19
---

!!! tldr
    - C++ 中的 C 库函数为类型安全做了调整：`strchr` 等函数有 `const` 和非 `const` 两个重载，`abs` 和 `<cmath>` 函数对每种算术类型都有重载。
    - 这些函数的行为和前置条件以 C 标准为准，包括 C 签名中 `restrict` 隐含的不重叠要求。这个要求在 C++ 签名上看不到，但违反它同样是 UB。
    - C++26 起 `std::sqrt` 等可以在常量求值中调用。调用如果引发 `FE_INEXACT` 以外的浮点异常（如 `std::sqrt(-1.0)`），就不是常量表达式。

C 头文件怎样组织（`<cstring>` 与 `<string.h>` 的区别）见 [[headers]]；C 库中的名字保留给实现的规则见 [[extern.names]] 与 [[extern.types]]；C 函数具有 C 语言链接还是 C++ 语言链接见 [[using.linkage]]。

## 为类型安全而调整（¶1）

```cpp error
#include <cstring>
int main() {
  const char cs[] = "abc";
  char* p = std::strchr(cs, 'b');   // error: 这里调用的 strchr 返回 const char*，
                                    //        不能用来初始化 char*
  return p != nullptr;
}
```

¶1 C++ 标准库也提供 C 标准库的设施，并做了适当的调整以保证静态类型安全。

最典型的调整是 `const` 正确性。C 的 `strchr` 签名是 `char* strchr(const char* s, int c);`：传进去的是 `const char*`，返回的却是 `char*`，`const` 被悄悄丢掉了。C 没有重载，只能这样写。C++ 的 [cstring.syn] 用两个重载取而代之：

```cpp
const char* strchr(const char* s, int c);
      char* strchr(      char* s, int c);
```

`strpbrk`、`strrchr`、`strstr`、`memchr` 以及 `<cwchar>` 中的对应函数都做了同样的处理。所以上面的程序在 C 中能编译，在 C++ 中是错误的。

另一类调整是为 C++ 的类型补充重载。`<cstdlib>` 的 `abs` 有 `int`、`long`、`long long` 的重载；`<cmath>` 的数学函数对每种浮点类型都有重载，包括扩展浮点类型。C 要用 `fabsf`、`fabsl` 这样的不同名字，或 `<tgmath.h>` 的类型泛型宏，才能做到同样的事。

## 语义沿用 C 标准（¶2）

```cpp ub
#include <cstring>
int main() {
  char buf[8] = "abcdefg";
  std::memcpy(buf + 1, buf, 4);   // UB：源与目标重叠，应当用 memmove
}
```

¶2 许多库函数的语义由 C 标准库规定。本文档给出的签名可能与 C 不同，也可能多出一些重载，但除非另有说明，行为和前置条件都与 C 相同，包括 C 的 `restrict` 限定符所隐含的前置条件。

C++ 没有 `restrict` 关键字，所以 `std::memcpy` 在 C++ 中的签名是 `void* memcpy(void* s1, const void* s2, size_t n);`。在 C 中它的两个形参都是 `restrict` 的，意思是两块内存不得重叠。¶2 把这个要求作为前置条件带进了 C++，违反前置条件是 UB（[[structure.specifications#3.4]]）。这个前置条件只能去 C 标准里找。

本机 Clang 23 用 `-fsanitize=address` 运行上面的程序，AddressSanitizer 报告 `memcpy-param-overlap`。

## C 函数在常量求值中（¶3）

```cpp
#include <cmath>
constexpr double a = std::sqrt(4.0);    // C++26：OK
constexpr double b = std::sqrt(2.0);    // C++26：OK，只引发 FE_INEXACT
constexpr double c = std::sqrt(-1.0);   // error: 引发 FE_INVALID，不是常量表达式
```

C++23 起，`<cmath>` 和 `<cstdlib>` 中的函数逐步成为 `constexpr`：C++23 的 [[P0533R9]] 覆盖了 `fabs`、`floor`、`fmod` 等较简单的函数，C++26 的 [[P1383R2]] 扩展到 `sin`、`sqrt`、`exp` 等。难点在于，数学函数出错时要设置 `errno` 或引发浮点异常，这些都是副作用，常量求值中无法表达。

¶3 如果对 C 标准库函数的一次调用引发了 `FE_INEXACT` 以外的浮点异常，它就是一次[[g:non-constant-library-call|非常量库调用]]（non-constant library call，[[defns.nonconst.libcall]]）。非常量库调用会使包含它的表达式不是核心常量表达式（[[expr.const]]）。

¶3 第二句规定，C 函数调用作为核心常量表达式求值时，语义由 ISO/IEC 9899:2024 附录 F 规定，适用范围限于被调函数形参所用的浮点类型（[[basic.fundamental]]）。附录 F 是 C 标准中按 IEEE 754 规定浮点行为的部分，注 1 说明它规定了何时引发浮点异常，以及传入 NaN 或无穷大时的行为。注 2 给出一个等价的判断方法：在 `math_errhandling & MATH_ERRNO` 为真时，如果调用会设置 `errno`，它就是非常量库调用。

| 调用 | 引发的浮点异常 | 结果 |
|---|---|---|
| `std::sqrt(4.0)` | 无 | 常量表达式，值为 2.0 |
| `std::sqrt(2.0)` | 只有 `FE_INEXACT`（结果经过舍入） | 仍是常量表达式，舍入是浮点运算的常态，不算错误 |
| `std::sqrt(-1.0)` | `FE_INVALID` | 非常量库调用，在要求常量表达式的地方非良构 |
| `std::exp(1000.0)` | `FE_OVERFLOW` | 同上 |

适用范围的限定意味着，如果实现的 `long double` 不是 IEEE 格式，附录 F 对 `long double` 版本的函数就不适用。

!!! warning "编译器支持现状"
    截至写作时，本机 Clang 23 + libc++ 还没有实现 `<cmath>` 的 `constexpr` 化，上面的代码块因此不标判定。`constexpr double a = std::sqrt(4.0);` 报错，连 C++23 就要求的 `std::fabs` 也一样：libc++ 的这些重载没有标 `constexpr`，`double` 版本直接来自 macOS SDK 的 C 声明。

## 实现视角

!!! impl "libc++ 怎样提供 C 函数"
    libc++ 的 `<cstring>` 先包含 C 的 `<string.h>`，再用 `using ::strlen _LIBCPP_USING_IF_EXISTS;` 这样的声明把全局名字引入 `std`，这是 [[headers]] 允许的做法。`_LIBCPP_USING_IF_EXISTS` 展开为 Clang 的 `__attribute__((__using_if_exists__))`：底层 C 库缺少某个函数时，这条 using 声明本身不报错，只有真正使用那个名字时才报错。

    `strchr` 的两个重载来自 libc++ 自带的包装头文件 `<string.h>`。底层 C 库没有提供 C++ 风格的重载时，它用 `__builtin_strchr` 自己定义这两个重载，并标上 `_LIBCPP_PREFERRED_OVERLOAD`，使它们优先于 C 的原始声明。

    C 函数通常由系统 C 库（glibc、Apple libc、MSVC UCRT）实现，常量求值无法调用它们。编译器必须用 `__builtin_sqrt` 这类内建函数在编译期计算，还要正确判断是否引发了浮点异常。这是 C++26 的 `constexpr <cmath>` 实现滞后的主要原因。
