---
title: 替代记号
summary: <% %> <: :> %: %:%: 这些双字符组，以及 and、or、not、bitand、compl 等单词形式，除了拼写之外与对应的运算符和标点完全相同。
status: done
related: lex.pptoken, lex.operators, lex.key, cpp.stringize, cpp.replace.general
tags: 词法, 双字符组
updated: 2026-10-19
---

!!! tldr
    - `<%` `%>` `<:` `:>` `%:` `%:%:` 和 `and`、`or`、`not`、`bitand`、`compl` 等 11 个单词，是某些运算符和标点的另一种拼写。
    - 替代记号与它对应的记号在语言的一切方面都相同，只有字符串化时保留原来的拼写。
    - `and` 就是 `&&` 这个记号，所以 `int and r = 1;` 声明的是右值引用，`compl X()` 是析构函数。
    - 单词形式既不是标识符也不是关键字，不能用作变量名，也不能定义成宏。

## 不只是逻辑运算

```cpp run title="alt-everywhere.cpp" ok
struct X {
  X() = default;
  compl X() {}               // ~X()：析构函数
  void f() bitand {}         // void f() &：左值引用限定的成员函数
  void g() and {}            // void g() &&：右值引用限定
};
int x = 0;
int bitand r = x;            // int& r：左值引用
int and rr = 1;              // int&& rr：右值引用
int* p = bitand x;           // &x：取地址
bool b = not x or x not_eq 0;
int main() <%
  X{}.g();
  int a<:2:> = <%1, 2%>;
  return a<:0:> xor 1;       // 1 ^ 1 == 0
%>
```

这段代码全部良构，本机 Clang 23 以 `-Wall -Wextra -pedantic` 编译没有任何诊断。`and` 不表示逻辑与运算，它就是 `&&` 这个记号，所以语法里凡是能写 `&&` 的地方都能写 `and`，包括引用声明和引用限定符。

¶1 标准为部分运算符和标点提供了**替代记号**（[[g:alternative-token|alternative token]]）表示。它们最初是为缺少 `{ } [ ] # | ^ ~` 等字符的键盘和字符集（例如 ISO 646 的一些国家变体）准备的。今天几乎没人因为键盘而用它们，但它们仍是语言的一部分。

脚注 10 说，双字符组（digraph）这个叫法不太准确，因为 `%:%:` 有四个字符，而很多普通记号本身也是两个字符；不过习惯上，不属于词法关键字的那几个替代记号都叫双字符组。

## 只有拼写不同（¶2）

!!! std
    In all respects of the language, each alternative token behaves the same, respectively, as its primary token, except for its spelling.

¶2 每个替代记号在语言的一切方面都与对应的**主记号**（primary token）相同，只有拼写不同。完整的对应关系是表 3：

| 替代 | 主记号 | 替代 | 主记号 | 替代 | 主记号 |
|---|---|---|---|---|---|
| `<%` | `{` | `and` | `&&` | `and_eq` | `&=` |
| `%>` | `}` | `bitor` | `|` | `or_eq` | `|=` |
| `<:` | `[` | `or` | `||` | `xor_eq` | `^=` |
| `:>` | `]` | `xor` | `^` | `not` | `!` |
| `%:` | `#` | `compl` | `~` | `not_eq` | `!=` |
| `%:%:` | `##` | `bitand` | `&` | | |

注 1 指出了唯一能看出区别的地方：字符串化（[[cpp.stringize]]）保留源码里的拼写，`[` 和 `<:` 字符串化的结果不同。

```cpp run title="stringize.cpp" ok
#define S(t) #t
static_assert(S(<:)[0] == '<');   // "<:"
static_assert(S([)[0] == '[');    // "["
static_assert(S(and)[0] == 'a');  // "and"
int main() {}
```

`%:` 和 `%:%:` 也一样：`%:` 可以在行首引导预处理指令，也可以在宏定义里字符串化；`%:%:` 可以拼接记号。

