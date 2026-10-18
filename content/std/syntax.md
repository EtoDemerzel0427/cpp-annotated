---
title: 语法表示法
summary: 如何读标准里的语法产生式：斜体非终结符、等宽终结符、"one of"、下标 opt，以及 X-name / X-id / X-seq / X-list 的命名惯例；附几条真实产生式的逐字解读。
status: done
related: intro.structure, gram, lex.pptoken, stmt.ambig, topics/how-to-read-the-standard
tags: 语法, 导读
updated: 2026-10-17
---

标准用一种 BNF 风格的记法给出 C++ 的语法。[syntax] 只有两段，说明这种记法怎么读。但要真正读懂一条产生式——它允许什么、不允许什么、为什么写成这样——需要一些练习。本页先讲规则，再拿几条真实的产生式逐字解读。

## 记法（¶1）

¶1 在本文档的语法记法中：

- **语法类别**（syntactic categories，即非终结符）用*斜体无衬线*字体表示，如 *expression*、*declarator*。
- **字面的单词和字符**（终结符）用等宽字体表示，如 `if`、`(`、`::`。
- **备选项**分行列出；少数备选项很多的情况用 "one of" 标出，写在一行或几行里。
- 备选项太长一行放不下时，接续行相对首行**缩进**。
- **可选**的终结符或非终结符用下标 "opt" 表示。

所以

> { *expression*<sub>opt</sub> }

表示花括号括起的一个**可选**表达式：`{}` 和 `{ x + 1 }` 都匹配。

!!! tip "在 eel.is 上和复制出来的文本里"
    eel.is 上 opt 渲染为下标；但把产生式复制成纯文本时，下标会和前面的词粘在一起，变成 `expressionopt`、`constexpropt`。本站笔记在代码块中引用产生式时写作 `expression_opt`，含义相同。

一个"one of"的例子，[[expr.assign]] 中的赋值运算符：

```text
assignment-operator: one of
    =  *=  /=  %=  +=  -=  >>=  <<=  &=  ^=  |=
```

这里每个记号都是一个独立的备选项。

## 命名惯例（¶2）

¶2 语法类别的名字一般按以下规则选取：

| 形式 | 含义 | 例子 |
|---|---|---|
| *X-name* | 在**由上下文决定其含义**的语境中使用的标识符 | *class-name*、*typedef-name*、*template-name*、*namespace-name* |
| *X-id* | 没有上下文相关含义的标识符（或标识符组合） | *qualified-id*、*unqualified-id*、*type-id*、*declarator-id* |
| *X-seq* | 一个或多个 *X*，中间**没有**分隔符 | *decl-specifier-seq*、*attribute-specifier-seq*、*statement-seq* |
| *X-list* | 一个或多个 *X*，中间用**逗号**分隔 | *identifier-list*、*init-declarator-list*、*template-argument-list* |

*X-name* 和 *X-id* 的区别值得细想。*class-name* 在语法上就是一个 *identifier*（或 *simple-template-id*），但只有当名字查找发现它**确实**命名一个类时，它才是 *class-name*。这意味着 C++ 的语法**不是上下文无关的**：解析器需要名字查找的结果才能决定一个标识符属于哪个语法类别。经典例子：

```cpp
T(a);       // 若 T 是类型名：声明一个名为 a 的 T 类型变量
            // 若 T 是函数名：以 a 为实参调用 T
```

这正是 C++ 难以解析的根源之一，也是 [[temp.res]] 要求在模板中用 `typename` 标出依赖类型名的原因——在模板定义处，编译器无法通过查找得知 `T::x` 是不是类型。

*X-seq* 和 *X-list* 在语法中通常递归定义。例如 [[dcl.decl]]：

```text
init-declarator-list:
    init-declarator
    init-declarator-list , init-declarator
```

这是**左递归**：一个列表要么是单个元素，要么是"一个更短的列表 + 逗号 + 一个元素"。展开后就是 `a`、`a, b`、`a, b, c`……

## 逐字解读：几条真实的产生式

### selection-statement：可选项与必选项

[[stmt.select.general]] 中的选择语句：

```text
selection-statement:
    if constexpr_opt ( init-statement_opt condition ) statement
    if constexpr_opt ( init-statement_opt condition ) statement else statement
    if !_opt consteval compound-statement
    if !_opt consteval compound-statement else statement
    switch ( init-statement_opt condition ) statement
```

（这里用 `_opt` 代替下标。）逐项读：

- `constexpr` 可选——这就是 `if` 和 `if constexpr`（[[stmt.if]]）共用一条产生式的原因。
- *init-statement* 可选——C++17 的带初始化的 `if`。标准的注 1 提醒：*init-statement* 以分号结尾。所以 `if (auto n = v.size(); n > 2)` 中，分号是 *init-statement* 的一部分，而不是 `if` 语法里的分隔符。
- `!` 可选——`if consteval` 和 `if !consteval`。
- `consteval` 分支要求 *compound-statement*，而不是任意 *statement*：**花括号是必须的**。

