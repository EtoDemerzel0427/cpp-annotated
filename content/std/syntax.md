---
title: 语法表示法
summary: 怎样读标准里的语法产生式：非终结符与终结符、每行一个备选、one of、下标 opt，以及 -name、-id、-seq、-list 这几个后缀；再用几条真实的产生式回答优先级、声明怎么读这类实际问题。
status: done
related: intro.structure, gram, lex.pptoken, stmt.ambig, topics/how-to-read-the-standard
tags: 语法, 导读
updated: 2026-10-18
---

!!! tldr
    - 产生式冒号前是被定义的语法类别，下面每一行是一个备选；斜体词是其他语法类别，等宽的词和符号要原样写出，下标 opt 表示可以省略。
    - 名字的后缀有固定含义：-seq 是若干个连写，-list 是若干个用逗号隔开，-name 要靠名字查找才能确定，-id 不依赖上下文。
    - 标准里没有运算符优先级表，优先级和结合性由表达式产生式的嵌套关系决定。
    - 声明符的产生式说明了为什么声明要从名字开始、由内向外读。
    - 符合语法不等于合法。歧义消解、名字查找和类型规则还会排除大量合乎语法的代码。

## 读一条产生式（¶1）

`if` 语句的语法写在 [[stmt.select.general]]：

```text
selection-statement:
    if constexpr_opt ( init-statement_opt condition ) statement
    if constexpr_opt ( init-statement_opt condition ) statement else statement
    if !_opt consteval compound-statement
    if !_opt consteval compound-statement else statement
    switch ( init-statement_opt condition ) statement
```

第一行冒号前的 *selection-statement* 是这条产生式定义的语法类别。下面缩进的每一行是一个备选，代码只要符合其中一行就是一个 *selection-statement*。

行里的词分两种。*init-statement*、*condition*、*statement* 这类带连字符的小写词是其他语法类别，也叫非终结符，各有自己的产生式。`if`、`constexpr`、`(`、`else` 是终结符，必须在源码里原样出现。带 `_opt` 的成分可以省略。

¶1 这就是 [syntax] 规定的记法。在标准原文里：

- 语法类别用斜体无衬线字体，如 *expression*；终结符用等宽字体，如 `if`、`::`；
- 备选项分行列出，备选项很多时用 one of 标出，几个备选写在同一行；
- 一个备选太长、一行写不下时，接续行比首行多缩进一些；
- 可以省略的成分加下标 opt，例如 { *expression*<sub>opt</sub> } 表示花括号里可以有一个表达式，也可以没有。

!!! tip "本站的写法"
    eel.is 上 opt 显示为下标。把产生式复制成纯文本时，下标会和前面的词粘在一起，变成 `expressionopt`、`constexpropt`。本站在代码块中写作 `expression_opt`，并去掉斜体。

one of 的例子是 [[expr.assign]] 中的赋值运算符，同一行里每个记号都是一个独立的备选：

```text
assignment-operator: one of
    =  *=  /=  %=  +=  -=  >>=  <<=  &=  ^=  |=
```

接续行的例子是 [[dcl.decl.general]] 中的 *parameters-and-qualifiers*，第二行多缩进了一层，它和第一行合起来是同一个备选：

```text
parameters-and-qualifiers:
    ( parameter-declaration-clause ) cv-qualifier-seq_opt
        ref-qualifier_opt noexcept-specifier_opt attribute-specifier-seq_opt
```

### 从 selection-statement 能读出什么

回到 `if` 的产生式，逐项看：

- `constexpr` 可以省略，所以 `if` 和 `if constexpr` 共用一条产生式（[[stmt.if]]）。
- *init-statement* 可以省略，这就是 C++17 带初始化的 `if`。条文的注 1 说明 *init-statement* 以分号结尾，所以 `if (auto n = v.size(); n > 2)` 里的分号属于 *init-statement*，不是 `if` 语法里的分隔符。
- `!` 可以省略，对应 `if consteval` 和 `if !consteval`。
- `consteval` 后面要求的是 *compound-statement*，不是任意的 *statement*，所以花括号不能省。

<div class="compare" markdown="1">

```cpp run error
constexpr int f() {
  if consteval return 1;   // error
  return 0;
}
```

```cpp run ok
constexpr int f() {
  if consteval { return 1; }
  return 0;
}
```

</div>

`if constexpr (B) return 1;` 没有这个限制，因为括号里的条件已经把条件和语句隔开了。`if consteval` 没有括号，如果允许任意语句，`if consteval return 1;` 读起来就像 `consteval` 修饰了 `return`。

