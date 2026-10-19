---
title: 断言
summary: <cassert> 的 assert 宏：NDEBUG 决定它展开成什么，失败时打印诊断并 abort，C++26 起是可变参数宏，每次包含都按当时的 NDEBUG 重新定义，在常量求值中怎样工作，以及它与 contract_assert 的区别。
status: done
covers: *
papers: P2264R7
related: diagnostics, stmt.contract.assert, basic.contract, dcl.attr.assume, basic.def.odr, cpp.replace, expr.const
tags: 标准库, assert, NDEBUG, 契约, 宏
updated: 2026-10-19
---

!!! tldr
    - 包含 `<cassert>` 时如果定义了 `NDEBUG`，`assert(...)` 展开为 `((void)0)`，实参根本不求值；否则求值实参，为假时向标准错误输出诊断并调用 `abort()`。
    - C++26 起 `assert` 是可变参数宏，`assert(std::is_same_v<int, int>)` 不再需要额外的括号；但实参必须是单个赋值表达式，`assert(x, "msg")` 非良构。
    - `<cassert>` 每次被包含都按当时的 `NDEBUG` 重新定义 `assert`，可以在一个文件里局部开关断言。
    - `constexpr` 函数里可以用 `assert`：条件为真时不妨碍常量求值，为假时在编译期报错。
    - 不同翻译单元用不同的 `NDEBUG` 编译同一个 inline 函数，违反 ODR。C++26 的 `contract_assert` 没有这个问题。

## 失败时发生什么

```cpp run title="assert-fail.cpp" ok
#include <cassert>

int main() {
  int balance = -5;
  assert(balance >= 0 && "balance must be non-negative");
}
```

本机（macOS）运行时输出

```text
Assertion failed: (balance >= 0 && "balance must be non-negative"), function main, file assert-fail.cpp, line 5.
```

然后进程因 `SIGABRT` 终止。`&& "说明文字"` 是一个老惯用法：字符串字面量转换为 `bool` 恒为真，不影响结果，但会出现在打印出的表达式文本里。

[assertions.general] ¶1 说，`<cassert>` 提供一个用于记录程序断言的宏，以及通过定义宏 `NDEBUG` 来禁用断言检查的机制。断言首先是文档：它把程序员对程序状态的假设写成能执行的形式。

## 两种定义（[assertions.assert]）

¶1 如果在源文件中包含 `<cassert>` 的位置，`NDEBUG` 已被定义为宏名，`assert` 就定义为

```cpp
#define assert(...) ((void)0)
```

实参在预处理阶段就消失了，完全不求值。`assert(init_subsystem())` 在定义了 `NDEBUG` 的构建里意味着子系统根本不会初始化。

¶2 否则，`assert` 展开为一个 `void` 类型的表达式，效果是：

- ¶2.1 求值 `__VA_ARGS__`，并[[g:contextually-converted-to-bool|按语境转换为 `bool`]]；
- ¶2.2 结果为 `true` 时没有其他效果；
- ¶2.3 否则在标准错误流上输出一条格式由实现定义的诊断，然后调用 `abort()`。诊断包含 `#__VA_ARGS__`（实参的源代码文本），以及源文件名、行号、外围函数名，即 `source_location::current()` 能提供的那些信息。

调用的是 `abort()` 而不是 `exit()`：不运行 `atexit` 注册的函数，不析构静态对象，是否刷新 C 流的缓冲区由实现定义（[[support.start.term]]），通常还会产生 core dump。断言失败说明程序状态已经不可信，这时运行清理代码可能造成更大的破坏，core dump 则保留了现场。

## 实参里的逗号（¶3）{{c++26}}

C++26 之前，`assert` 只有一个宏形参。预处理器只认圆括号，不认尖括号和花括号，所以

```cpp
assert(std::is_same_v<int, int>);    // C++23：预处理器看到两个宏实参
assert(std::pair{1, 2} == p);        // 同样的问题
assert((std::is_same_v<int, int>));  // 传统的绕法：再加一层括号
```

C++26 把它改成 `assert(...)`（[[P2264R7]]，与 C23 一致），`__VA_ARGS__` 收下所有逗号。这又带来一个新问题：有人会模仿 `static_assert` 写 `assert(x, "message")`。这现在能通过预处理，展开后是逗号表达式，条件恒为字符串字面量转换出的 `true`，断言永远不会失败。¶3 堵上了这个漏洞：

!!! std
    If `__VA_ARGS__` does not expand to a well-formed *assignment-expression*, the program is ill-formed.

*assignment-expression* 是比 *expression* 低一级的语法产生式，不包含顶层的逗号运算符（[[expr.comma]]）。所以 `assert(x, "msg")` 非良构，而 `assert(std::is_same_v<int, int>)` 合法，因为模板实参列表里的逗号不是逗号运算符。

¶3 的第二句说，如果这个赋值表达式在作为不求值操作数处理时非良构，程序 {{ifndr}}。这给实现留出了检查手段：把实参放进 `sizeof`、`decltype` 这类不求值语境里，就能检查它是不是单个赋值表达式。`co_await`、`co_yield` 不能出现在不求值操作数中（[[expr.await]]、[[expr.yield]]），所以 `assert(co_await f())` 这种写法被定为 IFNDR，实现不必特殊处理。

!!! warning "实现状况"
    libc++ 的 `<cassert>` 直接使用平台 C 库的 `<assert.h>`，`assert` 的形式由 C 库决定。本机 macOS SDK 仍然定义单参数的 `assert(e)`，所以 `assert(std::is_same_v<int, int>)` 在本机报 "too many arguments provided to function-like macro invocation"。按标准它是合法的，平台还没有跟进。

