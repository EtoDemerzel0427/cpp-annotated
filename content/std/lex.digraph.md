---
title: 替代记号
summary: <% %> <: :> %: %:%: 等双字符组，以及 and、or、not、bitand、compl 等单词形式的运算符：它们在除拼写外的一切方面与主记号相同。
status: draft
related: lex.pptoken, lex.operators, lex.key, cpp.stringize, cpp.replace.general
tags: 词法, 双字符组
updated: 2026-10-17
---

[[lex.digraph]] 为部分运算符和标点提供了[[g:alternative-token|**替代记号**]]（alternative token）表示。它们最初是为了让 C/C++ 能在缺少 `{ } [ ] # | ^ ~` 等字符的键盘和字符集（如 ISO 646 的某些国家变体）上书写。今天几乎没人因为键盘而使用它们，但它们仍然是语言的一部分，而且会以意想不到的方式出现——尤其是 `<:` 和 `and`。

## ¶1–¶2：与主记号完全等价

¶1 为部分运算符和标点提供替代记号表示。脚注 10 解释了名字："双字符组"（digraph）并不准确——`%:%:` 有四个字符，而许多主记号本身也是两个字符；但那些不是词法关键字的替代记号仍被俗称为"双字符组"。

¶2 在语言的**所有方面**，每个替代记号的行为都与其主记号相同，**除了拼写**。注 1：`[` 与 `<:` 的"字符串化"值（[[cpp.stringize]]）不同，保持源码拼写。

!!! std
    In all respects of the language, each alternative token behaves the same, respectively, as its primary token, except for its spelling.

    替代记号与主记号是同一个记号，只是写法不同。

表 3（替代记号）：

| 替代 | 主记号 | 替代 | 主记号 | 替代 | 主记号 |
|---|---|---|---|---|---|
| `<%` | `{` | `and` | `&&` | `and_eq` | `&=` |
| `%>` | `}` | `bitor` | `|` | `or_eq` | `|=` |
| `<:` | `[` | `or` | `||` | `xor_eq` | `^=` |
| `:>` | `]` | `xor` | `^` | `not` | `!` |
| `%:` | `#` | `compl` | `~` | `not_eq` | `!=` |
| `%:%:` | `##` | `bitand` | `&` | | |

## "在所有方面"意味着什么

`and` 就是 `&&` 这个**记号**，不是"逻辑与运算"。所以凡是语法里出现 `&&` 记号的地方都能写 `and`——包括与逻辑运算毫无关系的地方：

