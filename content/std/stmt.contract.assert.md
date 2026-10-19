---
title: 断言语句（contract_assert）
summary: C++26 的 contract_assert 语句：在函数体里写一个契约断言，谓词按语境转换为 bool，连续的断言作为一组按序求值；它和 assert 宏、assume 属性的区别。
status: draft
since: c++26
papers: P2900R14
related: basic.contract, dcl.contract, expr.prim.id.unqual, dcl.attr.assume, stmt.pre
tags: 语句, 契约, C++26
updated: 2026-10-19
---

!!! tldr
    - `contract_assert(条件);` 是 C++26 的一条语句，它引入一个契约断言，和函数上的 `pre`、`post` 共用同一套求值规则。
    - 括号里只能写 *conditional-expression*：赋值和逗号表达式要再套一层括号。
    - 谓词里出现的外部变量都按 const 看待，所以谓词不能直接修改它们；谓词是否求值、求值几次都没有保证，不要依赖它的副作用。
    - 是否检查、失败后怎样由实现选的求值语义决定（ignore、observe、enforce、quick-enforce），与 `NDEBUG` 无关。
    - 紧挨着的几条断言语句作为一组按序求值，实现可以把整组重复求值，但第一次出现的先后顺序不变。

截至写作时，本机 Clang 23 还不认识 `contract_assert`，把它当作未声明的标识符。本页的例子都按标准原文分析，没有经过编译验证，所以不带判定标记。

## 一条断言语句

```cpp
#include <cstddef>
int at(const int* p, std::size_t n, std::size_t i) {
    contract_assert(p != nullptr);
    contract_assert(i < n);
    return p[i];
}
```

**契约断言**（[[g:contract-assertion|contract assertion]]）是 C++26 契约特性的基本单位：它带一个**谓词**，即一个描述程序此刻应当满足的条件的 `bool` 表达式。契约断言有三种写法：函数声明上的前置条件 `pre(...)`、后置条件 `post(...)`（[[dcl.contract]]），以及本节的断言语句。三者的求值和违约处理都在 [[basic.contract]] 中统一规定，本节只规定语句形式自己的部分。

语法如下：

```text
assertion-statement:
    contract_assert attribute-specifier-seq(opt) ( conditional-expression ) ;
```

`contract_assert` 是关键字（[[lex.key]]）。`pre` 和 `post` 则只是在函数声明符的特定位置有特殊含义的标识符。这个名字没有用 `assert`，因为 `assert` 早已是 `<cassert>` 里的宏。

¶1 *assertion-statement* 引入一个契约断言。写在关键字和左括号之间的属性属于这个契约断言，而不属于语句。

它是一条语句，所以能出现在任何允许写语句的地方：函数体、lambda 体、循环体、`if` 的分支，也包括 `constexpr` 和 `consteval` 函数。它不能出现在表达式里，例如成员初始化列表或默认实参中。这些位置需要检查时，可以把条件放进被调函数的 `pre`，或者用立即调用的 lambda 包一层。

## 括号里只能写条件表达式

```cpp
void f(int x) {
    contract_assert(x = 1);           // error: 赋值表达式不是 conditional-expression
    contract_assert(x > 0, x < 10);   // error: 逗号表达式不是 conditional-expression
    contract_assert((x > 0, x < 10)); // 语法上可以，但只检查 x < 10
}
```

语法要求的是 *conditional-expression*，它比 *expression* 少了赋值和逗号两层。于是把 `==` 误写成 `=` 会直接成为语法错误。`contract_assert(a, b)` 也不会被悄悄读成只检查 `b` 的逗号表达式。确实需要这两种运算时，再加一层括号即可。

## 谓词（¶2）

¶2 断言语句的谓词，是它的 *conditional-expression* [[g:contextually-converted-to-bool|按语境转换为 bool]] 的结果，也就是 `if (e)` 对条件做的那种转换。所以指针、整数，以及带 `explicit operator bool` 的类类型都可以直接写。

