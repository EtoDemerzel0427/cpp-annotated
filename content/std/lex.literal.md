---
title: 字面量
summary: 七种字面量各是什么、作为表达式时是什么值类别，以及最简单的两种：布尔字面量 true/false 和指针字面量 nullptr。
status: done
covers: lex.literal.kinds, lex.bool, lex.nullptr
related: lex.icon, lex.ccon, lex.fcon, lex.string, lex.ext, expr.prim.literal, conv.ptr, dcl.init.general, topics/value-categories
tags: 字面量
updated: 2026-10-19
---

!!! tldr
    - 字面量有七种：整数、字符、浮点、字符串、布尔、指针、用户定义。
    - 字符串字面量是左值，用户定义字面量的值类别跟随对应的运算符调用，其余字面量都是纯右值。
    - `-1` 不是字面量，而是一元 `-` 作用于字面量 `1`。
    - `true` 和 `false` 的类型是 `bool`，在 `#if` 里也保持原值，不会被替换成 0。
    - `nullptr` 的类型 `std::nullptr_t` 不是指针类型；它能转换成任何指针，却不能转换成整数，所以重载决议不会把它当成 `int`。

**字面量**（literal）是直接写在源码里的值，例如 `42`、`'a'`、`"abc"`。第 5 章只规定字面量的拼写和它的类型、值；作为表达式时它是左值还是右值，由 [[expr.prim.literal]] 规定。

## 七种字面量（[[lex.literal.kinds]]）

¶1 文法把字面量分成七种，其中五种各有专页：

| 种类 | 例子 | 页面 |
|---|---|---|
| 整数字面量 | `42`、`0x2A`、`0b101`、`1'000uz` | [[lex.icon]] |
| 字符字面量 | `'a'`、`u8'x'`、`L'w'`、`'\n'` | [[lex.ccon]] |
| 浮点字面量 | `3.14`、`1e-9f`、`0x1p-3` | [[lex.fcon]] |
| 字符串字面量 | `"abc"`、`R"(raw)"`、`u8"x"` | [[lex.string]] |
| 布尔字面量 | `true`、`false` | 本页 |
| 指针字面量 | `nullptr` | 本页 |
| 用户定义字面量 | `12_km`、`"abc"s` | [[lex.ext]] |

### 值类别

注 1 提醒，字面量作为表达式出现时具有类型和值类别。[[expr.prim.literal]] 的规定是：

- 字符串字面量是**左值**，指代一个静态存储期的字符串字面量对象（[[lex.string]]）；
- 用户定义字面量的值类别与它对应的字面量运算符调用相同（[[lex.ext]]）；
- 其余字面量都是纯右值。

字符串字面量是左值，是因为它确实对应内存里的一个数组对象，所以可以对它取地址，也可以把它绑定到数组引用上。

```cpp run title="literal-categories.cpp" ok
#include <type_traits>
#include <cstddef>
// decltype((e)) 对左值给出引用类型，对纯右值给出非引用类型
static_assert(std::is_same_v<decltype(("abc")), const char(&)[4]>);
static_assert(std::is_same_v<decltype((42)), int>);
static_assert(std::is_same_v<decltype(true), bool>);
static_assert(std::is_same_v<decltype(nullptr), std::nullptr_t>);
const char (*p)[4] = &"abc";   // OK：字符串字面量是左值，可以取地址
int main() {}
```

### 负数不是字面量

文法里没有负号。`-1` 是一元运算符 `-` 作用于整数字面量 `1`。这一点会影响类型：`-2147483648` 的类型由 `2147483648` 决定，在 32 位 `int` 的平台上是 `long` 或 `long long`，而不是 `int`（见 [[lex.icon]]）。这也是 `INT_MIN` 通常被定义为 `(-2147483647 - 1)` 的原因。

### 字面量与常量表达式不是一回事

字面量是词法概念，常量表达式是语义概念（[[expr.const]]）。`42` 两者都是；`std::numeric_limits<int>::max()` 是常量表达式，却不是字面量。**字面类型**（literal type，[[basic.types.general]]）又是另一个概念，指可以在常量求值中使用的类型，和字面量只是名字相近。

## 布尔字面量（[[lex.bool]]）

¶1 布尔字面量是关键字 `false` 和 `true`，类型为 `bool`。

它们参与算术时按整数提升变成 `int` 的 0 和 1（[[conv.prom]]），所以 `true + true == 2`。

