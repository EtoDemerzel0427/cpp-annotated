---
title: 字符串库
summary: 第 27 章导读：本章所说的字符（char-like type）是什么，为什么 string 和 string_view 都要带一个 traits 参数，四个子条款各管什么，以及三种字符串表示的分工。
status: done
covers: strings.general
related: char.traits, string.view, string.classes, basic.string, c.strings, lex.string, basic.types.general, views.contiguous, charconv, format
tags: 标准库, 字符串, 导读
updated: 2026-10-19
---

!!! tldr
    - 本章的字符叫 char-like type：非数组、可平凡复制、标准布局、可平凡默认构造的任何类型，不限于 `char` 这类字符类型。
    - 字符之间如何比较、如何复制、字符串多长，由 traits 类决定；标准只为五种字符类型提供了 `char_traits`。
    - 本章有四部分：字符 traits、`string_view`、`string`、C 的空终止字符串函数。编码和 locale 不在本章，在第 28 章。
    - 三种表示：C 风格字符串靠 `'\0'` 确定长度；`string_view` 不拥有存储，也不保证以 `'\0'` 结尾；`string` 拥有存储，保证以 `'\0'` 结尾。

## 什么是字符（¶1）

```cpp run title="char_like.cpp" ok
#include <cstdint>
#include <type_traits>

struct Glyph { std::uint16_t code; std::uint8_t attr; };

// Glyph 满足 char-like type 的全部四个条件
static_assert(std::is_trivially_copyable_v<Glyph>);
static_assert(std::is_standard_layout_v<Glyph>);
static_assert(std::is_trivially_default_constructible_v<Glyph>);
static_assert(!std::is_array_v<Glyph>);

int main() {}
```

!!! std
    This Clause describes components for manipulating sequences of any non-array trivially copyable standard-layout type `T` where `is_trivially_default_constructible_v<T>` is true. Such types are called *char-like types*.

¶1 本章处理的元素类型必须同时满足四个条件：不是数组、可平凡复制、标准布局（[[basic.types.general]]）、可平凡默认构造。满足条件的类型叫 **char-like type**（[[g:char-like-type]]），它的对象叫 char-like object，或者直接叫字符。上面的 `Glyph` 就是一个 char-like type。

四个条件各有用处：

| 条件 | 用处 |
|---|---|
| 可平凡复制 | `basic_string` 用 `traits::copy`、`traits::move` 搬运元素，通常就是 `memcpy`、`memmove`，不调用复制构造函数 |
| 可平凡默认构造 | 预留容量时只需分配存储，不必逐个运行构造函数；值初始化的 `charT()` 用作结尾的空字符 |
| 标准布局 | 内存布局与 C 兼容，可以把 `data()` 交给 C 接口 |
| 不是数组 | 元素要能按值传递、返回和赋值，如 `push_back(charT)`、`traits::assign(r, d)`，数组做不到 |

这个集合比核心语言的**字符类型**（[[g:character-type]]）宽得多。字符类型只有 `char`、`signed char`、`unsigned char`、`char8_t`、`char16_t`、`char32_t`、`wchar_t` 七种。

不过，要放进 `basic_string`，还需要一个配套的 traits 类描述字符的语义：如何比较相等、如何求长度、文件结束用什么值表示（[[char.traits]]）。标准只为 `char`、`char8_t`、`char16_t`、`char32_t`、`wchar_t` 五种类型提供了 `char_traits` 特化，`char_traits` 的主模板只有声明。所以 `std::basic_string<unsigned char>` 在本机 libc++ 上编译失败，报错 `implicit instantiation of undefined template 'std::char_traits<unsigned char>'`。

[char.traits.general] 用的是另一个术语：**字符容器类型**（character container type，[[defns.character.container]]），指 traits 类所描述的那个字符类型。两个术语实际指同一批类型，一个从能放进字符串的角度命名，一个从 traits 为谁服务的角度命名。

## 四个子条款（¶2）