```cpp run error
constexpr int f() {
  if consteval return 1;     // error: consteval 之后必须是复合语句
  return 0;
}
```

为什么要强制花括号？因为如果允许 `if consteval return 1; else ...`，悬挂 else 的歧义和"consteval 到底管到哪"的问题会更难读；强制复合语句让作用范围一目了然。

```cpp run ok
#include <vector>
int main() {
  std::vector<int> v{1, 2, 3};
  if (auto n = v.size(); n > 2) { }       // init-statement + condition
  if constexpr (sizeof(int) == 4) { }     // constexpr_opt
  if !consteval { }                       // !_opt consteval compound-statement
  switch (int k = 2; k) { case 2: break; }
}
```

### assignment-expression：语法如何编码优先级与结合性

[[expr.assign]]：

```text
assignment-expression:
    conditional-expression
    yield-expression
    throw-expression
    logical-or-expression assignment-operator initializer-clause
```

C++ 标准里没有"运算符优先级表"。优先级和结合性完全由产生式的**嵌套结构**编码：每一级表达式的产生式引用下一级（更高优先级）的非终结符。读这一条可以得出三个结论：

1. **左操作数是 *logical-or-expression***。条件运算符 `?:` 不是 *logical-or-expression*，所以 `c ? a : b = 42` 不能把 `c ? a : b` 当作左操作数。那它怎么解析？看 [[expr.cond]]：*conditional-expression* 的第三个操作数是 *assignment-expression*。于是它被解析为 `c ? a : (b = 42)`。（这与 C 不同：C 的语法里这是一个错误。）
2. **右操作数是 *initializer-clause***，它可以是 *braced-init-list*：`x = {1}` 合法（同时受 [[dcl.init.list]] 的窄化规则约束）。
3. **右递归**：*initializer-clause* 可以再是一个 *assignment-expression*，所以 `x = y = z` 解析为 `x = (y = z)`——赋值是右结合的。

```cpp run ok
int main() {
  bool c = false;
  int a = 1, b = 2;
  c ? a : b = 42;          // 解析为 c ? a : (b = 42)
  int x, y, z = 3;
  x = y = z;               // x = (y = z)
  x = {3};                 // 右操作数可以是 braced-init-list
  return (a == 1 && b == 42 && x == 3 && y == 3) ? 0 : 1;
}
```

另外，`throw-expression` 和 `yield-expression` 也是 *assignment-expression* 的备选——所以 `throw` 表达式的优先级和赋值一样低，`cond ? x : throw err` 是合法的。

### declarator：从内到外读声明

[[dcl.decl.general]] ¶7 给出声明符的语法（节选）：