谓词里还有一条来自 [[expr.prim.id.unqual#7]] 的规则：如果名字指代的是在断言之外声明的变量，这个表达式的类型带 const。`this` 在谓词里也是指向 const 的指针（[[expr.prim.this#3]]）。这样谓词就不能直接修改它检查的状态：

```cpp
#include <vector>
void g(std::vector<int>& v, int i) {
    contract_assert(++i > 0);                 // error: 这里的 i 是 const int
    contract_assert(v.emplace_back(1) == 1);  // error: v 是 const，不能调用非 const 成员
}
```

const 只加在名字本身上，不会沿指针传递，也挡不住 `const_cast` 和 `mutable` 成员。刻意绕过时仍然能写出有副作用的谓词，但这些副作用不一定发生，见下一节。

## 求值语义

每次求值一个契约断言，都采用四种[[g:evaluation-semantic|求值语义]]之一（[[basic.contract.eval#1]]）。选哪一种由实现决定，通常由编译选项控制，同一个断言的不同次求值也可以不同（[[basic.contract.eval#2]]）。标准建议默认用 enforce。

| 语义 | 检查谓词吗 | 谓词为 false 时 |
|---|---|---|
| ignore | 不检查 | 什么也不发生 |
| observe | 检查 | 调用违约处理函数，它正常返回后继续往下执行 |
| enforce | 检查 | 调用违约处理函数，它正常返回后终止程序 |
| quick-enforce | 检查 | 不调用处理函数，直接终止程序 |

后三种叫检查型语义。即使在检查型语义下，谓词也不一定真的被求值：实现可以用一个结果相同、没有副作用的计算来代替它（[[basic.contract.eval#5]]）。ignore 语义下谓词不求值，但它仍是潜在求值的，其中用到的函数和变量照样被 odr-use。

断言语句不是宏，不经过预处理器，`NDEBUG` 对它没有影响。

违约处理函数可以抛出异常。对断言语句来说，异常从这条语句所在的位置继续向外寻找处理器（[[basic.contract.eval#17]] 的注 13）。`pre`、`post` 的情形不同，异常表现为函数体以这个异常退出。

### 常量求值中的违约

```cpp
constexpr int checked_div(int a, int b) {
    contract_assert(b != 0);
    return a / b;
}
constexpr int ok  = checked_div(6, 3);   // OK
constexpr int bad = checked_div(1, 0);   // 违约
```

常量求值中发生违约时，结局取决于这次求值的语义（[[basic.contract.eval#8]]）。enforce 和 quick-enforce 下程序非良构。observe 下实现必须给出诊断，然后可以继续，但接下来的 `1 / 0` 不是常量表达式，`bad` 的初始化照样失败。ignore 下同样卡在除以零上。所以这个初始化在任何语义下都通不过，区别只在报出的是哪一个错误。

## 连续的断言按序求值（¶3）

¶3 若干条紧挨着的断言语句，它们的求值是对所引入契约断言的一次**按序求值**（evaluation in sequence，[[basic.contract.eval#18]]）。

```cpp
void f(int i) {
    contract_assert(i > 0);    // #1
    contract_assert(i < 10);   // #2
}
// 合法的求值序列：#1 #2；#1 #1 #2 #2；#1 #2 #1 #2；#1 #2 #2 #1
// 不合法：#2 #1
```

按序求值允许实现把每个断言重复求值实现定义的次数，唯一的约束是每个断言第一次出现的先后顺序与源码一致。所以 `#2 #1` 不行，`#1 #2 #2 #1` 可以。

允许重复是为了方便工具和测试：一个无副作用的谓词，求值多少次结果都应当相同，重复求值可以把有副作用的谓词暴露出来。标准建议实现提供重复求值的选项，但默认不重复（[[basic.contract.eval#19]]）。中间隔了一条其他语句的断言不算连续，分属两组。

## 与 assert 宏、`[[assume]]` 的对比

| | `assert(e)` | `contract_assert(e);` | `[[assume(e)]];` |
|---|---|---|---|
| 是什么 | 预处理宏（[[cassert.syn]]） | 语句，引入契约断言 | 用在空语句上的属性（[[dcl.attr.assume]]） |
| 怎样关闭 | 定义 `NDEBUG` | 实现选择 ignore 语义 | 不能关闭 |
| `e` 为 false 时 | 调用 `abort` | 取决于求值语义 | 未定义行为 |
| `e` 会被求值吗 | 未定义 `NDEBUG` 时会 | 未指定 | 从不 |
| 外部变量在 `e` 中是 const | 否 | 是 | 否 |
| 能用在表达式里 | 能 | 不能 | 不能 |

`[[assume]]` 和契约断言的方向相反。契约断言的意思是请检查这个条件，不满足就报告；`[[assume(e)]]` 的意思是我保证 `e` 成立，编译器可以据此优化，不成立就是 UB。

`assert` 在不同翻译单元里 `NDEBUG` 设置不一致时，同一个 inline 函数会有不同的定义，违反 ODR。契约断言的求值语义不是定义的一部分，一般没有这个问题。只有谓词的副作用改变了某个常量表达式的值时，不同的语义选择才可能导致 ODR 违规（[[basic.contract.eval#8]] 的注 6）。

## 常见误解

!!! pitfall "在谓词里做有用的事"
    谓词可能不求值（ignore，或者被等价计算代替），也可能求值多次（按序求值的重复）。日志、计数、修改状态这类程序依赖的副作用都不应该放进谓词。

!!! pitfall "有了断言，后面的代码就安全了"
    observe 语义下，违约处理函数返回后程序继续执行。对 `contract_assert(p != nullptr); use(*p);`，接下来仍然是空指针解引用。断言之后的代码要么能承受条件不成立，要么确保这段代码不会以 observe 或 ignore 语义部署。

## 历史与演进

!!! history
    - C++20 的工作草案曾经有一套基于属性语法的契约（`[[expects]]`、`[[ensures]]`、`[[assert]]`），在 C++20 发布前被整体移除，分歧集中在违约后能否继续执行、怎样配置构建模式等问题上。
    - 之后的设计以 [[P2900R14]] 进入 C++26：语法改为 `contract_assert` 关键字和 `pre`、`post`，用每次求值的求值语义取代了原来的构建级别。
    - C++23 及以前，函数体内的断言只能用 `<cassert>` 的 `assert` 宏或各家的扩展。

## 思考题

!!! question "思考题 1"
    下面的代码良构吗？调用 `g()` 之后 `n` 的值是多少？
    ```cpp
    int n = 0;
    void f(int* p) { contract_assert((*p = 1, true)); }
    void g() { f(&n); }
    ```

<details markdown="1">
<summary>答案</summary>

良构。const 只加在谓词中出现的名字 `p` 上，`p` 的类型变成 `int* const`，`*p` 仍是可修改的 `int` 左值。外层的括号让逗号表达式成为一个 *primary-expression*，符合语法。

但赋值是否发生是未指定的：ignore 语义下谓词不求值；检查型语义下，实现可以看出谓词恒为 `true` 而跳过求值（[[basic.contract.eval#5]]）；重复求值时还可能赋值多次。所以 `n` 可能是 0，也可能是 1。
</details>

!!! question "思考题 2"
    `contract_assert(x > 0); log(); contract_assert(x < 10);` 中，实现可以先检查 `x < 10` 再检查 `x > 0` 吗？

<details markdown="1">
<summary>答案</summary>

不可以。中间隔了一条语句，两条断言不是连续的，各自单独求值，按语句的执行顺序进行。只有连续的断言语句才组成一组按序求值（¶3），而即使在一组之内，第一次出现的先后顺序也必须与源码一致。
</details>