```cpp run title="alt-everywhere.cpp" ok
struct X {
  X() = default;
  compl X() {}               // ~X()：析构函数
  void f() bitand {}         // void f() &   ：左值引用限定的成员函数
  void g() and {}            // void g() &&  ：右值引用限定
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

以上全部良构（Clang 23 以 `-Wall -Wextra -pedantic` 编译无任何诊断）。这说明替代记号是**词法层面**的替换：阶段 3 产生的记号与主记号相同，此后没有任何规则能区分它们——唯一的例外是字符串化。

```cpp run title="stringize.cpp" ok
#define S(t) #t
static_assert(S(<:)[0] == '<');   // "<:"
static_assert(S([)[0] == '[');    // "["
static_assert(S(and)[0] == 'a');  // "and"
int main() {}
```

## `%:` 也是预处理指令的引导符

`%:` 等价于 `#`，`%:%:` 等价于 `##`——包括在行首引导预处理指令、在宏定义中字符串化和拼接：

```cpp run title="percent-colon.cpp" ok
%:include <cstdio>
%:define CAT(a, b) a %:%: b
%:define STR(x) %:x
int main() { std::puts(STR(CAT(he, llo))); }   // 打印 CAT(he, llo)：# 不展开实参
```

## 单词形式的替代记号不是标识符

[[lex.key#3]] 规定表 6 中的单词形式（`and`、`and_eq`、`bitand`、`bitor`、`compl`、`not`、`not_eq`、`or`、`or_eq`、`xor`、`xor_eq`）是**保留的，不得另作他用**。它们在阶段 3 就被识别为 *preprocessing-op-or-punc*，而不是 *identifier*。由此：

- 不能用作变量名、函数名等任何名字；
- **不能定义为宏名**：[[cpp.replace.general]] 的注说，替代记号即使拼写全由字母和下划线构成也不是标识符，所以不可能定义同名的宏（`#define` 后面要求的是标识符）；
- 但它们可以出现在任何主记号能出现的位置，例如 `operator and` 就是合法的运算符函数名，与 `operator&&` 是同一个记号序列。

```cpp title="alt-macro.cpp" error
#define and &&     // error：and 不是标识符，不能作为宏名
int not = 0;       // error：not 不是标识符
```

!!! lawyer "Annex C 说它们是\"关键字\""
    [[diff.header.iso646.h]] 写道：这些记号"在 C++ 中是关键字"，因此 `<iso646.h>` 不把它们引入为宏。但在第 5 章的分类里，它们既不在关键字表（[[lex.key]] 表 5）中，也不是 *identifier*，而是 *operator-or-punctuator*（[[lex.operators]]）。Annex C 是参考性（informative）的，这里的措辞是非正式的；规范性的分类以第 5 章为准。

## 与 C 的关系

C 语言中，`and`、`or` 等是 `<iso646.h>` 中定义的**宏**；C++ 中它们是记号，`<iso646.h>`（以及 C++20 前的 `<ciso646>`）在 C++ 中不定义任何东西。C++20 删除了 `<ciso646>`（它过去常被用来"包含一个最小的库头文件以获取库版本宏"，这个用途现在由 `<version>` 取代）。

双字符组 `<% %> <: :> %: %:%:` 在 C 中（C95 起）是记号，与 C++ 相同。

!!! impl "实现视角"
    - GCC、Clang 在所有标准模式下都识别单词形式的替代记号。
    - MSVC 历史上默认**不**把 `and`、`or` 等识别为记号（需要包含 `<iso646.h>` 获取宏），只在符合性模式（如 `/permissive-` 或更早的 `/Za`）下按标准处理。写跨编译器代码时若使用它们，最好确认目标 MSVC 的模式。
    - Clang 对把替代记号用作宏名给出错误（"C++ operator 'and' (aka '&&') used as a macro name"）。

## 三字符组：已删除的"第三种拼写"

C++14 及以前还有 9 个**三字符组**（trigraph）：`??=` `??/` `??'` `??(` `??)` `??!` `??<` `??>` `??-`。它们与替代记号本质不同：三字符组在**阶段 1** 做纯字符替换，在字符串字面量和注释中**也**生效；替代记号则是阶段 3 的**记号**，在字面量中没有任何特殊含义。三字符组的替换范围过大，带来了 `"what??!"` 变成 `"what|"` 一类事故，于是在 C++17 被删除（[[N4086]]，见 [[lex.phases]]）。替代记号则被保留。

## 陷阱

!!! pitfall "`<::` 的历史坑"
    C++03 中 `std::vector<::std::string>` 被切成 `vector [ :std::string >`，编译失败，必须写 `< ::std`。C++11 加入了 [[lex.pptoken#5]] 的 `<::` 例外。

!!! pitfall "以为 `and` 只能用于逻辑运算"
    `int and x = 1;` 声明了一个右值引用。代码审查时看到奇怪的 `bitand`、`compl` 不要以为是笔误。

## 思考题

!!! question "思考题"
    `operator and` 和 `operator&&` 是不是同一个函数名？`std::string("and")` 和 `std::string(S(&&))`（`S` 为字符串化宏）呢？

<details markdown="1">
<summary>答案</summary>

`operator and` 与 `operator&&` 是同一个 *operator-function-id*，因为 `and` 与 `&&` 是同一个记号（¶2）。在类中先声明 `bool operator&&(X);` 再定义 `bool X::operator and(X) {...}` 完全合法。

而字符串化保留拼写：`S(and)` 是 `"and"`，`S(&&)` 是 `"&&"`，两个字符串不同。这正是 ¶2 注 1 指出的唯一区别。
</details>

## 小结

!!! summary
    - 替代记号：`<% %> <: :> %: %:%:` 与 11 个单词形式；与主记号在一切方面相同，只有字符串化保留拼写。
    - 单词形式不是标识符也不是关键字，不能作为名字或宏名。
    - `and`、`bitand`、`compl` 等可以用于引用声明、引用限定符、析构函数——任何主记号能出现的地方。
    - 三字符组（阶段 1 的字符替换）已于 C++17 删除；替代记号（阶段 3 的记号）保留。
