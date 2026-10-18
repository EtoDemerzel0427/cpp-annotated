---
title: 字符串库
summary: 第 27 章导读——"字符"在标准库里的精确定义（char-like type）、为什么 string/string_view/iostream 都要带一个 traits 参数、四个子条款各管什么，以及读这一章需要先掌握的核心语言规则
status: done
covers: strings.general
related: char.traits, string.view, string.classes, basic.string, c.strings, lex.string, basic.types.general, views.contiguous, charconv, format
tags: 标准库, 字符串, 导读
updated: 2026-10-18
---

第 27 章是标准库里"文本"的地基，但它的地基不是 Unicode，也不是 locale，而是一个非常朴素的问题：**一段连续的、可以按值拷来拷去的小对象序列，应该怎么管理？** 这里的"小对象"标准称为 *char-like object*，它可以是 `char`，也可以是你自己定义的一个三字节结构体。至于这些对象编码了什么文字，是第 28 章 [text]（`<locale>`、`<format>`、`<charconv>`、`<text_encoding>` 以及 `<cwchar>`/`<cuchar>`）的事。

读这一章之前需要的核心语言前置：

- **平凡可复制、标准布局**（[[basic.types.general]]、[[class.prop]]）：char-like type 的定义直接引用这两个概念；
- **临时对象的生命周期**（[[class.temporary]]）：`string_view` 的大部分事故都是它造成的；
- **字符串字面量**（[[lex.string]]）与用户定义字面量（[[over.literal]]）：`"abc"`、`"abc"s`、`"abc"sv` 的类型和长度各不相同；
- **隐式创建对象**（[[intro.object]]）：`memcpy`/`memmove` 在 C++ 里的语义靠它。

## 什么是"字符"：char-like type（¶1）

!!! std
    This Clause describes components for manipulating sequences of any non-array trivially copyable standard-layout type `T` where `is_trivially_default_constructible_v<T>` is true. Such types are called *char-like types*.

    本章处理的元素类型 `T` 必须是：非数组、平凡可复制、标准布局、可平凡默认构造。满足这些条件的类型叫 **char-like type**（[[g:char-like-type]]），其对象叫 char-like object，或者直接叫"字符"。

这四个条件各有用途：

| 条件 | 为什么需要 |
|---|---|
| 平凡可复制 | `basic_string` 在内部用 `traits::copy`/`traits::move`（通常就是 `memcpy`/`memmove`）搬运元素，不调用拷贝构造函数 |
| 可平凡默认构造 | 预留容量（`reserve`、`resize_and_overwrite`）时只需分配存储、无需逐个运行构造函数；值初始化的 `charT()` 被用作**终止符** |
| 标准布局 | 保证与 C 的内存布局兼容，可以把 `data()` 交给 C 接口 |
| 非数组 | 元素要能按值传递、返回和赋值（`push_back(charT)`、`operator=(charT)`、`traits::assign(r, d)`），数组做不到 |

这是个**比"字符类型"宽得多**的集合。核心语言里的 [[g:character-type]] 只有 `char`、`signed char`、`unsigned char`、`char8_t`、`char16_t`、`char32_t`、`wchar_t`；而一个 `struct Glyph { std::uint16_t code; std::uint8_t attr; };` 也是 char-like type。不过能放进 `basic_string` 还需要一个配套的 traits 类（[[char.traits]]），标准只为五种字符类型提供了 `char_traits` 特化——`basic_string<unsigned char>` 在 libc++ 上直接编译失败，原因在 [[char.traits]] 里解释。

!!! note "char-like 与 “character container type”"
    [char.traits.general] ¶3 用的是另一个术语 *character container type*（[[defns.character.container]]）：traits 类 `X` 所描述的那个字符类型。实际上两者指的是同一批类型，只是一个从"能放进字符串"的角度命名，另一个从"traits 为谁服务"的角度命名。

## 四个子条款（¶2）

