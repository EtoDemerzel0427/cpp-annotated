---
title: 关键字
summary: 82 个保留为关键字的标识符（含 C++26 的 contract_assert）、import/module/export 占位关键字、属性记号中的例外，以及单词形式的替代记号。
status: draft
related: lex.name, lex.digraph, dcl.attr.grammar, cpp.replace.general, cpp.import
tags: 关键字, 词法
updated: 2026-10-17
---

[[lex.key]] 列出[[g:keyword|**关键字**]]（keyword）。在阶段 3–5，关键字和标识符都是 *identifier* 预处理记号；到阶段 6 转换为记号时，表 5 中的拼写才成为关键字。所以关键字这个概念只在阶段 6、7 有意义，这也解释了为什么在预处理器里 `#if int` 是合法的（`int` 被当作普通标识符替换为 0）。

## 文法

```
keyword:
    any identifier listed in Table 5
    import-keyword
    module-keyword
    export-keyword
```

*import-keyword*、*module-keyword*、*export-keyword* 是预处理器在处理 import / module 指令时产生的占位记号，没有拼写（[[lex.pptoken#4]]、[[cpp.import]]、[[cpp.module]]）。有了它们，语法就能区分作为模块指令一部分的 import 和名叫 import 的普通标识符。注意 `export` 在表 5 里也是普通关键字，*export-keyword* 则专指出现在模块指令开头的那个 `export`。

## ¶1：表 5

¶1 表 5 中的标识符保留作关键字，即在阶段 6 和 7 中无条件地当作关键字，只有在 *attribute-token* 中除外。注 1：`register` 关键字未被使用，但保留供将来使用。

当前草案共有 82 个关键字（按字母序）：

```
alignas      alignof      asm          auto         bool         break
case         catch        char         char8_t      char16_t     char32_t
class        co_await     co_return    co_yield     concept      const
const_cast   consteval    constexpr    constinit    continue     contract_assert
decltype     default      delete       do           double       dynamic_cast
else         enum         explicit     export       extern       false
float        for          friend       goto         if           inline
int          long         mutable      namespace    new          noexcept
nullptr      operator     private      protected    public       register
reinterpret_cast          requires     return       short        signed
sizeof       static       static_assert             static_cast  struct
switch       template     this         thread_local throw        true
try          typedef      typeid       typename     union        unsigned
using        virtual      void         volatile     wchar_t      while
```

下面这些不在表中，却常被误以为是关键字：

| 拼写 | 实际身份 |
|---|---|
| `override`、`final`、`import`、`module`、`pre`、`post` | 特殊含义标识符（[[lex.name#2]]） |
| `and`、`or`、`not`、`bitand`、`compl` … | 替代记号，即运算符/标点（[[lex.digraph]]、¶3） |
| `main` | 普通标识符，有特殊规则（[[basic.start.main]]） |
| `std` | 普通标识符（命名空间名，受库规则保留） |
| `size_t`、`nullptr_t`、`int8_t` | 库中的 typedef |
| `restrict`、`_Bool`、`_Atomic`、`typeof` | C 的关键字，C++ 中没有 |
| `__restrict`、`__attribute__`、`__declspec` | 实现扩展（使用保留标识符，[[lex.name#4]]） |

### 无条件：关键字永不作为标识符

无条件当作关键字，意味着关键字不能用作任何名字，即使在不会产生歧义的上下文中也不行：

```cpp title="keyword-as-name.cpp" error
struct S { int class; };      // error：class 是关键字
int contract_assert = 0;      // error（C++26）：contract_assert 是关键字
void f(int new);              // error
```

（实测 Clang 23 尚未把 `contract_assert` 识别为关键字，第二行能通过编译；这是实现进度问题。）

特殊含义标识符（`override` 等）与此不同，它们只在特定位置有特殊含义，在其他地方都是普通标识符。

### 例外：属性记号

*attribute-token*（如 `gnu::const` 中的 `const`）中的关键字不当作关键字。[[dcl.attr.grammar]] 进一步规定，属性记号中满足标识符语法要求的关键字或替代记号视为标识符。

```cpp run title="attr-keyword.cpp" ok
[[gnu::const]] int square(int x);      // const 在此是标识符
[[gnu::noreturn]] void die();
int main() {}
```

为什么要有这个例外？厂商属性（`gnu::const`、`gnu::noinline`、OpenMP 的 `omp::...` 等）的名字往往来自已有的编译器扩展，其中不少与 C++ 关键字同名；而属性记号所在的位置（`[[` … `]]` 内、作为属性名）本身没有歧义。

### `register`：未使用但保留

C++11 弃用了 `register` 存储类说明符，C++17 将其删除（`register int x;` 非良构）。但 `register` 仍在关键字表中，将来可以赋予它新含义而不破坏现有代码。`auto`（C++11 改义）和 `export`（C++11 移除导出模板，C++20 用于模块）走的都是这条路。

```cpp title="register.cpp" error
void f() {
  register int x = 0;   // error（C++17 起）：register 不再是存储类说明符
}
```

## ¶2：关键字不能作为宏名

¶2 注 2：关键字不能用作宏名（[[cpp.replace.general]]）。

```cpp title="keyword-macro.cpp" error
#define private public    // 当前草案：非良构（[cpp.replace.general]/9）
#include "header.h"       // 经典的"测试代码访问私有成员"黑魔法
```

这条规则的出处值得一提。在 C++23 中，该限制位于库条款 [[macro.names]]；当前草案把它移到了预处理条款 [[cpp.replace.general]] 第 9 段，作为一条普通的 shall not 规则，因此违反时需要诊断。它同样适用于特殊含义标识符和标准属性名（`likely`、`unlikely` 可以定义为函数式宏）。Clang 对此给出 `-Wkeyword-macro` 警告，警告也是诊断，满足必须诊断的要求。

为什么禁止？`#define private public` 会改变类的布局规则吗？在 C++23 之前，不同访问控制的成员之间的布局顺序可以由实现决定，把 `private` 换成 `public` 可能真的改变布局，导致 ODR 违规。更一般地，重定义关键字会让标准库头文件的行为完全不可预测。

## ¶3：替代表示保留

¶3 表 6 中某些运算符和标点的替代表示（[[lex.digraph]]）也是保留的，不得另作他用：

```
and     and_eq    bitand    bitor    compl    not
not_eq  or        or_eq     xor      xor_eq
```

它们不是关键字（不在表 5 中），而是 *operator-or-punctuator*；但效果上和关键字一样，不能用作名字。

## 历史与演进

!!! history
    | 版本 | 新增关键字 |
    |---|---|
    | C++98 | 基础集合（含 `export`、`register`、`auto` 的旧含义） |
    | C++11 | `alignas` `alignof` `char16_t` `char32_t` `constexpr` `decltype` `noexcept` `nullptr` `static_assert` `thread_local`（[[diff.cpp03.lex]]） |
    | C++20 | `char8_t` `concept` `consteval` `constinit` `co_await` `co_yield` `co_return` `requires`（[[diff.cpp17.lex]]） |
    | C++26 | `contract_assert`（[[diff.cpp23.lex]]，契约 [[P2900R14]]） |

    改义而未删除的有：`auto`（C++11 由存储类改为类型推导）、`export`（C++11 移除导出模板，C++20 用于模块）、`register`（C++17 移除存储类，保留拼写）。

    `contract_assert` 之所以不叫 `assert`，是因为 `assert` 是 `<cassert>` 中的宏，不可能成为关键字。契约的前置/后置条件则选用了特殊含义标识符 `pre`/`post` 而非关键字，以免破坏大量以 `pre`/`post` 为名的现有代码。

## 陷阱

!!! pitfall "C 代码里的变量名"
    C 代码中常用 `new`、`class`、`template`、`this`、`delete`、`private` 作变量名或结构体成员名，这些代码按 C++ 编译时全部会失败（[[diff.lex]]）。要在 C++ 中使用的 C 头文件，需要避开这些名字。

!!! pitfall "以为 `override` 是关键字"
    `int override = 0;` 完全合法。反过来，`struct S { int and; };` 非良构，因为 `and` 不是标识符。

## 思考题

!!! question "思考题"
    为什么 C++26 的契约把断言语句设计为关键字 `contract_assert`，而把前置/后置条件设计为特殊含义标识符 `pre`/`post`？

<details markdown="1">
<summary>答案</summary>

`pre`/`post` 出现在函数声明符之后（`int f(int x) pre(x > 0);`），这个位置原本只能出现 `override`、`final`、`noexcept`、`requires`、`= 0`、`{` 等少数几种东西，靠上下文就能识别，所以可以做成特殊含义标识符，避免破坏名为 `pre`/`post` 的现有变量。断言语句则出现在语句位置，在那里 `name(expr);` 本来就是合法的函数调用表达式语句，无法靠上下文区分，只能用关键字。为了不与现有代码（以及 `<cassert>` 的 `assert` 宏）冲突，标准选择了一个不太可能被用作名字的拼写 `contract_assert`。
</details>

## 小结

!!! summary
    - 关键字包括表 5 的 82 个拼写，加上三个没有拼写的模块占位关键字；它们只在阶段 6、7 存在。
    - 除属性记号外，表 5 的拼写无条件是关键字；关键字不能用作宏名（当前草案中这是一条需要诊断的规则）。
    - 单词形式的替代记号同样保留，但它们是运算符记号而非关键字。
    - C++26 新增 `contract_assert`；`pre`/`post` 是特殊含义标识符。