```cpp run ok
#include <vector>
int main() {
  std::vector<int> v{1, 2, 3};
  if (auto n = v.size(); n > 2) { }       // init-statement 和 condition
  if constexpr (sizeof(int) == 4) { }     // constexpr_opt
  if !consteval { }                       // !_opt consteval compound-statement
  switch (int k = 2; k) { case 2: break; }
}
```

## 名字的后缀（¶2）

¶2 语法类别的名字一般按下面的规则选取：

| 形式 | 含义 | 例子 |
|---|---|---|
| *X-name* | 一个标识符，它的含义由所在的上下文决定 | *class-name*、*typedef-name*、*template-name* |
| *X-id* | 一个标识符（或标识符的组合），含义不依赖上下文 | *qualified-id*、*unqualified-id*、*type-id* |
| *X-seq* | 一个或多个 *X*，中间没有分隔符 | *decl-specifier-seq*、*attribute-specifier-seq*、*statement-seq* |
| *X-list* | 一个或多个 *X*，中间用逗号隔开 | *identifier-list*、*init-declarator-list*、*template-argument-list* |

### -seq 与 -list：用递归表示重复

产生式里没有表示重复的符号，重复靠递归写出来。[[dcl.decl.general]] 中的声明符列表是这样定义的：

```text
init-declarator-list:
    init-declarator
    init-declarator-list , init-declarator
```

一个列表要么是单个元素，要么是一个更短的列表后面跟逗号和一个元素。展开就是 `a`、`a, b`、`a, b, c`。`int a = 1, b, c = 3;` 里的 `a = 1, b, c = 3` 就是一个 *init-declarator-list*。

### -name：语法要依赖名字查找

*class-name* 在形式上就是一个标识符，只有名字查找发现它确实命名一个类，它才是 *class-name*。所以解析 C++ 需要先知道每个名字是什么：

```cpp run ok
struct T {};
void h(int) {}
int a = 1;
int main() {
  T(x);   // T 命名一个类型：声明一个 T 类型的变量 x
  h(a);   // h 命名一个函数：以 a 为实参调用 h
  (void)x;
}
```

两行的形式完全一样，含义取决于括号前的名字是类型还是函数。这是 C++ 难以解析的主要原因之一，也是模板里需要 `typename` 的原因：在模板定义处，编译器还不知道 `T::x` 是不是类型，只能由程序员用 `typename T::x` 标明（[[temp.res]]）。

## 用语法回答实际问题

### 运算符优先级

C++ 标准里没有运算符优先级表。[[expr.pre]] 的脚注说，优先级没有直接规定，但可以从语法推出来。每一级表达式的产生式引用更高一级的语法类别，嵌套关系就是优先级。

赋值表达式的产生式在 [[expr.assign]]：

```text
assignment-expression:
    conditional-expression
    yield-expression
    throw-expression
    logical-or-expression assignment-operator initializer-clause
```

从最后一个备选可以读出三件事：

1. 左操作数是 *logical-or-expression*。条件表达式 `c ? a : b` 不是 *logical-or-expression*，所以 `c ? a : b = 42` 不能把 `c ? a : b` 当作左操作数。[[expr.cond]] 规定条件表达式的第三个操作数是 *assignment-expression*，于是整个式子解析为 `c ? a : (b = 42)`。C 的语法与此不同，在 C 里这是一个错误。
2. 右操作数是 *initializer-clause*，它可以是花括号列表，所以 `x = {3}` 合法。
3. *initializer-clause* 又可以是一个 *assignment-expression*，所以 `x = y = z` 解析为 `x = (y = z)`，赋值从右向左结合。

```cpp run ok
int main() {
  bool c = false;
  int a = 1, b = 2;
  c ? a : b = 42;          // c ? a : (b = 42)
  int x, y, z = 3;
  x = y = z;               // x = (y = z)
  x = {3};                 // 右操作数可以是花括号列表
  return (a == 1 && b == 42 && x == 3 && y == 3) ? 0 : 1;
}
```

*throw-expression* 也是 *assignment-expression* 的一个备选，所以 `throw` 的优先级和赋值一样低，`cond ? x : throw err` 是合法的。

### 声明为什么要由内向外读

[[dcl.decl.general]] 中声明符的语法（节选）：

```text
ptr-declarator:
    noptr-declarator
    ptr-operator ptr-declarator

noptr-declarator:
    declarator-id attribute-specifier-seq_opt
    noptr-declarator parameters-and-qualifiers
    noptr-declarator [ constant-expression_opt ] attribute-specifier-seq_opt
    ( ptr-declarator )

ptr-operator:
    * attribute-specifier-seq_opt cv-qualifier-seq_opt
    & attribute-specifier-seq_opt
    && attribute-specifier-seq_opt
    nested-name-specifier * attribute-specifier-seq_opt cv-qualifier-seq_opt
```