| 子条款 | 头文件 | 内容 | 本站笔记 |
|---|---|---|---|
| [char.traits] | `<string>` | 字符 traits 要求与五个 `char_traits` 特化 | [[char.traits]] |
| [string.view] | `<string_view>` | 非拥有的只读视图 `basic_string_view` | [[string.view]] |
| [string.classes] | `<string>` | 拥有存储的 `basic_string` 及其非成员函数、数值转换、哈希、字面量 | [[string.classes]]、[[basic.string]] |
| [c.strings] | `<cstring>` | C 的 `memcpy`/`strlen`/`strtok` 等 | [[c.strings]] |

注意 `<cwchar>`、`<cuchar>`、`<cctype>`、`<cwctype>` 不在这里：它们涉及多字节编码与 locale，被放在第 28 章的 [[text.c.strings]]。这一章里唯一与编码沾边的是 `char_traits::state_type`（通常是 `mbstate_t`），而它只被 iostream 的 `codecvt` 用到。

## 三种"字符串"的分工

把这一章的类型放在一张图里，关键区别是**谁拥有存储**以及**有没有终止符**：

| | 拥有存储 | 保证 `'\0'` 终止 | 长度来源 | 典型来源 |
|---|---|---|---|---|
| ntbs（[[g:ntbs]]，`const char*`，[[byte.strings]]） | 不确定 | 是（定义如此） | 线性扫描 `strlen` | 字面量、C API |
| `basic_string_view` | 否 | **否** | 存储的 `size_` | 任何连续字符序列 |
| `basic_string` | 是 | 是（[basic.string.general] ¶3） | 存储的 size | 自己 |

这张表解释了本章几乎所有陷阱：

- 从 `string_view` 拿 `data()` 交给 C API ——缺终止符（[[string.view]]）；
- 把临时 `string` 绑定到 `string_view` ——缺所有权（[[string.view]]）；
- 在 `string` 增长后继续用旧的 `c_str()` ——存储被换掉（[[basic.string]] 的失效规则）；
- 对 ntbs 用 `memcpy` 处理重叠区间 ——C 函数没有 C++ 的安全网（[[c.strings]]）。

## 本章在 C++ 版本里的主要变化

| 版本 | 变化 |
|---|---|
| C++11 | `basic_string` 禁止写时复制（COW）：数据竞争规则与 `operator[]` 不得使迭代器失效的要求实际上排除了引用计数实现；`char16_t`/`char32_t` 特化；`to_string`/`stoi` |
| C++17 | `basic_string_view`（[[P0254R2]] 把它接入 `basic_string`）；`char_traits` 成员 `constexpr`（[[P0426R1]]） |
| C++20 | `char8_t` 与 `u8string`（[[P0482R6]]）；`constexpr basic_string`（[[P0980R1]]）；`starts_with`/`ends_with`（[[P0457R2]]）；`<=>`（[[P1614R2]]） |
| C++23 | `contains`（[[P1679R3]]）；`resize_and_overwrite`（[[P1072R10]]）；禁止从 `nullptr` 构造（[[P2166R1]]）；`string_view` 的 range 构造函数（[[P1989R2]]，随后由 [[P2499R0]] 改为 `explicit`）；`substr() &&`（[[P2438R2]]） |
| C++26 | `string` 与 `string_view` 直接拼接（[[P2591R5]]）；`to_string` 改为按 `format("{}")` 定义（[[P2587R3]]）；`operator[]`/`front`/`back` 等成为加固前置条件（[[P3471R4]]） |

之后的工作草案还新增了 `subview`（返回 `string_view` 的 `substr`）、整数版 `to_string` 的 `constexpr`，以及 `<cstring>` 随 C23 加入的 `memset_explicit`、`strdup` 等。

## 小结

- 这一章的"字符"是 **char-like type**：非数组、平凡可复制、标准布局、可平凡默认构造；字符**语义**（相等、大小、长度、EOF）由 traits 类提供。
- 三种表示：ntbs（终止符定长度）、`string_view`（不拥有、不保证终止）、`string`（拥有、保证终止）。
- 编码、locale、宽字符转换不在本章，而在 [text]。
