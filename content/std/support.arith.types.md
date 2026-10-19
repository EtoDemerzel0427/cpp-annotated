---
title: 算术类型
summary: <cstdint> 的定宽、最小宽度和最快整数类型以及 intptr_t、intmax_t，和 <stdfloat> 中可选的扩展浮点类型别名 float16_t 到 bfloat16_t。
status: done
covers: *
related: basic.fundamental, basic.extended.fp, cpp.predefined, support.limits, support.types, conv.rank
tags: 标准库, cstdint, stdfloat, 定宽整数
updated: 2026-10-19
---

!!! tldr
    - `int32_t` 这类定宽类型恰好有 N 位、没有填充位。它们是可选的，但只要平台有这样的整数类型，实现就必须提供。
    - `int_least32_t`、`int_fast32_t` 这类至少 N 位的类型，在 N 为 8、16、32、64 时一定存在。
    - C++ 中 `intptr_t` 和 `uintptr_t` 总是存在，C 中它们是可选的。
    - `int8_t` 在主流实现上就是 `signed char`，输出时会被当作字符。
    - `<stdfloat>` 的 `float16_t` 等别名都是可选的，存在时它们是与 `float`、`double` 不同的类型；本机 Clang + libc++ 尚未提供。

[[basic.fundamental]] 只规定标准整数类型的最小宽度，比如 `int` 至少 16 位、`long` 至少 32 位，具体宽度由实现决定。需要恰好 32 位或至少 64 位的整数时，就用 `<cstdint>`；需要 IEEE 754 的 16 位浮点数时，用 `<stdfloat>`。

## `<cstdint>`（[cstdint.syn]）

¶1 `<cstdint>` 提供具有指定宽度的整数类型，以及描述这些类型范围的宏。整个头文件在独立实现中也必须提供。类型分五族，其中 N 是宽度：

| 类型 | 含义 | 是否一定存在 |
|---|---|---|
| `intN_t`、`uintN_t` | 恰好 N 位，没有填充位 | 可选（¶3） |
| `int_leastN_t`、`uint_leastN_t` | 至少 N 位的类型中最窄的 | N 为 8、16、32、64 时一定存在 |
| `int_fastN_t`、`uint_fastN_t` | 至少 N 位的类型中通常最快的 | N 为 8、16、32、64 时一定存在 |
| `intmax_t`、`uintmax_t` | 最宽的整数类型（有例外，见下文） | 一定存在 |
| `intptr_t`、`uintptr_t` | 能与 `void*` 往返转换的整数类型 | C++ 中一定存在（¶2） |

宏包括 `INT32_MIN`、`INT32_MAX`、`UINT32_MAX`，C23 加入的 `INT32_WIDTH` 等宽度宏，`PTRDIFF_MAX`、`SIZE_MAX`，以及构造常量的 `INT64_C(v)`、`UINT64_C(v)`、`INTMAX_C(v)`。

```cpp run title="cstdint.cpp" impl
#include <cstdint>
#include <type_traits>

static_assert(sizeof(std::int32_t) * 8 == 32);         // 存在时恰好 32 位
static_assert(sizeof(std::int_least16_t) * 8 >= 16);
static_assert(std::is_same_v<std::int8_t, signed char>); // 实践如此，标准不保证

int main() {
    int x = 0;
    auto i = reinterpret_cast<std::uintptr_t>(&x);
    int* p = reinterpret_cast<int*>(i);   // 转回来得到原来的指针
    return p == &x ? 0 : 1;
}
```

### 与 C 的差别（¶2）

¶2 `<cstdint>` 中的类型和宏与 C 的 `<stdint.h>` 相同，但有两处差别。

第一，`intptr_t`、`uintptr_t` 以及宏 `INTPTR_MIN`、`INTPTR_MAX`、`UINTPTR_MAX` 在 C++ 中总是定义。这与 [[expr.reinterpret.cast]] 呼应：指针转换为足够大的整数类型再转回来，会得到原来的值，而 `intptr_t` 就是保证存在的那个足够大的类型。

