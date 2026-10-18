---
title: 算术类型
summary: <cstdint> 的定宽、最小宽度、最快整数类型与 intmax_t/intptr_t，以及 <stdfloat> 的可选扩展浮点类型别名 float16_t…bfloat16_t
status: done
covers: *
related: basic.fundamental, basic.extended.fp, cpp.predefined, support.limits, support.types, conv.rank
tags: 标准库, cstdint, stdfloat, 定宽整数
updated: 2026-10-18
---

[[basic.fundamental]] 只规定了标准整数类型的**最小宽度**（`int` 至少 16 位，`long` 至少 32 位……），具体宽度是由实现定义的。如果你需要"恰好 32 位"或"至少 64 位"的整数，就需要 `<cstdint>`；如果你需要 IEEE 754 的 `binary16`，就需要 `<stdfloat>`。本节只有两个头文件概要，但其中有几处 C++ 与 C 的微妙差别。

## `<cstdint>`（[cstdint.syn]）

¶1：`<cstdint>` 提供具有指定宽度的整数类型，以及给出整数类型极限的宏。整个头文件是 freestanding 的。

类型分为五族（*N* 为宽度）：

| 族 | 含义 | 是否必需 |
|---|---|---|
| `intN_t` / `uintN_t` | **恰好** *N* 位、无填充位（有符号的为二进制补码） | 可选（见 ¶3） |
| `int_leastN_t` / `uint_leastN_t` | 至少 *N* 位的**最窄**类型 | *N* = 8、16、32、64 时必需 |
| `int_fastN_t` / `uint_fastN_t` | 至少 *N* 位的"通常最快"的类型 | *N* = 8、16、32、64 时必需 |
| `intmax_t` / `uintmax_t` | 最宽的整数类型（见下文例外） | 必需 |
| `intptr_t` / `uintptr_t` | 能与 `void*` 互相往返转换的整数类型 | C++ 中**总是定义**（¶2） |

宏有 `INTN_MIN`/`INTN_MAX`/`UINTN_MAX`、对应的 `*_WIDTH`（C23）、`INTMAX_MIN` 等，以及 `PTRDIFF_MAX`、`SIZE_MAX`、`SIG_ATOMIC_MIN` 等，和常量构造宏 `INTN_C(v)`/`UINTN_C(v)`/`INTMAX_C(v)`。

### 与 C 的差别（¶2）

!!! std
    The header defines all types and macros the same as the C standard library header `<stdint.h>`, except that the types `intptr_t` and `uintptr_t` and the macros `INTPTR_MIN`, `INTPTR_MAX`, and `UINTPTR_MAX` are always defined.

    该头文件定义的所有类型和宏与 C 的 `<stdint.h>` 相同，但 `intptr_t`、`uintptr_t` 及宏 `INTPTR_MIN`、`INTPTR_MAX`、`UINTPTR_MAX` 总是定义。

两处差别：

1. **`intptr_t`/`uintptr_t` 在 C++ 中是必需的**，在 C 中是可选的。这和 [[expr.reinterpret.cast]] 呼应：C++ 规定指针可以转换为"足够大"的整数类型再转回来得到原值，而 `intptr_t` 就是那个保证存在的"足够大的类型"。
2. **`intmax_t`/`uintmax_t` 不必能表示比 `long long`/`unsigned long long` 更宽的扩展整数类型的所有值**。这句话为 ABI 稳定性开了口子：`intmax_t` 出现在 `printf("%jd")`、`imaxabs` 等 C 库函数的 ABI 中，一旦固定就不能加宽。如果实现日后加入一个 128 位的扩展整数类型，它不必为此改变 `intmax_t`。

### 可选性（¶3）

- 名字中带 *N* 的类型，在 *N* 不是 8、16、32、64 时**都是可选的**（例如 `int24_t`、`int_least128_t`）。
- **定宽**类型 `intN_t`/`uintN_t` 即使在 *N* = 8、16、32、64 时也是可选的；**但**如果实现有对应宽度且没有填充位的整数类型，就**必须**声明这些 *typedef-name*。所以在任何"有 8 位字节和二进制补码 32 位整数"的平台上，`int32_t` 必然存在。
- 每个宏当且仅当对应的 *typedef-name* 被声明时才定义——因此可以用 `#ifdef INT8_MAX` 检测 `int8_t` 是否存在。
- 注 1：`INTN_C` 与 `UINTN_C` 宏对应的是 `int_leastN_t`/`uint_leastN_t`，而不是 `intN_t`。`INT64_C(5)` 展开为一个类型为 `int_least64_t` 提升后类型的整型常量表达式，例如 `5LL`。

