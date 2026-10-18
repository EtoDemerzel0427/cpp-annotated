---
title: 字面量
summary: 七种字面量的总览，以及其中最简单的两种：布尔字面量 true/false 和指针字面量 nullptr。
status: draft
covers: lex.literal.kinds, lex.bool, lex.nullptr
related: lex.icon, lex.ccon, lex.fcon, lex.string, lex.ext, expr.prim.literal, conv.ptr, conv.bool, topics/value-categories, topics/overload-resolution-walkthrough
tags: 字面量
updated: 2026-10-17
---

[[lex.literal]] 是第 5 章最长的部分，共九个小节。本页覆盖总览（[[lex.literal.kinds]]）和两个只有一段的小节：布尔字面量（[[lex.bool]]）与指针字面量（[[lex.nullptr]]）。其余各种字面量各有专页：

| 小节 | 字面量 | 页面 |
|---|---|---|
| 5.13.2 | 整数字面量 `42`、`0x2A`、`0b101`、`1'000uz` | [[lex.icon]] |
| 5.13.3 | 字符字面量 `'a'`、`u8'x'`、`L'w'`、`'\n'` | [[lex.ccon]] |
| 5.13.4 | 浮点字面量 `3.14`、`1e-9f`、`0x1p-3` | [[lex.fcon]] |
| 5.13.5–6 | 字符串字面量、原始字符串、不求值字符串 | [[lex.string]] |
| 5.13.7 | 布尔字面量 `true`、`false` | 本页 |
| 5.13.8 | 指针字面量 `nullptr` | 本页 |
| 5.13.9 | 用户定义字面量 `12_km`、`"abc"s` | [[lex.ext]] |

## 字面量的种类（[[lex.literal.kinds]]）

¶1 字面量有若干种：

```
literal:
    integer-literal
    character-literal
    floating-point-literal
    string-literal
    boolean-literal
    pointer-literal
    user-defined-literal
```

注 1：字面量作为表达式出现时，具有类型和值类别（[[expr.prim.literal]]）。

第 5 章只规定字面量的词法形式，以及（对大多数种类而言）它的类型和值；字面量作为表达式时的值类别由 [[expr.prim.literal]] 规定：