| 子条款 | 头文件 | 内容 | 本站笔记 |
|---|---|---|---|
| [char.traits] | `<string>` | 字符 traits 的要求和五个 `char_traits` 特化 | [[char.traits]] |
| [string.view] | `<string_view>` | 不拥有存储的只读视图 `basic_string_view` | [[string.view]] |
| [string.classes] | `<string>` | 拥有存储的 `basic_string`，以及非成员函数、数值转换、哈希、字面量 | [[string.classes]]、[[basic.string]] |
| [c.strings] | `<cstring>` | C 的 `memcpy`、`strlen`、`strtok` 等 | [[c.strings]] |

`<cwchar>`、`<cuchar>`、`<cctype>`、`<cwctype>` 不在本章。它们涉及多字节编码和 locale，放在第 28 章的 [[text.c.strings]]。第 28 章还包括 `<locale>`、`<format>`、`<charconv>`、`<text_encoding>`。本章只关心如何管理一段字符序列，不关心这些字符编码了什么文字。

## 三种字符串表示

| | 拥有存储 | 以 `'\0'` 结尾 | 长度从哪里来 | 典型来源 |
|---|---|---|---|---|
| 空终止字节串（[[g:ntbs]]，[[byte.strings]]） | 不一定 | 是，定义如此 | 用 `strlen` 线性扫描 | 字符串字面量、C 接口 |
| `basic_string_view` | 否 | 不保证 | 存储的长度 | 任何连续的字符序列 |
| `basic_string` | 是 | 是（[[basic.string.general#3]]） | 存储的长度 | 自身 |

本章的大多数陷阱都能从这张表推出来：

- 把 `string_view` 的 `data()` 交给需要空终止字符串的 C 接口，结尾可能没有 `'\0'`（[[string.view]]）；
- 让 `string_view` 指向一个临时的 `string`，`string` 销毁后视图悬垂，因为视图不拥有存储（[[string.view]]）；
- `string` 增长后继续使用旧的 `c_str()` 指针，存储可能已经换了（[[basic.string]] 的失效规则）；
- 用 `memcpy` 处理重叠的区间，C 函数没有任何检查（[[c.strings]]）。

读本章还会用到这些核心语言规则：临时对象的生命期（[[class.temporary]]），`string_view` 的悬垂问题大多由它引起；字符串字面量（[[lex.string]]）与用户定义字面量（[[over.literal]]），`"abc"`、`"abc"s`、`"abc"sv` 的类型各不相同；隐式创建对象（[[intro.object]]），`memcpy` 在 C++ 中的语义依赖它。

## 各版本的主要变化

| 版本 | 变化 |
|---|---|
| C++11 | 禁止 `basic_string` 写时复制：数据竞争规则和 `operator[]` 不得使迭代器失效的要求实际上排除了引用计数实现；`char16_t`、`char32_t` 特化；`to_string`、`stoi` |
| C++17 | `basic_string_view`（[[P0254R2]] 把它接入 `basic_string`）；`char_traits` 的成员成为 `constexpr`（[[P0426R1]]） |
| C++20 | `char8_t` 与 `u8string`（[[P0482R6]]）；`constexpr` 的 `basic_string`（[[P0980R1]]）；`starts_with`、`ends_with`（[[P0457R2]]）；`<=>`（[[P1614R2]]） |
| C++23 | `contains`（[[P1679R3]]）；`resize_and_overwrite`（[[P1072R10]]）；禁止用 `nullptr` 构造（[[P2166R1]]）；`string_view` 的范围构造函数（[[P1989R2]]，随后由 [[P2499R0]] 改为 `explicit`）；`substr() &&`（[[P2438R2]]） |
| C++26 | `string` 与 `string_view` 直接拼接（[[P2591R5]]）；`to_string` 改用 `format("{}")` 定义（[[P2587R3]]）；`operator[]`、`front`、`back` 等的前置条件成为加固前置条件（[[P3471R4]]） |

当前草案中还有一些 C++23 之后的新内容：返回 `string_view` 的 `subview`（[[P3044R2]]），以及 `<cstring>` 随 C23 加入的 `memset_explicit`、`strdup` 等。