!!! pitfall "`int8_t` 是字符类型"
    在几乎所有实现上，`std::int8_t` 是 `signed char` 的别名，`std::uint8_t` 是 `unsigned char` 的别名。于是 `std::cout << std::int8_t{65}` 打印字符 `A` 而不是 `65`；`uint8_t*` 也和 `unsigned char*` 一样能为任意对象别名（[[basic.lval]]）——这有时会让优化器无法假设 `uint8_t*` 与其他指针不重叠。标准并不保证 `int8_t` 是 `signed char`（理论上可以是一个 8 位的扩展整数类型），但改动它会破坏 ABI，所以实践上不会变。

```cpp run title="cstdint.cpp" impl
#include <cstdint>
#include <type_traits>

static_assert(sizeof(std::int32_t) * 8 == 32);                 // 若存在，宽度恰好 32
static_assert(sizeof(std::int_least16_t) * 8 >= 16);
static_assert(std::is_same_v<std::int8_t, signed char>);       // 实践中如此，标准不保证
static_assert(std::is_same_v<decltype(INT64_C(5)), long long> || std::is_same_v<decltype(INT64_C(5)), long>);

int main() {
    int x = 0;
    auto i = reinterpret_cast<std::uintptr_t>(&x);
    int* p = reinterpret_cast<int*>(i);                        // 往返转换得到原指针（[expr.reinterpret.cast]）
    return p == &x ? 0 : 1;
}
```

!!! impl
    在 macOS（Apple Silicon）上，`int64_t` 是 `long long`、`intptr_t` 是 `long`；在 x86-64 Linux（glibc）上，`int64_t` 是 `long`。两者都是 64 位，但**是不同的类型**——为 `long` 和 `long long` 都提供重载的代码在两个平台上行为一致，只为其中一个提供重载、又用 `int64_t` 去调用的代码则可能在另一平台上报歧义。

## `<stdfloat>`（[stdfloat.syn]）

¶1：`<stdfloat>` 为 [[basic.extended.fp]] 中规定的**可选扩展浮点类型**声明类型别名：

```cpp
namespace std {
#if defined(__STDCPP_FLOAT16_T__)
  using float16_t  = implementation-defined;   // IEEE binary16
#endif
  // float32_t、float64_t、float128_t、bfloat16_t 同理
}
```

每个别名都由对应的预定义宏（[[cpp.predefined]]）守卫：`__STDCPP_FLOAT16_T__`、`__STDCPP_FLOAT32_T__`、`__STDCPP_FLOAT64_T__`、`__STDCPP_FLOAT128_T__`、`__STDCPP_BFLOAT16_T__`。如果编译器定义了这些宏，它就承诺提供一个具有对应 IEEE 格式的**扩展浮点类型**——一个与 `float`/`double` **不同的类型**，即使格式相同（`std::float64_t` 不是 `double`）。这些类型的字面量后缀（`1.0f16`、`1.0bf16`……）、转换等级（[[conv.rank]]）以及不允许隐式窄化等规则都在核心语言中规定。

!!! impl "Clang + libc++ 尚未提供"
    截至本文编写时，Clang 不预定义任何 `__STDCPP_FLOAT*_T__` 宏（它有 `_Float16`、`__bf16` 等扩展类型，但没有按 [[basic.extended.fp]] 的要求实现），libc++ 也没有提供 `<stdfloat>` 头文件——`#include <stdfloat>` 直接报 "file not found"。GCC 13 起与 libstdc++ 支持这些类型。可移植代码应当用 `__has_include(<stdfloat>)` 加上对应宏一起检测。

```cpp run title="stdfloat-detect.cpp" ok
#if __has_include(<stdfloat>)
#  include <stdfloat>
#endif

int main() {
#if defined(__STDCPP_FLOAT16_T__)
    std::float16_t h = 1.5f16;
    return h == 1.5f16 ? 0 : 1;
#else
    return 0;                     // 实现不提供 float16_t
#endif
}
```

## 小结

!!! summary
    - `intN_t`：恰好 *N* 位、无填充；可选，但只要平台有对应类型就必须提供。`int_leastN_t`/`int_fastN_t`（*N* = 8/16/32/64）必需。
    - C++ 中 `intptr_t`/`uintptr_t` 总是存在；`intmax_t` 不必覆盖比 `long long` 更宽的扩展整数类型。
    - 宏当且仅当对应类型存在时才定义；`INTN_C` 对应 `int_leastN_t`。
    - `<stdfloat>` 的别名都是可选的，由 `__STDCPP_FLOAT*_T__` 宏守卫，它们是与 `float`/`double` 不同的类型。
