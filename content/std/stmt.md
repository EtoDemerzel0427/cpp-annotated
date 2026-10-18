---
title: 语句
summary: 第 8 章导读：语句的分类、子语句与"包围"关系、条件与 init-statement、跳转与自动对象的销毁、C++17→26 新增的各种语句形式。
status: draft
related: stmt.pre, stmt.select, stmt.iter, stmt.jump, stmt.dcl, basic.scope.block, intro.execution
tags: 语句, 控制流
updated: 2026-10-17
---

第 8 章 [stmt] 规定的是**控制流的骨架**：一段函数体由哪些语句组成，它们按什么顺序执行，控制如何在它们之间转移，以及转移时哪些对象被构造、哪些被销毁。
表达式（第 7 章 [[expr]]）决定"算什么"，语句决定"什么时候算、算几次、算完去哪"。

这一章篇幅不大，但它和其他章节咬合得很紧：

- **作用域**：每个复合语句、每个选择/迭代语句及其子语句都引入块作用域（[[basic.scope.block]]）。"变量在哪里可见"由第 6 章管，"变量什么时候构造/析构"由本章 [[stmt.dcl]] 管。
- **对象生命周期**：跳出作用域会按构造的逆序销毁自动变量（[[stmt.jump.general]]、[[stmt.dcl#2]]）；临时对象的生命周期在 [[class.temporary]]，但范围 for 和展开语句在那里各占一个"延长生命周期的上下文"。
- **模板**：`if constexpr` 的"弃置语句"（discarded statement）和 `template for` 的"重复实例化"都是本章定义、在第 13 章 [[temp]] 中发挥作用的机制。
- **常量求值**：`if consteval` 取决于"是否明显常量求值"（[[expr.const]]）。
- **契约**：C++26 的 `contract_assert` 语句（[[stmt.contract.assert]]）是 [[basic.contract]] 定义的契约断言的一种。

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

### 1. "等价于"改写

本章大量使用 **"X 等价于 Y"**（is equivalent to）的写法来定义语义：

- 带初始化器的 `if`/`switch` 等价于外面套一层 `{ init-statement; if (...) ... }`（[[stmt.if#3]]、[[stmt.switch#7]]）；
- `while` 等价于一个带标号和 `goto` 的 `if`（[[stmt.while#2]]）；
- `for` 等价于 `while`（[[stmt.for#1]]）；
- 范围 for 等价于一个经典 `for`，外加几个仅供说明的变量（[[stmt.ranged#1]]）；
- `template for` 等价于一串展开的复合语句（[[stmt.expand#5]]）；
- `co_return` 等价于 `{ p.return_value(...); goto final-suspend; }`（[[stmt.return.coroutine#2]]）。

读这些改写时要注意它们几乎都带着 **"except that ..."** 的但书：例如 *init-statement* 与 *condition* 处于**同一作用域**（而按字面改写它们会处于嵌套的两层作用域），`for` 中的 `continue` 会先执行迭代表达式。language lawyer 的很多问题就出在"改写"与"但书"的交界处。

### 2. 子语句、包围与"控制流受限"

[[stmt.pre#2]] 定义**子语句**（substatement），[[stmt.pre#3]] 在其上定义**包围**（encloses）关系。后者是全章的基础设施：

- `break` 必须被循环、展开语句或 `switch` 包围（[[stmt.break]]）；
- `case` 标号必须被 `switch` 包围（[[stmt.label#2]]）；
- 协程不得包围 `return` 语句（[[stmt.return.coroutine#1]]）；
- **控制流受限语句**（control-flow-limited statement，[[stmt.label#3]]）禁止从外面用 `goto`/`case` 跳进去——`if constexpr`、`if consteval` 的分支和 `template for` 的循环体都是这种语句。

注意 lambda 的函数体**不是**它所在语句的子语句（[[stmt.pre#2]] 注 1），所以 lambda 里的 `break` 不能跳出外层循环。

### 3. 跳转与对象的构造/析构

"任何方式离开作用域，都要按构造的逆序销毁已构造的自动变量"——这是 C++ RAII 的语言基础。[[stmt.dcl#2]] 把它精确化为"在点 P 活跃而在点 Q 不活跃的变量"被销毁；反方向上，**跳转**（`goto`、`switch` 到 `case`）不能绕过非平凡的初始化。

### 4. 条件里的声明

C++ 从一开始就允许 `if (T* p = get())` 这种在条件里声明变量的写法；C++17 加上了 *init-statement*（`if (auto x = f(); x > 0)`）；C++26 允许结构化绑定声明作为条件（`if (auto [p, ec] = std::from_chars(...))`）。这三者共同的目标是：**让变量的作用域尽可能小，恰好覆盖使用它的语句**。

## 演进一览

| 版本 | 本章相关的变化 |
|---|---|
| C++98 | 基本语句形式；条件中的声明；`switch` 跳过初始化的规则；局部静态变量"首次经过时初始化" |
| C++11 | 范围 for；局部静态变量初始化线程安全；`return` 时的隐式移动；语句前可以写 *attribute-specifier-seq* |
| C++17 | `if constexpr`；`if`/`switch` 的 *init-statement*；范围 for 的 begin/end 可以是不同类型；`[[fallthrough]]` |
| C++20 | 范围 for 的 *init-statement*；协程 `co_return`；`[[likely]]`/`[[unlikely]]`；隐式移动规则扩大 |
| C++23 | `if consteval`；复合语句末尾的标号；范围 for 初始化器中临时对象的生命周期延长；隐式移动进一步简化；`if constexpr` 条件允许窄化 |
| C++26 | `template for` 展开语句；`contract_assert`；结构化绑定作为条件；平凡无限循环不再是 UB；`return` 绑定临时对象到返回引用变为非良构 |

具体的提案与细节见各节笔记。

## 读本章需要的前置概念

- [[basic.scope.block]]：块作用域；[[basic.lookup.unqual]]：名字隐藏。
- [[basic.life]]：生命周期、**vacuous initialization**（跳转规则用到它）。
- [[class.temporary]]：临时对象何时销毁（范围 for 的坑全在这里）。
- [[expr.context]]：**弃值表达式**（discarded-value expression，表达式语句的表达式就是它）。
- [[conv]]：**按语境转换为 bool**（contextually converted to bool，条件的取值方式）。
