---
title: 头文件 <stdbit.h> 概要
summary: C++26 收录 C23 的 <stdbit.h>，让同一份头文件能同时被 C 和 C++ 编译；它的函数与 <bit> 功能相近，但名字在全局命名空间、不是 constexpr、返回无符号类型。
status: draft
papers: P3370
related: bit, bitset, support.c.headers, structure.specifications
tags: 标准库, C 兼容, stdbit.h, freestanding
updated: 2026-10-19
---

!!! tldr
    - `<stdbit.h>` 来自 C23，提供位计数、2 的幂函数和字节序宏。C++26 收录它，只是为了让 C 和 C++ 能共用同一份头文件。纯 C++ 代码应当用 `<bit>`（[[bit]]）。
    - 每个函数族有 5 个按参数类型命名的普通函数（`_uc` 到 `_ull`），外加一个函数模板，代替 C 里的类型泛型宏。
    - 函数模板的 *Mandates* 要求无符号整数类型：传入 `int` 是非良构的，而 `<bit>` 的同名功能是不参与重载决议。
    - 名字在全局命名空间，没有 `<cstdbit>`，函数不是 `constexpr`，计数结果是无符号类型。

## 内容（[stdbit.h.syn]）

C23 新增了头文件 `<stdbit.h>`。{{c++26}} 起 C++ 也提供它（[[P3370]]，与 `<stdckdint.h>` 一起作为来自 C23 的新头文件）。概要第一行是 `// all freestanding`，内容分三部分：

1. 版本宏 `__STDC_VERSION_STDBIT_H__`，值为 `202311L`。
2. 字节序宏 `__STDC_ENDIAN_BIG__`、`__STDC_ENDIAN_LITTLE__`、`__STDC_ENDIAN_NATIVE__`，值按 C 标准规定。它们和 `std::endian`（[[bit.endian]]）的三个值一一对应。
3. 14 组函数。每组有 5 个按参数类型后缀区分的普通函数（`_uc`、`_us`、`_ui`、`_ul`、`_ull`，分别对应 `unsigned char` 到 `unsigned long long`），再加 1 个函数模板。

| C 函数族 | 对应的 `<bit>` 函数 | 普通函数的返回类型 |
|---|---|---|
| `stdc_leading_zeros`、`stdc_leading_ones` | `countl_zero`、`countl_one` | `unsigned int` |
| `stdc_trailing_zeros`、`stdc_trailing_ones` | `countr_zero`、`countr_one` | `unsigned int` |
| `stdc_first_leading_zero`、`stdc_first_leading_one` | 无 | `unsigned int` |
| `stdc_first_trailing_zero`、`stdc_first_trailing_one` | 无 | `unsigned int` |
| `stdc_count_zeros`、`stdc_count_ones` | `popcount` 及其补 | `unsigned int` |
| `stdc_has_single_bit` | `has_single_bit` | `bool` |
| `stdc_bit_width` | `bit_width` | `unsigned int` |
| `stdc_bit_floor`、`stdc_bit_ceil` | `bit_floor`、`bit_ceil` | 与参数类型相同 |

`first_*` 系列返回的是位置而不是个数。按 C 标准，它是从相应一端数起、从 1 开始的位置，找不到时返回 0。`<bit>` 没有对应的函数，用 `countl_zero(x) + 1` 之类组合时要单独处理找不到的情况。

## 函数模板代替类型泛型宏（¶1–¶3）

在 C 里，`stdc_leading_zeros(value)` 是一个类型泛型宏，按参数类型选择对应的函数。C++ 没有 C 的 `_Generic`，所以概要把它们写成函数模板，例如 `template<class T> see below stdc_leading_zeros(T value);`。

¶1 概要中没有写出返回类型的函数模板，返回一个实现定义的无符号整数类型，大到足以表示所有可能的结果。每个模板的语义与 C 标准（ISO/IEC 9899:2024 第 7.18 节）中同名的类型泛型函数相同。

¶2 *Mandates*：`T` 是无符号整数类型。这里用的是 *Mandates*，而 `<bit>` 用的是 *Constraints*（[[structure.specifications]]）。区别在于传入 `int` 时：

- `std::popcount(1)` 是没有匹配的函数，因为函数模板不参与重载决议，可以用 `requires` 表达式探测；
- `stdc_count_ones(1)` 选中了函数模板，然后因 *Mandates* 不满足而非良构，必须诊断。实现通常用 `static_assert` 实现它，所以一般无法用 SFINAE 或 `requires` 探测。

¶3 除此之外，`<stdbit.h>` 的内容和含义与 C 标准库的 `<stdbit.h>` 相同。

## 与 `<bit>` 的区别

- 名字在全局命名空间，没有 `std::` 版本，也没有 `<cstdbit>`。与 `<stdckdint.h>`、`<stdatomic.h>` 一样，这个头文件只为 C 兼容而存在（[[support.c.headers]]）。
- 函数都不是 `constexpr`，也不是 `noexcept`。编译期计算要用 `<bit>`。
- 计数函数返回 `unsigned int` 或实现定义的无符号类型，`<bit>` 返回 `int`。两者混用时注意有符号和无符号比较的警告。

截至写作时，本机的 libc++（LLVM 23）不提供 `<stdbit.h>`，macOS SDK 的 C 库也没有它，`#include <stdbit.h>` 在 C 和 C++ 模式下都找不到文件。所以本页没有可运行的例子。

## 小结

| 方面 | `<stdbit.h>` | `<bit>` |
|---|---|---|
| 来源 | C23，C++26 收录 | C++20 |
| 命名空间 | 全局 | `std` |
| 泛型形式 | 函数模板，*Mandates* 无符号整数 | 函数模板，*Constraints* 无符号整数 |
| `constexpr` | 否 | 是 |
| 计数结果的类型 | `unsigned int` 或实现定义 | `int` |
| 用途 | C 与 C++ 共用的头文件 | C++ 代码首选 |