!!! lawyer "定义了 `NDEBUG` 时怎样执行 ¶3"
    ¶3 没有区分是否定义了 `NDEBUG`。但 ¶1 规定这时宏恰好展开为 `((void)0)`，实参在预处理阶段就被丢弃，实现无从检查 `assert(x, "msg")` 是否是单个赋值表达式。实际上，各实现只能在没有定义 `NDEBUG` 时诊断这类错误。

## 每次包含都重新定义（¶4）

¶4 每次包含 `<cassert>`，`assert` 宏都按 `NDEBUG` 当时的状态重新定义。所以 `<cassert>` 没有包含保护，这是标准的规定。它允许在一个翻译单元里局部开关断言：

```cpp run title="ndebug-toggle.cpp" ok
#define NDEBUG
#include <cassert>
void hot_path([[maybe_unused]] int x) {
  assert(x > 0);    // 这里的 assert 被禁用
}

#undef NDEBUG
#include <cassert>
int main() {
  hot_path(-1);     // 不会触发
  assert(true);     // 这里的 assert 生效
}
```

## 常量求值中的 `assert`（¶5）

```cpp run title="constexpr-assert.cpp" ok
#include <cassert>

constexpr int checked_div(int a, int b) {
  assert(b != 0);
  return a / b;
}
static_assert(checked_div(6, 3) == 2);
// constexpr int bad = checked_div(1, 0);   // 编译错误

int main() { return checked_div(4, 2) - 2; }
```

¶5 规定，满足下列条件之一时，表达式 `assert(E)` 是[[g:constant-subexpression|常量子表达式]]：

- ¶5.1 在 `assert` 最后一次被定义或重新定义的位置，`NDEBUG` 已定义；
- ¶5.2 `E` 按语境转换为 `bool` 是一个求值为 `true` 的常量子表达式。

所以 `constexpr` 函数里可以放 `assert`。条件为真时它不妨碍常量求值；条件为假时要调用 `abort()`，这不是常量表达式，于是在编译期就报错。去掉上面那行注释，Clang 报 `bad` 必须由常量表达式初始化，并附注 assertion failed during evaluation of constant expression。同一份检查，在编译期是硬错误，在运行期是 `abort`。

## 与契约断言、`[[assume]]` 的区别

C++26 的契约断言包括函数上的 `pre`、`post` 和语句 `contract_assert`（[[stmt.contract.assert]]）。它们可以看作语言内建、修正了 `assert` 种种问题的断言：

| | `assert` | `contract_assert` |
|---|---|---|
| 本质 | 宏 | 语句 |
| 怎样开关 | 每个包含点的 `NDEBUG` | 实现定义的求值语义：ignore、observe、enforce、quick-enforce（[[basic.contract.eval]]） |
| 失败时 | 打印诊断，`abort()` | 按语义而定：observe 和 enforce 调用可替换的违约处理函数，enforce 和 quick-enforce 终止程序 |
| 实参里的逗号 | C++26 之前要加括号 | 没有问题 |
| 不同翻译单元设置不同 | 可能违反 ODR | 明确允许 |

最后一行需要解释。头文件里的 inline 函数用了 `assert`，一个翻译单元定义了 `NDEBUG`、另一个没有，这个函数在两个翻译单元里预处理后的记号序列就不同，违反单一定义规则（[[basic.def.odr]]），程序是 {{ifndr}}。链接器随便保留一个版本，结果可能是发布版里某些断言仍然生效，或者调试版里某些断言没有效果。契约断言的每次求值都可以采用不同的语义，没有这个问题。

`[[assume]]`（[[dcl.attr.assume]]）正好相反。它告诉编译器条件成立、可以据此优化，条件为假是未定义行为，而且从不检查。`assert` 启用时检查，禁用时什么也不做，不会让编译器据此优化。

截至写作时，本机 Clang 23 还不支持 `contract_assert`。

## 常见误解

!!! pitfall "实参里有副作用"
    `assert(fd = open(path))`、`assert(++count < limit)` 在定义了 `NDEBUG` 的构建里整条消失。断言的实参应当是没有副作用的条件。

!!! pitfall "用 `assert` 检查外部输入"
    用户输入、文件内容、网络数据出错是运行期错误，不是 bug。关闭断言后这些检查全部消失。外部输入应当用常规的错误处理，比如返回错误码或抛异常。

!!! pitfall "不同翻译单元的 `NDEBUG` 不一致"
    头文件里的 inline 函数、模板、`constexpr` 函数用了 `assert`，而各翻译单元用不同的 `NDEBUG` 设置编译，这是 IFNDR 的 ODR 违反。整个程序应当统一 `NDEBUG` 设置。

## 思考题

!!! question "思考题"
    1. `assert((x, y))`（两层括号）在 C++26 中良构吗？它检查的是什么？
    2. 程序在 `main` 之前的静态初始化期间断言失败，`abort()` 会运行已构造的静态对象的析构函数吗？
    3. 定义了 `NDEBUG` 时，`constexpr` 函数里的 `assert(E)` 靠 ¶5 的哪一项成为常量子表达式？

<details markdown="1">
<summary>答案</summary>

1. 良构。`(x, y)` 是带括号的表达式，属于 *assignment-expression*，括号里可以有逗号表达式。它检查的是 `y`，`x` 求值后被丢弃。这种有意的绕过写法 ¶3 拦不住。
2. 不会。`abort()` 不运行 `atexit` 注册的函数，也不析构静态存储期的对象（[[support.start.term]]）。
3. ¶5.1。`assert` 最后一次定义时 `NDEBUG` 已定义，`assert(E)` 展开为 `((void)0)`，总是常量子表达式。没有定义 `NDEBUG` 时，¶5.2 保证条件为真的 `assert` 也不妨碍常量求值。两项合起来，`assert` 可以放心地写进任何 `constexpr` 函数。
</details>