第二，`intmax_t` 和 `uintmax_t` 不必能表示比 `long long`、`unsigned long long` 更宽的扩展整数类型的所有值。`intmax_t` 出现在 `printf("%jd")`、`imaxabs` 这类 C 库函数的接口里，一旦确定就无法加宽而不破坏 ABI。有了这条例外，实现以后加入 128 位的扩展整数类型时，不必改变 `intmax_t`。

### 哪些类型一定存在（¶3）

- 带 N 的类型，在 N 不是 8、16、32、64 时都是可选的，例如 `int24_t`、`int_least128_t`。
- 定宽类型 `intN_t`、`uintN_t` 即使在 N 为 8、16、32、64 时也是可选的。但如果实现有对应宽度、没有填充位的整数类型，就必须声明这些名字。所以在任何有 32 位无填充整数类型的平台上，`int32_t` 一定存在。
- 每个宏当且仅当对应的类型名存在时才定义，因此可以用 `#ifdef INT8_MAX` 检查 `int8_t` 是否存在。
- 注 1：`INTN_C` 和 `UINTN_C` 对应的是 `int_leastN_t` 和 `uint_leastN_t`，而不是 `intN_t`。`INT64_C(5)` 展开为一个类型为 `int_least64_t` 提升后类型的整型常量，例如 `5LL`。

!!! pitfall "`int8_t` 是字符类型"
    在几乎所有实现上，`std::int8_t` 是 `signed char`，`std::uint8_t` 是 `unsigned char`。于是 `std::cout << std::int8_t{65}` 打印的是字符 `A` 而不是 `65`。`uint8_t*` 也和 `unsigned char*` 一样可以访问任何对象（[[basic.lval]]），优化器因此不能假设通过它的写入不影响其他类型的对象。标准并不保证 `int8_t` 是 `signed char`，理论上它可以是一个 8 位的扩展整数类型，但改动会破坏 ABI，实践中不会变。

!!! impl "`int64_t` 在不同平台上是不同的类型"
    在 macOS（Apple Silicon）上，`int64_t` 是 `long long`，`intptr_t` 是 `long`；在 x86-64 Linux（glibc）上，`int64_t` 是 `long`。两者都是 64 位，却是不同的类型。如果一组重载只提供了 `long` 版本和 `int` 版本，用 `int64_t` 调用时在一个平台上精确匹配，在另一个平台上可能就有歧义。

## `<stdfloat>`（[stdfloat.syn]）

¶1 `<stdfloat>` 为 [[basic.extended.fp]] 规定的可选扩展浮点类型声明别名，每个别名都由对应的预定义宏（[[cpp.predefined]]）守护：

```cpp
namespace std {
#if defined(__STDCPP_FLOAT16_T__)
  using float16_t = implementation-defined;   // IEEE binary16
#endif
  // float32_t、float64_t、float128_t、bfloat16_t 同理
}
```

编译器定义了 `__STDCPP_FLOAT16_T__` 这类宏，就表示它提供一个具有对应 IEEE 格式的扩展浮点类型。这个类型与 `float`、`double` 是不同的类型，即使格式相同，`std::float64_t` 也不是 `double`。这些类型的字面量后缀（`1.0f16`、`1.0bf16`）、转换等级（[[conv.rank]]）以及禁止隐式窄化等规则都在核心语言中规定。

!!! impl "Clang + libc++ 尚未提供"
    本机 Clang 23 不预定义任何 `__STDCPP_FLOAT*_T__` 宏。它有 `_Float16`、`__bf16` 等扩展类型，但没有按 [[basic.extended.fp]] 的要求实现。libc++ 也没有 `<stdfloat>` 头文件，`#include <stdfloat>` 报告找不到文件。GCC 13 起与 libstdc++ 支持这些类型。可移植的代码应当同时检查 `__has_include(<stdfloat>)` 和对应的宏：

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
