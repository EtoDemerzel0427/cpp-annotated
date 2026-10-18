---
title: C 标准库
summary: C++ 标准库吸收了 C 标准库的设施并"适当调整以保证静态类型安全"；C 函数的语义与前置条件（含 restrict 隐含的）沿用 C 标准；C 函数在常量求值中按 C 附录 F 的语义进行，引发 FE_INEXACT 以外的浮点异常即为非常量库调用。
status: done
papers: P0533R9, P1383R2
related: library, headers, extern.names, extern.types, using.linkage, expr.const, intro.refs
tags: 库, C 兼容, constexpr, 浮点
updated: 2026-10-18
---

C++ 从诞生起就把 C 标准库当作自己的一部分：`<cstdio>`、`<cstring>`、`<cmath>`…… 本节 [library.c] 只有三段，但回答了三个实际问题：

1. C++ 里的 `strchr` 和 C 里的 `strchr` 是同一个函数吗？（不完全是——签名被调整过。）
2. C 函数的语义在哪里规定？（在 C 标准里，C++ 只是引用。）
3. `constexpr double r = std::sqrt(2.0);` 合法吗？`std::sqrt(-1.0)` 呢？（C++26 起前者合法，后者不是常量表达式。）

C 头文件的组织（`<cname>` 与 `<name.h>` 的区别）见 [[headers]]；C 名字的保留规则见 [[extern.names]] 与 [[extern.types]]；C 函数是 `extern "C"` 还是 `extern "C++"` 见 [[using.linkage]]。

## 为类型安全而调整（¶1）

¶1 C++ 标准库也提供 C 标准库的设施，并**适当调整以保证静态类型安全**。

最典型的调整是**常量正确性**。C 的 `strchr` 签名是 `char* strchr(const char* s, int c);`——传入 `const char*`，返回 `char*`，悄悄丢掉了 `const`。这是 C 没有重载的无奈之举。C++ 用两个重载取而代之（[cstring.syn]，synopsis 中注明 "see [library.c]"）：

```cpp
const char* strchr(const char* s, int c);
      char* strchr(      char* s, int c);
```

`strpbrk`、`strrchr`、`strstr`、`memchr`，以及 `<cwchar>` 中的对应函数，都做了同样的处理。

```cpp error
#include <cstring>
int main() {
  const char cs[] = "abc";
  char* p = std::strchr(cs, 'b');   // error: strchr(const char*, int) 返回 const char*，
                                    //        不能初始化 char*
  return p != nullptr;
}
```

另一类调整是**为 C++ 的类型补充重载**：`<cstdlib>` 的 `abs` 有 `int`、`long`、`long long` 重载，`<cmath>` 中的数学函数对每种浮点类型（包括扩展浮点类型）都有重载（C 用 `fabsf`/`fabsl` 或 `<tgmath.h>` 的类型泛型宏来做同样的事）。

## 语义沿用 C 标准（¶2）

¶2 许多库函数的描述依赖 C 标准库来规定其语义。有些情况下，本文档中规定的**签名**可能与 C 标准库中的不同，还可能声明额外的重载，但**行为与前置条件**（包括 C 的 `restrict` 限定符所隐含的前置条件）都相同，除非另有说明。

这里的"`restrict` 隐含的前置条件"值得注意。C++ 没有 `restrict` 关键字，所以 `std::memcpy` 在 C++ 中的签名是 `void* memcpy(void* s1, const void* s2, size_t n);`——但 C 中它的形参是 `restrict` 的，这意味着两块内存**不得重叠**。¶2 明确把这一点作为前置条件带进了 C++：

```cpp ub
#include <cstring>
int main() {
  char buf[8] = "abcdefg";
  std::memcpy(buf + 1, buf, 4);   // UB：源与目标重叠，违反 restrict 隐含的前置条件
                                  // （应使用 memmove）
}
```