`*`、`&` 属于 *ptr-declarator*，写在名字左边；数组的 `[]` 和函数的 `()` 属于 *noptr-declarator*，写在名字右边。*noptr-declarator* 是 *ptr-declarator* 的组成部分，所以右边的 `[]`、`()` 比左边的 `*` 先和名字结合。想让 `*` 先结合，只能用最后一个备选 `( ptr-declarator )` 加括号。

按这个规则解析两个声明：

- `int *const p[3]`：名字 `p` 先和 `[3]` 组成 *noptr-declarator*，p 是有 3 个元素的数组；再和 `*const` 组成 *ptr-declarator*，元素是 const 指针。所以 p 是由 3 个指向 int 的 const 指针组成的数组。
- `int (*f)(int) noexcept`：括号里的 `*f` 先组成 *ptr-declarator*，加括号成为 *noptr-declarator*，再接上 `(int) noexcept`。所以 f 是指向函数的指针，这个函数接受 int、返回 int 且不抛异常。

```cpp run ok
#include <type_traits>
int main() {
  // 一个 init-declarator-list，含两个 init-declarator
  int *const p[3] = {}, (*f)(int) noexcept = nullptr;
  static_assert(std::is_same_v<decltype(p), int* const[3]>);
  static_assert(std::is_same_v<decltype(f), int(*)(int) noexcept>);
  (void)p; (void)f;
}
```

成员函数的 `const`、`&&` 限定也从这里进入函数类型：它们是 *parameters-and-qualifiers* 中的 *cv-qualifier-seq* 和 *ref-qualifier*（[[dcl.fct]]）。

## 语法只是第一道筛子

### 合乎语法的代码可能有多种读法

附录 Annex A [[gram]] 汇总了全部产生式，但 [[gram.general]] 说明，这份语法接受的是合法 C++ 构造的超集。同一段代码可能有几种读法，要靠歧义消解规则（[[stmt.ambig]]、[[dcl.ambig.res]]）选出一种，再由访问控制和类型规则排除没有意义的构造。

最有名的一条歧义消解是：一个语句既能读成声明、又能读成表达式时，按声明处理。这就是 most vexing parse：

```cpp run error
struct Timer {};
struct TimeKeeper {
  explicit TimeKeeper(Timer) {}
  int get_time() { return 0; }
};
int main() {
  TimeKeeper time_keeper(Timer());   // 声明了一个函数，不是对象
  return time_keeper.get_time();     // error: time_keeper 是函数
}
```

在形参的位置上，`Timer()` 可以读成一个无参、返回 Timer 的函数类型，作为形参类型时又调整为函数指针。于是整行声明了一个名为 `time_keeper` 的函数。改用花括号 `TimeKeeper time_keeper{Timer{}};` 就没有歧义了。Clang 对这种写法给出 `-Wvexing-parse` 警告。

### 词法在语法之前

[[lex]] 中还有一套词法产生式（*identifier*、*pp-number* 等），在翻译阶段 3 把源文本切成记号。切分时每次取能构成记号的最长字符序列，这叫最大吞噬（maximal munch，[[lex.pptoken]]）。

```cpp run error
int main() {
  int a = 1, b = 2;
  int c = a+++++b;    // error: 切成 a ++ ++ + b，a++ 的结果不能再 ++
}
```

`a++ + ++b` 本来是一种合法的读法，但切分记号时还没有语法分析，只会贪心地切出 `++`、`++`、`+`。一个例外是模板实参列表里的 `>>`：C++11 起，`vector<vector<int>>` 末尾的 `>>` 按两个 `>` 处理（[[temp.names]]）。

!!! note "引用产生式时以正文为准"
    Annex A 是说明性的汇总，偶尔与正文有编辑上的出入。引用产生式时，引用定义它的那一节。

## 思考题

!!! question "思考题"
    按 *assignment-expression* 的语法，`a = b ? c : d = e` 如何解析？`(a ? b : c) = d` 在语法上合法吗？

<details markdown="1">
<summary>答案</summary>

`a = b ? c : d = e` 中，左操作数 `a` 是 *logical-or-expression*，右边的 *initializer-clause* 是 *assignment-expression* `b ? c : d = e`。它又是一个条件表达式，第三个操作数是 *assignment-expression* `d = e`。所以整体是 `a = (b ? c : (d = e))`。

`(a ? b : c) = d` 加了括号，左边是一个 *primary-expression*，它也是 *logical-or-expression*，所以语法上合法。能否赋值由语义决定：`b`、`c` 是同类型的左值时，条件表达式的结果是左值，可以赋值（[[expr.cond]]）。
</details>
