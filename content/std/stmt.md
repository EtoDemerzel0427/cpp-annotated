---
title: 语句
summary: 第 8 章的结构：有哪些语句，控制流怎样在它们之间转移，转移时哪些对象被构造和销毁；本章惯用的等价改写写法，以及 C++11 到 C++26 新增的语句形式。
status: draft
related: stmt.pre, stmt.select, stmt.iter, stmt.jump, stmt.dcl, basic.scope.block, intro.execution
tags: 语句, 控制流, 导读
updated: 2026-10-19
---

!!! tldr
    - 第 7 章规定表达式算什么，第 8 章规定语句按什么顺序执行、执行几次、控制流怎样转移，以及转移时哪些自动变量被构造和销毁。
    - `while`、`for`、范围 `for`、带初始化的 `if`、`co_return` 等很多语句都用等价改写定义，要留意改写后面的 except that 但书。
    - `break`、`case`、`goto` 能写在哪里，取决于子语句和包围关系，它们不穿过 lambda 体。
    - 离开作用域时自动变量按构造的逆序销毁；跳转不能越过非空的初始化。
    - 条件里可以声明变量，C++17 加了 *init-statement*，C++26 允许结构化绑定作条件，目的都是让变量的作用域恰好覆盖使用它的语句。

函数体由语句组成。表达式（[[expr]]）决定计算什么，语句决定什么时候计算、计算几次、算完之后去哪里。本章还依赖第 6 章的几个概念：块作用域（[[basic.scope.block]]）、对象生命周期（[[basic.life]]）和求值顺序（[[intro.execution]]）。

## 本章的组织

| 小节 | 内容 | 本站笔记 |
|---|---|---|
| 8.1–8.4 | 语句的种类；子语句与包围；条件；标号、表达式语句、复合语句 | [[stmt.pre]] |
| 8.5 | `if`、`if constexpr`、`if consteval`、`switch` | [[stmt.select]] |
| 8.6 | `while`、`do`、`for`；平凡无限循环 | [[stmt.iter]] |
| 8.6.5 | 范围 `for` 的改写规则 | [[stmt.ranged]] |
| 8.7 | 展开语句 `template for` {{c++26}} | [[stmt.expand]] |
| 8.8 | `break`、`continue`、`return`、`co_return`、`goto` | [[stmt.jump]] |
| 8.9 | `contract_assert` {{c++26}} | [[stmt.contract.assert]] |
| 8.10 | 声明语句：跳过初始化、局部静态变量 | [[stmt.dcl]] |
| 8.11 | 表达式语句与声明之间的歧义 | [[stmt.ambig]] |

## 贯穿全章的几个规则

### 用等价改写定义语义

本章很多语句不直接描述行为，而是说"X 等价于 Y"：

- 带初始化器的 `if`、`switch` 等价于外面再套一层 `{ init-statement; if (…) … }`（[[stmt.if#3]]、[[stmt.switch#7]]）；
- `while` 等价于一个带标号和 `goto` 的 `if`（[[stmt.while#2]]），`for` 等价于 `while`（[[stmt.for#1]]）；
- 范围 `for` 等价于一个经典 `for` 加上几个仅供说明的变量（[[stmt.ranged#1]]）；
- `template for` 等价于一串展开的复合语句（[[stmt.expand#5]]）；
- `co_return` 等价于 `{ p.return_value(…); goto final-suspend; }`（[[stmt.return.coroutine#2]]）。

这些改写几乎都带着 except that 的但书。例如 *init-statement* 和条件处于同一个作用域，而按字面改写它们会在两层作用域里；`for` 循环体里的 `continue` 会先执行迭代表达式。很多细节问题就出在改写和但书的交界处。

### 子语句与包围

[[stmt.pre]] 定义了子语句和包围关系。`break`、`continue` 必须被循环、`switch` 或展开语句包围，`case` 标号必须被 `switch` 包围。lambda 体不是子语句，所以这些规则都不穿过 lambda：lambda 里的 `break` 不能跳出外层循环。

`if constexpr`、`if consteval` 的分支和 `template for` 的循环体是控制流受限语句，不能从外面用 `goto` 或 `case` 跳进去（[[stmt.label#3]]）。

### 跳转与自动变量的销毁

不论以什么方式离开作用域，已经构造的自动变量都按构造的逆序销毁，这是 RAII 在语言层面的基础。[[stmt.dcl#2]] 的表述是：控制从点 P 转移到点 Q 时，销毁在 P 处活跃、在 Q 处不活跃的变量。反过来，跳转不能越过需要真正初始化的变量：

<div class="compare" markdown="1">

```cpp run error
#include <string>
void f(bool b) {
  if (b) goto end;  // error
  std::string s = "x";  // 被越过
end:
  ;
}
```

```cpp run ok
void f(bool b) {
  if (b) goto end;
  int n;   // 空初始化，可以越过
end:
  n = 1;
  (void)n;
}
```

</div>

### 条件里的声明

C++ 从一开始就允许 `if (T* p = get())` 这样在条件里声明变量。C++17 加入了 *init-statement*（`if (auto x = f(); x > 0)`），C++26 允许结构化绑定声明作条件（`if (auto [p, ec] = std::from_chars(…))`）。三者的目的相同：让变量的作用域恰好覆盖使用它的语句。

## 各版本的变化

| 版本 | 本章相关的变化 |
|---|---|
| C++98 | 基本语句形式；条件中的声明；`switch` 不得跳过初始化；局部静态变量在控制首次经过时初始化 |
| C++11 | 范围 `for`；局部静态变量的初始化是线程安全的；`return` 局部变量时隐式移动；语句前可以写属性 |
| C++17 | `if constexpr`；`if`、`switch` 的 *init-statement*；范围 `for` 的 begin 和 end 可以是不同类型；`[[fallthrough]]` |
| C++20 | 范围 `for` 的 *init-statement*；`co_return`；`[[likely]]`、`[[unlikely]]`；隐式移动的适用范围扩大 |
| C++23 | `if consteval`；块末尾的标号；*init-statement* 可以是别名声明；范围 `for` 初始化器中的临时对象生命期延长；隐式移动进一步简化；`if constexpr` 的条件允许窄化转换到 `bool` |
| C++26 | `template for` 展开语句；`contract_assert`；结构化绑定作条件；平凡的无限循环不再是 UB；`return` 把临时对象绑定到返回的引用变为非良构 |

具体规则和提案见各节笔记。
