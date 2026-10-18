---
title: 断言
summary: <cassert> 的 assert 宏：NDEBUG 控制下的两种定义、失败时的诊断与 abort、C++26 的可变参数形式（解决模板实参中的逗号）、每次包含都按当时的 NDEBUG 重新定义、在常量求值中的行为，以及它与 C++26 契约（contract_assert）的关系和 ODR 隐患。
status: done
covers: *
papers: P2264R7
related: diagnostics, stmt.contract.assert, basic.contract, dcl.attr.assume, basic.def.odr, cpp.replace, expr.const
tags: 标准库, assert, NDEBUG, 契约, 宏
updated: 2026-10-18
---

`assert` 是 C 语言留下来的最朴素的诊断工具：一个宏，检查一个条件，失败就打印一行信息并 `abort()`。它的全部"魔法"都来自预处理器——这也正是它的局限所在，以及 C++26 引入契约（[[basic.contract]]）的动机之一。

## 概述与概要（[assertions.general]、[cassert.syn]）

[assertions.general] ¶1：`<cassert>` 提供一个用于**记录**程序断言的宏，以及一个通过定义宏 `NDEBUG` 来**禁用**断言检查的机制。

注意"documenting"一词：断言首先是**文档**——它把程序员对程序状态的假设写成可执行的形式。

概要只有一行：

```cpp
#define assert(...) see below
```

{{c++26}} 从 C++26 起，`assert` 是一个**可变参数宏**（[[P2264R7]]，与 C23 同步）。在此之前它的形式是 `assert(expression)`，只接受一个宏实参。

## 两种定义（[assertions.assert] ¶1–¶2）

### 定义了 `NDEBUG`：什么也不做（¶1）

若在包含 `<cassert>` 的位置 `NDEBUG` 已被定义为宏名，`assert` 被定义为：

```cpp
#define assert(...) ((void)0)
```

关键后果：**实参完全不被求值**——它在预处理阶段就消失了。`assert(init_subsystem())` 在发布版本中意味着子系统根本不会被初始化。

### 未定义 `NDEBUG`：诊断测试（¶2）

否则，`assert` 展开为一个 `void` 类型的表达式，效果是：

- ¶2.1：对 `__VA_ARGS__` 求值并**按语境转换为 `bool`**（[[g:contextually-converted-to-bool]]）；
- ¶2.2：结果为 `true` 时没有进一步效果；
- ¶2.3：否则，在**标准错误流**上产生一条诊断信息（格式**由实现定义**），然后调用 `abort()`。诊断信息包含 `#__VA_ARGS__`（实参的字符串化文本）以及源文件名、行号、外围函数名（例如 `source_location::current()` 所提供的那些信息）。

调用的是 `abort()` 而不是 `exit()`：不运行 `atexit` 处理函数，不析构静态对象，不刷新 C 流缓冲区（是否刷新由实现定义），通常产生 core dump（[[support.start.term]]）。这是刻意的——断言失败意味着程序状态已经不可信，运行任何清理代码都可能造成更大破坏，而 core dump 保留了现场。

```cpp run title="assert-fail.cpp" ok
#include <cassert>

int main() {
    int balance = -5;
    assert(balance >= 0 && "balance must be non-negative");
    // macOS/libc 上输出：
    // Assertion failed: (balance >= 0 && "balance must be non-negative"), function main, file assert-fail.cpp, line 5.
    // 随后 abort()，进程以 SIGABRT 终止
}
```

（"条件 `&& "说明文字"`"是一个老惯用法：字符串字面量转换为 `bool` 恒为真，不影响结果，但会出现在 `#__VA_ARGS__` 的文本里。）

## 可变参数与"逗号问题"（¶3）

C++26 之前，`assert` 只有一个宏形参，而预处理器只认圆括号，不认尖括号和花括号。于是：

```cpp
assert(std::is_same_v<int, int>);      // C++23：错误！预处理器看到两个宏实参
assert(std::pair{1, 2} == p);          // 同样的问题
assert((std::is_same_v<int, int>));    // 传统的绕法：多加一层括号
```

C++26 把它改为 `assert(...)`，`__VA_ARGS__` 吞下所有逗号。但这引入了新问题：`assert(x, "message")` 这种（错误地模仿 `static_assert` 的）写法现在会被预处理器接受，展开后变成逗号表达式，条件总是 `"message"` 转换出的 `true`——断言永远不会失败。¶3 堵住了这个洞：