违反前置条件是 UB（[[structure.specifications#3.4]]），而这个前置条件在 C++ 的签名上是看不到的——只能去 C 标准里找。

## C 函数在常量求值中（¶3）

¶3 若对 C 标准库函数的调用引发了 `FE_INEXACT` 以外的浮点异常，它就是一个[[g:non-constant-library-call|**非常量库调用**]]（non-constant library call，[[defns.nonconst.libcall]]）。作为核心常量表达式求值的 C 标准库函数调用，其语义是 ISO/IEC 9899:2024 附录 F 中规定的语义，在适用于被调函数形参类型的浮点类型（[[basic.fundamental]]）的范围内适用。

- Note 1：附录 F 规定了在何种条件下引发浮点异常，以及向函数传入 NaN 和/或无穷大时的行为。
- Note 2：等价地，若在 `math_errhandling & MATH_ERRNO` 为真时调用设置了 `errno`，该调用就是非常量库调用。

**非常量库调用**的定义（[intro.defs]）是："库函数的一次调用，它作为求值某个表达式 E 的一部分，使 E 不是核心常量表达式"。[[expr.const]] 把"非常量库调用"列入了使表达式不成为核心常量表达式的清单。

这一段是为 C++23 起 `<cmath>` / `<cstdlib>` 的 `constexpr` 化服务的（C++23 的 [[P0533R9]] 让 `fabs`、`floor`、`fmod` 等"简单"函数成为 `constexpr`；C++26 的 [[P1383R2]] 扩展到 `sin`、`sqrt`、`exp` 等）。问题是：数学函数在出错时要设置 `errno` 或引发浮点异常——这些是**副作用**，常量求值中无法表达。¶3 的解决办法是：

| 调用 | 浮点异常 | 结果 |
|---|---|---|
| `std::sqrt(4.0)` | 无 | 常量表达式，值为 2.0 |
| `std::sqrt(2.0)` | 只有 `FE_INEXACT`（结果被舍入） | 仍是常量表达式——舍入是浮点运算的常态，不算错误 |
| `std::sqrt(-1.0)` | `FE_INVALID` | **非常量库调用**：在要求常量表达式的上下文中非良构 |
| `std::exp(1000.0)` | `FE_OVERFLOW` | 同上 |

```cpp
#include <cmath>
constexpr double a = std::sqrt(4.0);    // C++26：OK
constexpr double b = std::sqrt(2.0);    // C++26：OK，只引发 FE_INEXACT
constexpr double c = std::sqrt(-1.0);   // error: FE_INVALID → 非常量库调用，不是常量表达式
```

!!! warning "编译器支持现状"
    标准规定 `std::sqrt`、`std::sin` 等在 C++26 中是 `constexpr` 的，但截至本文编写时，本机 Clang 23 + libc++ 仍未实现：`constexpr double a = std::sqrt(4.0);` 报错 "non-constexpr function 'sqrt' cannot be used in a constant expression"，连 C++23 要求的 `std::abs`、`std::fabs` 也同样如此（libc++ 的 `__math/abs.h` 中这些重载未标 `constexpr`，`double` 版本则直接来自 macOS SDK 的 C 声明）。上面的代码块因此不标判定。

"附录 F 的语义"意味着常量求值中的浮点运算按 IEEE 754 规则进行：NaN 与无穷大的传播、有符号零等都按附录 F 处理。但 ¶3 只说"在适用于形参类型的浮点类型的范围内"——若实现的 `long double` 不是 IEEE 格式，附录 F 对它就不适用。

## 实现视角

- 在 libc++ 中，`<cstring>` 在包含 C 的 `<string.h>` 后，用 `using ::strlen _LIBCPP_USING_IF_EXISTS;` 把全局名字引入 `std`（这正是 [[headers#5]] 允许的"先在全局声明再注入 `std`"）。`_LIBCPP_USING_IF_EXISTS` 展开为 Clang 的 `__attribute__((__using_if_exists__))`，使得底层 C 库缺少某个函数时，这个 using 声明不会导致编译失败，只有真正使用时才报错。
- `strchr` 的常量正确重载：libc++ 自带一个包装用的 `<string.h>`，在底层 C 库没有提供 C++ 风格重载时，用 `__builtin_strchr` 自行定义 `const char* strchr(const char*, int)` 与 `char* strchr(char*, int)` 两个重载（标有 `_LIBCPP_PREFERRED_OVERLOAD`，使其优先于 C 的原始声明）；`<cstring>` 再 `using ::strchr` 引入 `std`。
- 由于 C 函数的实现通常来自系统 C 库（glibc、Apple libc、MSVC UCRT），常量求值不能调用它们——编译器必须用**内建函数**（`__builtin_sqrt` 等）在编译期计算，而且必须正确地判定是否引发了浮点异常。这正是 C++26 的 `constexpr <cmath>` 在实现上滞后的原因。

## 小结

!!! summary "核心要点"
    - C++ 的 C 库函数为类型安全做了调整：常量正确的重载对（`strchr` 等）、按类型补充的重载（`abs`、`<cmath>`）。
    - 语义与前置条件以 C 标准为准，包括 `restrict` 隐含的"不重叠"前置条件——C++ 签名上看不到它。
    - 常量求值中的 C 函数按 C 附录 F 的语义；引发 `FE_INEXACT` 以外的浮点异常（等价地：设置 `errno`）即为非常量库调用，使表达式不是核心常量表达式。