```text
declarator:
    ptr-declarator
    noptr-declarator parameters-and-qualifiers trailing-return-type

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

这组产生式解释了 C/C++ 声明为什么要"从内向外读"：

- *ptr-operator*（`*`、`&`）在 *ptr-declarator* 里，位于**左边**；
- 数组 `[]` 和函数 `()` 在 *noptr-declarator* 里，位于**右边**，且 *noptr-declarator* 是 *ptr-declarator* 的组成部分——所以右边的 `[]`、`()` 比左边的 `*` **绑定得更紧**；
- 想让 `*` 先结合，只能用 `( ptr-declarator )` 加括号。

解析 `int *const p[3]`：*declarator-id* `p` → *noptr-declarator* `p[3]`（p 是 3 元素数组）→ *ptr-declarator* `*const p[3]`（元素是 const 指针）。所以 `p` 是"3 个指向 int 的 const 指针的数组"。

解析 `(*f)(int) noexcept`：括号里 `*f` 先构成 *ptr-declarator*，加括号成为 *noptr-declarator* → 后面接 *parameters-and-qualifiers* `(int) noexcept` → `f` 是"指向 `noexcept` 的、接受 int 返回 int 的函数的指针"。

```cpp run ok
#include <type_traits>
int main() {
  int *const p[3] = {}, (*f)(int) noexcept = nullptr;   // 一个 init-declarator-list，两个 init-declarator
  static_assert(std::is_same_v<decltype(p), int* const[3]>);
  static_assert(std::is_same_v<decltype(f), int(*)(int) noexcept>);
  (void)p; (void)f;
}
```

注意 *parameters-and-qualifiers* 里的 *cv-qualifier-seq*、*ref-qualifier*：成员函数的 `const`、`&&` 就是从这里进入函数类型的（[[dcl.fct]]）。

## 语法之外：语法只是第一道筛子

### 语法是超集

[[gram.general]] 明说：Annex A 的语法汇总**接受合法 C++ 构造的超集**。歧义消解规则（[[stmt.ambig]]、[[dcl.ambig.res]]）、访问控制、类型规则才把"语法上合法但无意义"的构造筛掉。正文中的语法也一样：一段代码符合语法，离良构还很远。

最著名的歧义消解是"最令人烦恼的解析"（most vexing parse）：一个既可以解析为声明、又可以解析为表达式的语句，按声明处理。

```cpp run error
struct Timer {};
struct TimeKeeper {
  explicit TimeKeeper(Timer) {}
  int get_time() { return 0; }
};
int main() {
  TimeKeeper time_keeper(Timer());   // 声明了一个函数！参数是"返回 Timer 的函数的指针"
  return time_keeper.get_time();     // error: time_keeper 是函数，不是对象
}
```

`Timer()` 在形参声明语境中被解析为 *abstract-declarator*：一个"无参、返回 Timer 的函数"类型，作为形参调整为函数指针。修复方法是用花括号 `TimeKeeper time_keeper{Timer{}};`。Clang 对此给出 `-Wvexing-parse` 警告。

### 词法层的语法

[[lex]] 中还有一套**词法语法**（*preprocessing-token*、*identifier*、*pp-number* ……），在翻译阶段 3 把源文本切成预处理记号。它遵循**最大吞噬**（maximal munch）原则（[[lex.pptoken]]）：每次取能构成记号的最长字符序列。

```cpp run error
int main() {
  int a = 1, b = 2;
  int c = a+++++b;           // error: 记号化为 a ++ ++ + b，a++ 是纯右值，不能再 ++
}
```

`a+++++b` 在语法上**本可以**解析为 `a++ + ++b`，但词法分析在语法分析之前完成，它只会贪心地切出 `++`、`++`、`+`。相反，模板实参列表中的 `>>` 有特殊规则（[[temp.names]]）：C++11 起，`vector<vector<int>>` 中的 `>>` 会被当作两个 `>`。

## 陷阱

!!! pitfall "“语法允许就是合法的”"
    语法只是必要条件。`int x = "hello";` 完全符合语法（*init-declarator* 带 *initializer*），但违反了初始化的语义规则。判断良构性，语法只是第一步。

!!! pitfall "把 *X-name* 当作纯语法类别"
    *class-name*、*template-name*、*typedef-name* 都依赖名字查找的结果。同一个标识符在不同位置可以属于不同的类别。看到 *X-name* 时要想到：这里隐含了一次查找，规则在 [[basic.lookup]]。

!!! pitfall "Annex A 与正文不一致时"
    Annex A 是资料性的汇总，以正文为准。两者偶有编辑性的出入，引用时应引用正文条款中的产生式。

## 思考题

!!! question "思考题 1"
    按 *assignment-expression* 的语法，`a = b ? c : d = e` 如何解析？`(a ? b : c) = d` 合法吗？

<details markdown="1">
<summary>答案</summary>

`a = b ? c : d = e`：左操作数 `a` 是 *logical-or-expression*，右操作数 *initializer-clause* 是 *assignment-expression* `b ? c : d = e`；而这又是一个 *conditional-expression*，其第三个操作数是 *assignment-expression* `d = e`。所以整体是 `a = (b ? c : (d = e))`。

`(a ? b : c) = d`：加了括号之后，左边是 *primary-expression*（括号表达式），它当然也是 *logical-or-expression*，语法上合法。语义上：若 `b`、`c` 是同类型的左值，条件表达式的结果是左值（[[expr.cond]]），可以赋值；若是纯右值则不可以。
</details>

!!! question "思考题 2"
    为什么 `if consteval` 要求 *compound-statement*，而 `if constexpr` 只要求 *statement*？从语法角度看，`if constexpr (B) return 1;` 和 `if consteval return 1;` 有什么区别？

<details markdown="1">
<summary>答案</summary>

`if constexpr (B) return 1;` 中，条件 `(B)` 用括号与后面的子语句隔开，语法上没有歧义。`if consteval` 没有括号括起的条件，如果允许任意 *statement*，`if consteval return 1;` 读起来就像 `consteval` 修饰了 `return`，`if !consteval x = 1;` 也容易误读。强制花括号让 `consteval` 只能作为一个独立的"条件"出现，语句体的范围总是明确的。
</details>

## 小结

!!! summary
    - 斜体 = 非终结符，等宽 = 终结符；分行 = 备选；"one of" = 一行多个备选；下标 opt = 可选。
    - *X-name* 依赖上下文（查找），*X-id* 不依赖；*X-seq* 无分隔，*X-list* 逗号分隔，通常左递归定义。
    - C++ 没有优先级表：优先级和结合性由表达式产生式的嵌套编码，例如赋值的左操作数是 *logical-or-expression*，右操作数是 *initializer-clause*。
    - 声明符语法解释了"从内向外读"：`[]`、`()` 比 `*`、`&` 结合得紧，要改变只能加括号。
    - 语法接受的是超集；歧义消解、名字查找、类型规则决定最终是否良构。词法层的最大吞噬先于语法分析。