预处理器也认识它们。`#if` 求值时，宏展开之后剩下的标识符和关键字一律替换为 0，只有 `true` 和 `false` 例外（[[cpp.cond]]）。所以 `#if true` 在 C++ 里成立。

```cpp run title="bool-literal.cpp" ok
static_assert(true + true == 2);     // 提升为 int
#if true && !false                   // 预处理器保留 true/false 的值
static_assert(sizeof(true) == sizeof(bool));
#endif
int main() {}
```

C 语言直到 C23 才把 `true`、`false` 变成关键字，此前它们是 `<stdbool.h>` 中值为 `int` 1 和 0 的宏。

## 指针字面量（[[lex.nullptr]]）

¶1 指针字面量是关键字 `nullptr`，类型为 `std::nullptr_t`。

注 1 补充了这个类型的性质：`std::nullptr_t` 是一个独立的类型，既不是指针类型，也不是成员指针类型。它的纯右值是**空指针常量**，可以转换为任何指针类型的空指针值，或任何成员指针类型的空成员指针值（[[conv.ptr]]、[[conv.mem]]）。

### 为什么需要 `nullptr`

C++11 之前，空指针常量只能是值为 0 的整数字面量，例如 `0`、`0L`。它的类型是整数，重载决议也就把它当整数看：

```cpp title="null-overload.cpp" error
#include <cstddef>
void f(int);
void f(char*);
void g() {
  f(0);         // 选 f(int)，多半不是本意
  f(NULL);      // error: 本机 NULL 是 __null，两个重载有歧义
  f(nullptr);   // OK：选 f(char*)
}
```

`NULL` 的定义由实现决定（[[support.types.nullptr]]），可能是 `0`、`0L` 或编译器内建的 `__null`，所以 `f(NULL)` 在不同平台上可能选 `f(int)`，也可能有歧义。本机 Clang 23 报歧义。

`std::nullptr_t` 能隐式转换为任何指针类型，却不能隐式转换为整数类型，`f(nullptr)` 因此只有一个可行函数。在模板实参推导中，`nullptr` 推导出 `std::nullptr_t`，而 `0` 推导出 `int`，所以经过完美转发后，空指针的含义也不会丢失。

### `std::nullptr_t` 的其他性质

[[basic.fundamental#16]] 规定，`std::nullptr_t` 的大小和对齐与 `void*` 相同；它的值表示可以不含任何位，因为所有值都相同。`<cstddef>` 用 `decltype(nullptr)` 定义这个名字。

可以定义 `std::nullptr_t` 类型的变量。读出来的值是 `std::nullptr_t` 纯右值，也是空指针常量，所以同样能转换为任何指针。

转换为 `bool` 只允许在直接初始化中进行（[[dcl.init.general#15.8]]），结果为 `false`：

<div class="compare" markdown="1">

```cpp ok
bool a{nullptr};   // OK：直接初始化，false
```

```cpp error
bool b = nullptr;  // error：复制初始化
```

</div>

Clang 对左边仍会给出 `-Wnull-conversion` 警告，因为这种写法几乎总是笔误。

!!! history
    `nullptr` 由 C++11 引入（[[N2431]]）。C23 也引入了 `nullptr` 和 `nullptr_t`，语义与 C++ 基本一致。

## 常见误解

!!! pitfall "字符串字面量是右值"
    `"abc"` 是 `const char[4]` 类型的左值，可以取地址，也可以绑定到 `const char(&)[4]`。它在大多数场合变成 `const char*` 纯右值，那是数组到指针转换的结果，不是字面量本身的值类别。

!!! pitfall "`nullptr` 是一个指针"
    `std::is_pointer_v<std::nullptr_t>` 为 `false`。`nullptr` 不能解引用，`std::nullptr_t` 也不是任何 `T*`。它只是能转换成指针。

## 思考题

!!! question "思考题"
    下面每个表达式的类型和值类别是什么？

    ```cpp
    'a'      u8"x"      nullptr      -1      true      1.0f
    ```

<details markdown="1">
<summary>答案</summary>

- `'a'`：`char` 纯右值。
- `u8"x"`：`const char8_t[2]` 左值。
- `nullptr`：`std::nullptr_t` 纯右值。
- `-1`：不是字面量，是一元 `-` 表达式，`int` 纯右值。
- `true`：`bool` 纯右值。
- `1.0f`：`float` 纯右值。
</details>