```cpp run title="percent-colon.cpp" ok
%:include <cstdio>
%:define CAT(a, b) a %:%: b
%:define STR(x) %:x
int main() { std::puts(STR(CAT(he, llo))); }   // 打印 CAT(he, llo)：# 不展开实参
```

## 单词形式不是标识符

[[lex.key#3]] 规定，`and`、`and_eq`、`bitand`、`bitor`、`compl`、`not`、`not_eq`、`or`、`or_eq`、`xor`、`xor_eq` 是保留的，不能另作他用。它们在阶段 3 就被切成运算符或标点（[[lex.operators]]），而不是标识符。所以：

- 它们不能用作变量名、函数名等任何名字；
- 它们不能定义成宏。`#define` 后面要求一个标识符，[[cpp.replace.general]] 的注 1 说，替代记号即使全由字母和下划线组成也不是标识符；
- 它们能出现在主记号能出现的任何位置，例如 `operator and` 和 `operator&&` 是同一个函数名。

```cpp title="alt-macro.cpp" error
#define and &&     // error: and 不是标识符，不能作为宏名
int not = 0;       // error: not 不是标识符
```

本机 Clang 23 对第一行报告 C++ operator 'and' (aka '&&') used as a macro name。

脚注 10 把单词形式称为词法关键字（lexical keywords），[[diff.header.iso646.h]] 也说它们在 C++ 中是关键字。但它们不在关键字表（[[lex.key]] 表 5）里，文法上属于 *operator-or-punctuator*。效果上，它们和关键字一样不能用作名字。

## 与 C 的关系

C 语言里，`and`、`or` 等是 `<iso646.h>` 定义的宏；C++ 里它们是记号，`<iso646.h>` 什么也不定义。C++20 删除了 `<ciso646>`，这个头文件过去常被当作最小的标准库头文件包含进来，以获取库的版本宏，这个用途现在由 `<version>` 取代。双字符组 `<% %> <: :> %: %:%:` 在 C 中也是记号。

!!! impl "实现视角"
    GCC 和 Clang 在所有标准模式下都识别单词形式。MSVC 历史上默认不识别 `and`、`or` 等，需要包含 `<iso646.h>` 取得宏，只在符合性模式下按标准处理。跨编译器的代码如果用到它们，要确认 MSVC 所用的模式。

## 三字符组：已经删除的第三种拼写

C++14 及以前还有 9 个三字符组（trigraph），如 `??=`、`??/`、`??!`。它们和替代记号有本质区别。三字符组在阶段 1 做纯字符替换，在字符串字面量和注释里也生效；替代记号是阶段 3 的记号，在字面量里没有特殊含义。三字符组替换的范围太大，会把 `"what??!"` 变成 `"what|"`，因此 C++17 把它删除了（[[N4086]]，见 [[lex.phases]]），替代记号则保留下来。

## 常见误解

!!! pitfall "`and` 只能用于逻辑运算"
    `int and x = 1;` 声明了一个右值引用。代码里看到 `bitand`、`compl` 出现在奇怪的位置，不一定是笔误。

!!! pitfall "`<::` 总会被当成 `[:`"
    C++03 中 `std::vector<::std::string>` 被切成 `vector [ :std::string >`，必须写成 `< ::std`。C++11 加入了 [[lex.pptoken#5]] 的 `<::` 例外，现在这样写没有问题。

## 思考题

!!! question "思考题"
    `operator and` 和 `operator&&` 是不是同一个函数名？`S(and)` 和 `S(&&)`（`S` 是字符串化宏）呢？

<details markdown="1">
<summary>答案</summary>

`operator and` 和 `operator&&` 是同一个运算符函数名，因为 `and` 和 `&&` 是同一个记号（¶2）。在类里声明 `bool operator&&(X);`，再在类外定义 `bool X::operator and(X) { ... }`，完全合法。

字符串化保留拼写：`S(and)` 是 `"and"`，`S(&&)` 是 `"&&"`，两者不同。这正是 ¶2 注 1 指出的唯一区别。
</details>
