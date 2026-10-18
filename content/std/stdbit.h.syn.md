---
title: 头文件 <stdbit.h> 概要
summary: C++26 收录 C23 的 <stdbit.h>：stdc_leading_zeros 等按类型后缀命名的函数、对应的类型泛型函数模板（Mandates 无符号整数，返回类型多为实现定义）与 __STDC_ENDIAN_* 宏；语义完全按 C 标准，没有 <cstdbit>，名字在全局命名空间
status: draft
papers: P3370
related: bit, bitset, support.c.headers, structure.specifications
tags: 标准库, C 兼容, stdbit.h, freestanding
updated: 2026-10-18
---

C23 新增了头文件 `<stdbit.h>`，提供与 C++20 `<bit>`（[[bit]]）功能相近的位计数与 2 的幂函数，以及字节序宏。{{c++26}} 起 C++ 也收录这个头文件（[[P3370]]，与 `<stdckdint.h>` 一起作为"来自 C23 的新库头文件"），目的只有一个：**让同一份头文件能同时被 C 和 C++ 编译**。在纯 C++ 代码里，应当优先使用 `<bit>`。

## 概要的形状

概要第一行是 `// all freestanding`。内容分三部分：

1. **版本宏** `__STDC_VERSION_STDBIT_H__`，值为 `202311L`；
2. **字节序宏** `__STDC_ENDIAN_BIG__`、`__STDC_ENDIAN_LITTLE__`、`__STDC_ENDIAN_NATIVE__`（"见下文"，即按 C 标准）——它们与 `std::endian`（[[bit.endian]]）一一对应：在混合字节序平台上 `NATIVE` 与另外两个都不相等；
3. **14 组函数**，每组有 5 个按类型后缀区分的普通函数（`_uc`、`_us`、`_ui`、`_ul`、`_ull`，对应 `unsigned char` 到 `unsigned long long`）加 1 个类型泛型的函数模板：

| C 函数族 | 对应的 `<bit>` 函数 | 返回 |
|---|---|---|
| `stdc_leading_zeros` / `_ones` | `countl_zero` / `countl_one` | `unsigned int` |
| `stdc_trailing_zeros` / `_ones` | `countr_zero` / `countr_one` | `unsigned int` |
| `stdc_first_leading_zero` / `_one` | 无直接对应 | `unsigned int` |
| `stdc_first_trailing_zero` / `_one` | 无直接对应 | `unsigned int` |
| `stdc_count_zeros` / `_ones` | `popcount`（及其补） | `unsigned int` |
| `stdc_has_single_bit` | `has_single_bit` | `bool` |
| `stdc_bit_width` | `bit_width` | `unsigned int` |
| `stdc_bit_floor` / `stdc_bit_ceil` | `bit_floor` / `bit_ceil` | 与参数同类型 |

`first_*` 系列返回的是**位置**而非计数：C 标准规定其为从相应一端数起、以 1 为基的位置，找不到时返回 0。`<bit>` 中没有对应函数（可由 `countl_zero(x) + 1` 等组合出来，但需单独处理"找不到"）。

## 函数模板：C 的类型泛型宏在 C++ 中的替身（¶1–2）

C 中 `stdc_leading_zeros(value)` 是类型泛型宏（基于 `_Generic` 之类的机制）。C++ 没有 `_Generic`，于是概要把它们写成函数模板 `template<class T> see below stdc_leading_zeros(T value);`。

- ¶1：返回类型未在概要中给出的函数模板，其返回类型是一个**实现定义**的、足以表示所有可能结果的无符号整数类型；每个模板的语义与 C 标准（ISO/IEC 9899:2024 第 7.18 节）中同名的类型泛型函数相同。
- ¶2 *Mandates*：`T` 是无符号整数类型。

注意这里用的是 *Mandates* 而不是 `<bit>` 的 *Constraints*（[[structure.specifications]]）：传入 `int` 时，`<bit>` 的 `std::popcount` 是"没有匹配的函数"（不参与重载决议，可被 SFINAE / `requires` 探测），而 `stdc_count_ones(1)` 是**非良构**的调用（需要诊断；实现通常用 `static_assert` 落实，因而一般无法被 SFINAE 探测）。

¶3：除上述之外，`<stdbit.h>` 的内容和含义与 C 标准库的 `<stdbit.h>` 相同。

## 与 `<bit>` 的差别

- **名字在全局命名空间**，没有 `std::` 版本，也**没有** `<cstdbit>`——与 `<stdckdint.h>`、`<stdatomic.h>` 一样，这是"仅为 C 兼容"的头文件（参见 [[support.c.headers]]）。
- **不是 `constexpr`**：概要中的函数都没有 `constexpr`，也没有 `noexcept`。需要编译期计算时用 `<bit>`。
- 返回类型是 `unsigned int`（或实现定义的无符号类型），而 `<bit>` 的计数函数返回 `int`——混用时注意有符号/无符号比较警告。

## 实现状态

截至本文编写时，本机的 libc++（LLVM 23）不提供 `<stdbit.h>`，macOS SDK 的 C 库也没有这个头文件，`#include <stdbit.h>` 在 C 和 C++ 模式下都报 *file not found*。部分其他平台的 C 库已提供 C 版本，但 C++ 所需的函数模板形式需要标准库额外提供。因此本页不给出可运行示例。

## 小结

| 方面 | `<stdbit.h>` | `<bit>` |
|---|---|---|
| 来源 | C23，C++26 收录 | C++20 |
| 命名空间 | 全局 | `std` |
| 泛型形式 | 函数模板，*Mandates* 无符号整数 | 函数模板，*Constraints* 无符号整数 |
| `constexpr` | 否 | 是 |
| 计数返回类型 | `unsigned int` / 实现定义 | `int` |
| 用途 | C/C++ 共享头文件 | C++ 代码首选 |