!!! std
    If `__VA_ARGS__` does not expand to a well-formed *assignment-expression*, the program is ill-formed.

    若 `__VA_ARGS__` 展开的结果不是一个良构的**赋值表达式**（*assignment-expression*），程序非良构。

*assignment-expression* 是比 *expression* 低一级的文法产生式——它**不包含顶层逗号运算符**（[[expr.comma]]）。所以 `assert(x, "msg")` 非良构，而 `assert(std::is_same_v<int, int>)` 合法（模板实参列表里的逗号不是逗号运算符）。

¶3 的第二句：如果这个赋值表达式在作为**不求值操作数**处理时非良构（[[expr.await]]、[[expr.yield]]），程序 {{ifndr}}。这一句为实现留出了手段：实现可以把实参放进 `sizeof`/`decltype` 之类的不求值语境来检查它是否构成单个赋值表达式；而 `co_await`、`co_yield` 不能出现在不求值操作数中，于是 `assert(co_await f())` 这种写法被宣布为 IFNDR，不要求实现为它特殊处理。

!!! warning "实现状况"
    libc++ 的 `<cassert>` 只是包含平台 C 库的 `<assert.h>`；`assert` 宏的形态由 C 库决定。本机 macOS SDK 的 `<assert.h>` 仍定义单参数的 `assert(e)`，所以下面的代码在 Clang 23 + libc++ + macOS 上会报"too many arguments provided to function-like macro invocation"——标准规定它合法，但平台尚未跟进：

    ```cpp
    #include <cassert>
    #include <type_traits>
    int main() { assert(std::is_same_v<int, int>); }   // C++26：OK；本机：宏实参过多
    ```

!!! lawyer "NDEBUG 下 ¶3 如何执行？"
    ¶3 的措辞没有区分是否定义了 `NDEBUG`，但 ¶1 规定 `NDEBUG` 下宏恰好展开为 `((void)0)`——实参在预处理阶段就被丢弃，实现无从检查 `assert(x, "msg")` 是否构成单个赋值表达式。实际上各实现只能在未定义 `NDEBUG` 时诊断这类错误。

## 每次包含都重新定义（¶4）

!!! std
    The macro assert is redefined according to the current state of NDEBUG each time that `<cassert>` is included.

    每次包含 `<cassert>`，`assert` 宏都按 `NDEBUG` **当时**的状态重新定义。

`<cassert>` 是标准库中少有的**没有**包含保护（include guard）的头文件——这是规定，不是疏忽。它允许在一个翻译单元内局部地开关断言：

```cpp run title="ndebug-toggle.cpp" ok
#define NDEBUG
#include <cassert>
void hot_path([[maybe_unused]] int x) { assert(x > 0); }   // 此处 assert 被禁用

#undef NDEBUG
#include <cassert>
int main() {
    hot_path(-1);   // 不会触发
    assert(true);   // 此处 assert 生效
}
```

## 常量求值中的 `assert`（¶5）

¶5：表达式 `assert(E)` 是**常量子表达式**（[[g:constant-subexpression]]），如果

- ¶5.1：在 `assert` 最后一次被定义或重新定义的位置，`NDEBUG` 已定义；或
- ¶5.2：`E` 按语境转换为 `bool` 是一个求值为 `true` 的常量子表达式。

换言之，`constexpr` 函数里可以放 `assert`：检查通过时它不妨碍常量求值；检查失败时，调用 `abort()` 不是常量表达式，于是**在编译期**就得到错误。

```cpp run title="constexpr-assert.cpp" ok
#include <cassert>

constexpr int checked_div(int a, int b) {
    assert(b != 0);
    return a / b;
}
static_assert(checked_div(6, 3) == 2);
// constexpr int bad = checked_div(1, 0);
//   error: constexpr variable 'bad' must be initialized by a constant expression
//   note: assertion failed during evaluation of constant expression

int main() { return checked_div(4, 2) - 2; }
```

这使得 `assert` 成为 `constexpr` 代码中检查前置条件的一种廉价方式：同一份检查在编译期是硬错误，在运行期是 `abort`。

## 与契约（contracts）的关系

C++26 引入了**契约断言**：函数上的 `pre`/`post`，以及语句 `contract_assert(...)`（[[stmt.contract.assert]]）。它们在很多方面就是"语言内建的、做对了的 `assert`"：