| 字面量 | 值类别 |
|---|---|
| *string-literal* | **左值**，指代对应的字符串字面量对象（[[lex.string#9]]） |
| *user-defined-literal* | 与对应的字面量运算符调用表达式相同（[[lex.ext]]） |
| 其他所有字面量 | 纯右值（prvalue） |

```cpp run title="literal-categories.cpp" ok
#include <type_traits>
#include <cstddef>
static_assert(std::is_same_v<decltype(("abc")), const char(&)[4]>);  // 左值：数组的引用
static_assert(std::is_same_v<decltype((42)), int>);                  // 纯右值
static_assert(std::is_same_v<decltype(true), bool>);
static_assert(std::is_same_v<decltype(nullptr), std::nullptr_t>);
const char (*p)[4] = &"abc";   // 可以对字符串字面量取地址：它是左值
int main() {}
```

### 负数不是字面量

文法里没有负号：`-1` 是一元运算符 `-` 作用于整数字面量 `1`。这个看似无关紧要的事实，导致了 [[lex.icon]] 中 `-2147483648` 的反常类型，也是 `INT_MIN` 通常被定义为 `(-2147483647 - 1)` 的原因。

### 字面量与常量表达式

字面量是词法概念，常量表达式是语义概念（[[expr.const]]）。`42` 是字面量，也是常量表达式；`"abc"` 是字面量，也是常量表达式（一个指代静态存储期对象的左值）；`std::numeric_limits<int>::max()` 是常量表达式，但不是字面量。字面类型（literal type，[[basic.types.general]]）则是另一个完全无关的概念，名字相似只是历史原因。

## 布尔字面量（[[lex.bool]]）

```
boolean-literal:
    false
    true
```

¶1 布尔字面量是关键字 `false` 和 `true`，类型为 `bool`。

值得注意的有几点：

- `true`、`false` 既是关键字也是字面量。它们在预处理器中也有特殊地位：在 `#if` 中，`true` 和 `false` 不会被替换为 0（[[cpp.cond]]），而其他关键字会。
- `true` 和 `false` 是 `bool` 纯右值，在整数提升中分别变为 `1` 和 `0`（[[conv.prom]]）。所以 `true + true == 2`。
- C 语言直到 C23 才把 `true`/`false` 变成关键字（此前它们是 `<stdbool.h>` 中的宏，值为 `int` 类型的 1 和 0）。

```cpp run title="bool-literal.cpp" ok
static_assert(true + true == 2);               // 提升为 int
static_assert(sizeof(true) == sizeof(bool));
#if true && !false                              // 预处理器认识 true/false
static_assert(true);
#endif
int main() {}
```

## 指针字面量（[[lex.nullptr]]）

```
pointer-literal:
    nullptr
```

¶1 指针字面量是关键字 `nullptr`，类型为 `std::nullptr_t`。注 1：`std::nullptr_t` 是一个独立的类型，既不是指针类型，也不是成员指针类型；它的纯右值是**空指针常量**，可以转换为空指针值或空成员指针值（[[conv.ptr]]、[[conv.mem]]）。

### 为什么需要 `nullptr`

在 C++11 之前，空指针常量只能是值为 0 的整数字面量（`0`、`0L`；实现常把 `NULL` 定义为 `0` 或编译器内建的 `__null`）。问题在于它的类型是整数：

```cpp title="null-overload.cpp" error
#include <cstddef>
void f(int);
void f(char*);
void g() {
  f(0);         // 调用 f(int)——多半不是程序员想要的
  f(NULL);      // 取决于 NULL 的定义：f(int)，或者有歧义（本例 Clang 报歧义）
  f(nullptr);   // OK：f(char*)，nullptr_t → char* 是指针转换，→ int 不可能
}
```

（标准只规定 `NULL` 是实现定义的空指针常量（[[support.types.nullptr]]）。在 Clang/libc++ 下 `NULL` 是 `__null`，此处调用有歧义，所以本例标为非良构。）

`nullptr` 的类型 `std::nullptr_t` 能隐式转换为任何指针类型和成员指针类型，但**不能**隐式转换为整数类型，它正是靠这一点解决了重载问题。在模板实参推导中，`nullptr` 推导出 `std::nullptr_t`，而 `0` 推导出 `int`，因此经过完美转发后，空指针的含义也能保留下来。

### `std::nullptr_t` 的性质

- `sizeof(std::nullptr_t) == sizeof(void*)`（[[basic.fundamental]]）。
- 它是标量类型；`decltype(nullptr)` 即 `std::nullptr_t`（`<cstddef>` 中就是这样定义的）。
- 可以定义 `std::nullptr_t` 类型的变量。[[conv.ptr]] 把空指针常量定义为值为零的整数字面量，或 `std::nullptr_t` 类型的纯右值，所以这种变量经左值到右值转换后，同样可以转换为任何指针类型。
- 转换为 `bool` 只允许在直接初始化中进行（[[conv.bool]]）：

```cpp title="nullptr-bool.cpp" error
bool a{nullptr};       // OK：直接初始化，值为 false
bool b = nullptr;      // error：拷贝初始化不允许 nullptr_t → bool
```

这条限制可以防止把 `if (p == nullptr)` 误写成 `bool flag = nullptr;` 这类错误而不被发现。

!!! history
    `nullptr` 在 C++11 引入（[[N2431]]）。C23 也引入了 `nullptr` 和 `nullptr_t`，语义与 C++ 基本一致。

## 陷阱

!!! pitfall "以为字符串字面量是右值"
    `"abc"` 是左值（`const char[4]` 类型的数组），所以可以取地址，也可以绑定到 `const char(&)[4]`。它在大多数上下文中会退化为 `const char*` 纯右值，那是数组到指针转换的结果。

!!! pitfall "以为 `nullptr` 是指针"
    `std::nullptr_t` 不是指针类型，`std::is_pointer_v<std::nullptr_t>` 为 `false`。不能对它解引用，`nullptr_t*` 和 `T*` 之间也没有转换。

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

## 小结

!!! summary
    - 字面量有七种：整数、字符、浮点、字符串、布尔、指针、用户定义。
    - 字符串字面量是左值；用户定义字面量的值类别与对应的运算符调用相同；其他字面量都是纯右值。
    - 负数不是字面量。
    - `true`/`false` 的类型是 `bool`，预处理器也认识它们。
    - `nullptr` 的类型是 `std::nullptr_t`（不是指针类型）；它是空指针常量，不能转换为整数，只在直接初始化中转换为 `bool`。
