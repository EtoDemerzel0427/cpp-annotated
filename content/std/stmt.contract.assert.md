---
title: 断言语句（contract_assert）
summary: C++26 的 contract_assert 语句：在函数体内引入一个契约断言；谓词是按语境转换为 bool 的条件表达式；连续的断言语句按序求值（可能重复）；与 assert 宏、assume 属性的区别。
status: draft
since: c++26
papers: P2900R14
related: basic.contract, dcl.contract.func, expr.prim.id.unqual, dcl.attr.assume, stmt.pre
tags: 语句, 契约, C++26
updated: 2026-10-17
---

{{c++26}} `contract_assert` 是 C++26 契约（contracts）特性中的语句形式。契约断言共有三种：函数声明上的前置条件 `pre(...)`、后置条件 `post(...)`（[[dcl.contract.func]]），以及函数体中的断言语句 `contract_assert(...)`（本节）。三者共享同一套语义，包括谓词、四种求值语义和违约处理函数，这些都定义在 [[basic.contract]] 中；本节只规定它作为语句的那一小部分。

所以，读这一页之前（或同时）应该读 [[basic.contract]]。下面先用一页篇幅概括那里的核心概念，再逐段讲解 [[stmt.contract.assert]]。

## 背景：契约断言的语义（[[basic.contract]] 概要）