| | `assert` | `contract_assert` |
|---|---|---|
| 本质 | 宏（预处理器） | 语句（核心语言） |
| 开关方式 | 每个包含点的 `NDEBUG` | 由实现定义的**求值语义**：ignore / observe / enforce / quick-enforce（[[basic.contract]]） |
| 失败时 | 打印并 `abort()` | 调用**违约处理函数**（可替换），之后按语义决定是否终止 |
| 实参中的逗号 | C++26 前需加括号 | 无问题（不是宏） |
| 跨 TU 不同设置 | 可能违反 ODR | 明确允许不同 TU 使用不同求值语义 |
| 常量求值 | ¶5：失败即非常量表达式 | 有专门规则（[[basic.contract]]） |

最后一行值得展开。如果头文件中的 `inline` 函数使用了 `assert`，而两个翻译单元一个定义了 `NDEBUG`、一个没有，那么该函数在两个 TU 中预处理后的**记号序列不同**——这违反了单一定义规则（[[basic.def.odr]]），程序 {{ifndr}}。链接器会随便挑一个版本，于是"发布版里某些断言仍然生效、或调试版里某些断言神秘失效"。契约的设计明确允许混合求值语义，避免了这个问题。

与 `[[assume]]`（[[dcl.attr.assume]]）的区别则正好相反：`assume` 告诉编译器"这个条件为真，你可以据此优化"，条件为假是 UB，**从不检查**；`assert` 在启用时检查、禁用时什么都不做，**从不**让编译器据此优化。

!!! warning "编译器支持"
    截至本文编写时，本机 Clang 23 尚不支持 `contract_assert`（报"use of undeclared identifier"）。

## 陷阱

!!! pitfall "实参中的副作用"
    `assert(fd = open(path))`、`assert(it != m.erase(k))`、`assert(++count < limit)`——这些在定义 `NDEBUG` 的构建中整条消失。断言实参必须是**无副作用**的纯条件。

!!! pitfall "用 assert 校验外部输入"
    用户输入、文件内容、网络数据的错误是**运行期错误**，不是 bug。发布版关闭断言后，这些检查全部消失。外部输入应当用常规的错误处理（返回错误码、抛异常）。

!!! pitfall "NDEBUG 与 ODR"
    在头文件的 `inline` 函数、模板、`constexpr` 函数中使用 `assert`，并让不同翻译单元以不同的 `NDEBUG` 设置编译——这是 IFNDR 的 ODR 违反。整个程序应当统一 `NDEBUG` 设置。

## 思考题

!!! question "思考题"
    1. `assert((x, y))`（双层括号）在 C++26 中是否良构？它检查的是什么？
    2. 一个程序在 `main` 之前（静态初始化期间）断言失败，`abort()` 会运行已构造的静态对象的析构函数吗？
    3. 在 `constexpr` 函数中使用 `assert`，且该函数只在运行期被调用、定义了 `NDEBUG`——¶5 的哪一条使得 `assert(E)` 是常量子表达式？这有什么意义？

<details markdown="1">
<summary>展开查看答案与解析</summary>

1. 良构。`(x, y)` 是一个带括号的*主表达式*，属于 *assignment-expression*（括号内可以有逗号表达式）。它检查的是 `y`（逗号运算符的结果），`x` 被求值后丢弃。这正是 ¶3 无法阻止的"故意绕过"写法。
2. 不会。`abort()` 不运行 `atexit` 注册的函数，也不析构具有静态存储期的对象（[[support.start.term]]）。
3. ¶5.1：`NDEBUG` 在 `assert` 最后一次定义时已定义，所以 `assert(E)` 展开为 `((void)0)`，总是常量子表达式。意义在于：同一个 `constexpr` 函数在发布配置下仍然可以用于常量求值，不会因为 `assert` 的存在而在常量求值中失败；而在未定义 `NDEBUG` 的配置下，¶5.2 保证条件为真时同样不妨碍常量求值。两条合起来，使 `assert` 可以放心地写进任何 `constexpr` 函数。
</details>

## 小结

!!! summary
    - `NDEBUG` 已定义：`assert(...)` 恰好展开为 `((void)0)`，实参不求值；否则求值、按语境转 `bool`，为假时打印（含表达式文本、文件、行、函数）并 `abort()`。
    - {{c++26}} `assert(...)` 是可变参数宏；实参必须是单个*赋值表达式*，`assert(x, "msg")` 非良构。本机 macOS C 库尚未跟进。
    - `<cassert>` 每次包含都按当前 `NDEBUG` 重定义，可以在 TU 内局部开关。
    - `constexpr` 中可用：通过时不妨碍常量求值，失败时成为编译错误。
    - 不同 TU 的 `NDEBUG` 设置不一致会导致 ODR 违反；C++26 的 `contract_assert` 是语言级的替代品。
