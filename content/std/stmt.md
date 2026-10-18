---
title: 语句
summary: 第 8 章导读：语句的分类、子语句与包围关系、条件与 init-statement、跳转与自动对象的销毁、C++17→26 新增的各种语句形式。
status: draft
related: stmt.pre, stmt.select, stmt.iter, stmt.jump, stmt.dcl, basic.scope.block, intro.execution
tags: 语句, 控制流
updated: 2026-10-17
---

第 8 章 [stmt] 规定的是控制流的骨架：函数体由哪些语句组成，它们按什么顺序执行，控制如何在它们之间转移，以及转移时哪些对象被构造、哪些被销毁。
表达式（第 7 章 [[expr]]）决定计算什么，语句决定什么时候计算、计算几次、算完之后去哪里。

这一章篇幅不大，但和其他章节联系紧密：

- 作用域：每个复合语句、每个选择或迭代语句及其子语句都引入块作用域（[[basic.scope.block]]）。变量在哪里可见由第 6 章规定，变量什么时候构造和析构由本章的 [[stmt.dcl]] 规定。
- 对象生命周期：跳出作用域时，自动变量按构造的逆序销毁（[[stmt.jump.general]]、[[stmt.dcl#2]]）。临时对象的生命周期在 [[class.temporary]] 中规定，范围 for 和展开语句在那里各占一个延长生命周期的上下文。
- 模板：`if constexpr` 的弃置语句（discarded statement）和 `template for` 的重复实例化都由本章定义，在第 13 章 [[temp]] 中发挥作用。
- 常量求值：`if consteval` 取决于当前是否处于显然常量求值中（[[expr.const]]）。
- 契约：C++26 的 `contract_assert` 语句（[[stmt.contract.assert]]）是 [[basic.contract]] 定义的契约断言的一种。

## 本章地图

| 节 | 内容 | 本站笔记 |
|---|---|---|
| 8.1 [[stmt.pre]] | 语句的语法总表；子语句、包围；*condition* 与 *init-statement* | [[stmt.pre]]（兼含 8.2–8.4） |
| 8.2 [[stmt.label]] | 标号、`case`/`default`、控制流受限语句 | 见 [[stmt.pre]] |
| 8.3 [[stmt.expr]] | 表达式语句、空语句 | 见 [[stmt.pre]] |
| 8.4 [[stmt.block]] | 复合语句（块） | 见 [[stmt.pre]] |
| 8.5 [[stmt.select]] | `if`、`if constexpr`、`if consteval`、`switch` | [[stmt.select]] |
| 8.6 [[stmt.iter]] | `while`、`do`、`for`；平凡无限循环 | [[stmt.iter]] |
| 8.6.5 [[stmt.ranged]] | 范围 for 的改写规则 | [[stmt.ranged]] |
| 8.7 [[stmt.expand]] | 展开语句 `template for` {{c++26}} | [[stmt.expand]] |
| 8.8 [[stmt.jump]] | `break`/`continue`/`return`/`co_return`/`goto` | [[stmt.jump]] |
| 8.9 [[stmt.contract.assert]] | `contract_assert` {{c++26}} | [[stmt.contract.assert]] |
| 8.10 [[stmt.dcl]] | 声明语句：跳过初始化、局部静态变量 | [[stmt.dcl]] |
| 8.11 [[stmt.ambig]] | 表达式语句与声明的歧义消解 | [[stmt.ambig]] |

## 贯穿全章的几个思想

### 1. 等价改写

本章大量使用"X 等价于 Y"（is equivalent to）的写法来定义语义：

- 带初始化器的 `if`/`switch` 等价于在外面套一层 `{ init-statement; if (...) ... }`（[[stmt.if#3]]、[[stmt.switch#7]]）；
- `while` 等价于一个带标号和 `goto` 的 `if`（[[stmt.while#2]]）；
- `for` 等价于 `while`（[[stmt.for#1]]）；
- 范围 for 等价于一个经典 `for`，外加几个仅供说明的变量（[[stmt.ranged#1]]）；
- `template for` 等价于一串展开的复合语句（[[stmt.expand#5]]）；
- `co_return` 等价于 `{ p.return_value(...); goto final-suspend; }`（[[stmt.return.coroutine#2]]）。

读这些改写时要注意，它们几乎都带着 "except that ..." 的但书。例如 *init-statement* 与 *condition* 处于同一作用域（按字面改写，它们会处于嵌套的两层作用域）；`for` 中的 `continue` 会先执行迭代表达式。language lawyer 关心的很多问题，就出在改写与但书的交界处。

### 2. 子语句、包围与控制流受限

[[stmt.pre#2]] 定义了**子语句**（substatement），[[stmt.pre#3]] 在此基础上定义了**包围**（encloses）关系。包围关系是全章的基础设施：

- `break` 必须被循环、展开语句或 `switch` 包围（[[stmt.break]]）；
- `case` 标号必须被 `switch` 包围（[[stmt.label#2]]）；
- 协程不得包围 `return` 语句（[[stmt.return.coroutine#1]]）；
- 不能从外面用 `goto` 或 `case` 跳进**控制流受限语句**（control-flow-limited statement，[[stmt.label#3]]）。`if constexpr`、`if consteval` 的分支和 `template for` 的循环体都是这种语句。

注意 lambda 的函数体不是它所在语句的子语句（[[stmt.pre#2]] 注 1），所以 lambda 里的 `break` 不能跳出外层循环。

### 3. 跳转与对象的构造和析构

无论以什么方式离开作用域，都要按构造的逆序销毁已构造的自动变量，这是 C++ RAII 在语言层面的基础。[[stmt.dcl#2]] 把它精确地表述为：销毁在点 P 活跃而在点 Q 不活跃的变量。反过来，跳转（`goto`、`switch` 跳到 `case`）不能绕过非平凡的初始化。

### 4. 条件里的声明

C++ 从一开始就允许 `if (T* p = get())` 这种在条件里声明变量的写法；C++17 加入了 *init-statement*（`if (auto x = f(); x > 0)`）；C++26 允许结构化绑定声明作为条件（`if (auto [p, ec] = std::from_chars(...))`）。三者的共同目标是**让变量的作用域尽可能小，恰好覆盖使用它的语句**。

## 演进一览

| 版本 | 本章相关的变化 |
|---|---|
| C++98 | 基本语句形式；条件中的声明；`switch` 跳过初始化的规则；局部静态变量在首次经过时初始化 |
| C++11 | 范围 for；局部静态变量初始化线程安全；`return` 时的隐式移动；语句前可以写 *attribute-specifier-seq* |
| C++17 | `if constexpr`；`if`/`switch` 的 *init-statement*；范围 for 的 begin/end 可以是不同类型；`[[fallthrough]]` |
| C++20 | 范围 for 的 *init-statement*；协程 `co_return`；`[[likely]]`/`[[unlikely]]`；隐式移动规则扩大 |
| C++23 | `if consteval`；复合语句末尾的标号；范围 for 初始化器中临时对象的生命周期延长；隐式移动进一步简化；`if constexpr` 条件允许窄化 |
| C++26 | `template for` 展开语句；`contract_assert`；结构化绑定作为条件；平凡无限循环不再是 UB；`return` 绑定临时对象到返回引用变为非良构 |

具体的提案与细节见各节笔记。

## 读本章需要的前置概念

- [[basic.scope.block]]：块作用域；[[basic.lookup.unqual]]：名字隐藏。
- [[basic.life]]：生命周期、空初始化（vacuous initialization，跳转规则用到它）。
- [[class.temporary]]：临时对象何时销毁（范围 for 的陷阱都与此有关）。
- [[expr.context]]：弃值表达式（discarded-value expression，表达式语句中的表达式就是弃值表达式）。
- [[conv]]：按语境转换为 bool（contextually converted to bool，条件的取值方式）。