- **谓词**（contract-assertion predicate）：一个 `bool` 类型的表达式（[[basic.contract.general#2]]），描述此处程序状态应当满足的性质。
- 谓词中引用的、在断言之外声明的变量，其 *id-expression* 的类型带 const（[[expr.prim.id.unqual#7]]）；`this` 是指向 const 的指针。这是为了防止谓词意外修改程序状态。
- 每次求值使用四种**求值语义**之一（[[basic.contract.eval#1]]）：
    - ignore：不求值谓词（但谓词仍是潜在求值的，会 odr-use 实体）；
    - observe：检查；违约时调用违约处理函数，处理函数正常返回后继续执行；
    - enforce：检查；违约时调用处理函数，正常返回后契约终止程序；
    - quick-enforce：检查；违约时直接契约终止，不调用处理函数。
- 使用哪种语义由实现定义，每次求值都可以不同（[[basic.contract.eval#2]]）。标准建议默认为 enforce，并提供全部 ignore 和全部 enforce 的编译选项。
- 在检查语义下，是否真的求值谓词是未指定的，实现可以用一个无副作用的等价计算得到它的值（[[basic.contract.eval#5]]）。所以不能依赖谓词的副作用。
- **违约**（contract violation）：谓词为 `false`、谓词求值抛出异常，或者在明显常量求值中谓词不是核心常量表达式（[[basic.contract.eval#7]]）。
- 如果在常量求值中违约，且语义是终止性的，程序非良构（[[basic.contract.eval#8]]）。也就是说，`constexpr` 函数里的 `contract_assert` 失败会变成编译错误。
- 违约处理函数 `::handle_contract_violation`（[[basic.contract.handler]]）接收一个 `const std::contracts::contract_violation&`；它是否可替换由实现定义。

## 语法

```text
assertion-statement:
    contract_assert attribute-specifier-seq(opt) ( conditional-expression ) ;
```

有几个容易忽略的细节：

1. `contract_assert` 是一个关键字（[[lex.key]]）。`pre` 和 `post` 则不同，它们是有特殊含义的标识符，只在函数声明符的特定位置有意义。不用 `assert` 这个名字，是因为 `assert` 早已是 `<cassert>` 中的宏名，任何包含该头文件的翻译单元都会把 `assert(...)` 展开掉。
2. 括号里是 *conditional-expression*，不是 *expression*，所以**不能直接写赋值表达式或逗号表达式**。`contract_assert(x = 1);` 在语法上就不成立（防止把 `==` 误写为 `=`）；`contract_assert(a, b);` 也不行，要写成 `contract_assert((a, b));`。
3. 属性写在关键字与左括号之间，它属于这个契约断言，而不是语句，见 ¶1。

```cpp error
void f(int x) {
    contract_assert(x = 1);     // error: 赋值表达式不是 conditional-expression
    contract_assert(x > 0, x < 10);   // error: 逗号表达式需要再加一层括号
}
```

## 引入一个契约断言（¶1）

¶1 *assertion-statement* **引入一个契约断言**（[[basic.contract]]）。可选的 *attribute-specifier-seq* 属于所引入的契约断言。

因为它是一条语句，所以：

- 它可以出现在任何能写语句的地方，如函数体、lambda 体、循环体、`if` 的分支，也包括 `constexpr`/`consteval` 函数；
- 它不能出现在表达式中（例如成员初始化列表、默认实参、`?:` 的操作数）。在这些位置需要断言时，可以用一个立即调用的 lambda 包装，或者把检查放进被调用函数的前置条件；
- 它不是宏，不受 `NDEBUG` 影响，也不经过预处理器；是否检查由实现选择的求值语义决定。

```cpp ok
#include <cstddef>
int at(const int* p, std::size_t n, std::size_t i) {
    contract_assert(p != nullptr);
    contract_assert(i < n);
    return p[i];
}
```

!!! impl "编译器支持"
    截至写作时，本机的 Clang 23 尚不支持 `contract_assert`（把它当作未声明的标识符），因此本页的例子未能在本地验证，判定按标准给出。

## 谓词（¶2）

¶2 断言语句的谓词，是它的 *conditional-expression* **按语境转换为 bool**（[[conv]]）后的结果。因此 `explicit operator bool` 可以用于谓词，指针、整数也都可以直接写。

结合 [[expr.prim.id.unqual#7]] 的 const 化规则，谓词不能修改断言之外声明的变量：

```cpp error
#include <vector>
void g(std::vector<int>& v, int i) {
    contract_assert(++i > 0);           // error: 谓词中的 i 是 const int
    contract_assert(v.emplace_back(1) == 1);  // error: v 在谓词中是 const，不能调用非 const 成员函数
}
```

但 const 化只作用于名字，不会传递到指针所指的对象，也挡不住 `const_cast` 或 `mutable` 成员。刻意绕过时仍然能写出带副作用的谓词，而标准明确说这些副作用不一定发生（[[basic.contract.eval#5]]）。

## 连续断言的按序求值（¶3）

¶3 连续的断言语句的求值，是对它们引入的契约断言的一次**按序求值**（evaluation in sequence，[[basic.contract.eval#18]]）。

按序求值允许实现把列表中的每个断言**重复求值实现定义的次数**，只要每个断言首次出现的相对顺序保持不变。注 1 的例子：

```cpp
int f(int i) {
    contract_assert(i == 0);   // #1
    contract_assert(i >= 0);   // #2
    return 0;
}
int g = f(0);   // 可能的求值序列：#1 #2 #1 #2
```

[[basic.contract.eval#18]] 的例子给出了更完整的列表：`#1 #2`、`#1 #1 #2 #2`、`#1 #2 #1 #2`、`#1 #2 #2 #1` 都合法，`#2 #1` 不合法（#2 的首次出现早于 #1）。

允许重复是为了支持工具与测试，例如检查谓词是否真的无副作用（多次求值结果应该一致），或者在不同的位置（调用方与被调方）各检查一次。标准建议实现默认不重复（[[basic.contract.eval#19]]），但提供选项。

连续是指这些断言语句之间没有其他语句。如果中间隔了一条普通语句，它们就分属两个独立的序列。

## 求值语义的后果

| 语义 | 谓词为 false 时 | 典型用途 |
|---|---|---|
| ignore | 什么也不发生 | 发布构建、性能敏感路径 |
| observe | 调用违约处理函数，处理函数返回后继续执行 | 在生产环境中先观察新加的断言 |
| enforce | 调用处理函数，返回后契约终止 | 默认；调试构建 |
| quick-enforce | 直接契约终止 | 安全加固，最小代码体积 |

违约处理函数可以抛出异常。对断言语句来说，异常从这条语句的执行处继续向外查找处理器（[[basic.contract.eval#17]] 注 13）。前置/后置条件则不同，表现为函数体以该异常退出。

在常量求值中：

```cpp error
constexpr int checked_div(int a, int b) {
    contract_assert(b != 0);
    return a / b;
}
constexpr int ok = checked_div(6, 3);    // OK
constexpr int bad = checked_div(1, 0);   // 非良构：常量求值中违约（若语义是终止性的）
```

（如果实现在常量求值中选择 observe 语义，会产生一条诊断，但不一定非良构；如果选择 ignore，随后的除以零会使求值不是常量表达式。无论如何，这个初始化都无法通过。）

## 与 assert 宏、assume 属性的对比

| | `assert(e)` 宏 | `contract_assert(e)` | `[[assume(e)]];` |
|---|---|---|---|
| 是什么 | 预处理宏（[[cassert.syn]]） | 语句，引入契约断言 | 属性，作用于空语句 |
| 关闭方式 | 定义 `NDEBUG` | 实现选择 ignore 语义（编译选项） | 不能关闭 |
| `e` 为 false 时 | 调用 `abort` | 依语义：忽略 / 观察 / 终止 | **UB**（[[dcl.attr.assume]]） |
| `e` 被求值吗 | 是（未定义 `NDEBUG` 时） | 未指定 | 从不 |
| 对变量的 const 化 | 无 | 有 | 无 |
| 能用在表达式中 | 能（是表达式） | 不能 | 不能 |
| 跨 TU 的 ODR 风险 | 有（`NDEBUG` 不一致导致 inline 函数的定义不同） | 求值语义不是定义的一部分；仅当谓词的副作用影响常量表达式的值时才可能出问题（[[basic.contract.eval#8]] 注 6） | 无 |

`[[assume]]` 与契约断言的方向正好相反。契约断言的意思是检查这个条件，不满足就报告；`[[assume]]` 的意思是程序员保证这个条件成立，编译器可以据此优化，不成立就是 UB。不要把二者混用。

## 历史与演进

!!! history
    - C++20 的工作草案中一度有基于属性语法的契约（`[[expects]]`、`[[ensures]]`、`[[assert]]`），在 C++20 发布前整体移除，原因是在违约后继续执行的语义、构建模式等问题上无法达成共识。
    - 之后 SG21 重新设计了最小可行产品（MVP），最终以 [[P2900R14]] 的形式进入 C++26：语法改为关键字/上下文关键字（`contract_assert`、`pre`、`post`），去掉了构建级别，改为每次求值的实现定义语义。
    - 在 C++23 及之前，函数体内的断言只能使用 `<cassert>` 的 `assert` 宏或各种库/编译器扩展。

## 陷阱

!!! pitfall "不要在谓词中做有用的事"
    谓词可能不求值（ignore，或检查语义下用等价计算代替），也可能求值多次（按序求值的重复）。程序依赖的任何副作用，如日志、计数、修改状态，都不该放进谓词。

!!! pitfall "observe 语义下违约后继续执行"
    对 `contract_assert(p != nullptr); use(*p);`，在 observe 语义下，违约处理函数返回后会继续执行 `use(*p)`，接着就是空指针解引用的 UB。契约断言不会让后面的代码变得安全。在 observe 或 ignore 语义下，断言之后的代码必须能承受谓词为假的情形，否则就必须确保不以这些语义部署。

## 思考题

!!! question "1. 为什么谓词的语法是 conditional-expression 而不是 expression？"

<details markdown="1">
<summary>答案</summary>

一是防止 `contract_assert(x = 0)` 这种把比较误写为赋值的错误，这种写法在 `assert` 宏和 `if` 中都合法而危险。二是逗号：如果允许 *expression*，`contract_assert(a, b)` 会解析为逗号表达式（只检查 `b`），读者却很可能以为它检查了两个条件。三是为将来的扩展留出语法空间（例如在括号内追加其他标注）。确实需要逗号或赋值时，可以再加一层括号，这样能清楚地表明是有意为之。
</details>

!!! question "2. 下面的代码中，`contract_assert` 能观察到 `n` 被修改吗？"
    ```cpp
    int n = 0;
    void f(int* p) { contract_assert((*p = 1, true)); }
    void g() { f(&n); }
    ```

<details markdown="1">
<summary>答案</summary>

程序是良构的。const 化只作用于谓词中出现的变量名 `p` 本身（`p` 变成 `int* const`），`*p` 的类型仍是 `int`，可以赋值。但赋值是否发生是未指定的：ignore 语义下谓词不求值；检查语义下，实现可以发现谓词恒为 `true` 而跳过求值（[[basic.contract.eval#5]]）；按序求值时还可能执行多次。所以 `g()` 之后 `n` 可能是 0，也可能是 1。
</details>

## 小结

| 方面 | 规则 |
|---|---|
| 语法 | `contract_assert attr(opt) ( conditional-expression ) ;`，关键字 |
| 引入 | 一个契约断言；属性属于该断言 |
| 谓词 | 条件表达式按语境转换为 bool；外部变量在谓词中为 const |
| 连续断言 | 一起按序求值，可重复，首次出现顺序不变 |
| 求值语义 | ignore / observe / enforce / quick-enforce，实现定义 |
| 常量求值 | 终止性语义下违约 → 非良构 |
| 违约处理函数抛异常 | 从该语句处继续传播 |
