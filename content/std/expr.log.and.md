---
title: 逻辑与、逻辑或运算符
summary: "&& 与 || 的语境转换为 bool、短路求值与“左操作数先于右操作数”的顺序保证；重载后失去短路（C++17 起仍保留顺序）；模板实例化与常量求值中的短路；约束中的合取/析取"
status: done
covers: expr.log.and, expr.log.or
papers: P0145R3
related: conv, expr.bit.and, intro.execution, over.match.oper, expr.cond, expr.comma, temp.constr.op, expr.prim.fold, expr.const.core
tags: 短路求值, 求值顺序, 布尔
updated: 2026-10-17
---

[[expr.log.and]]（`&&`）和 [[expr.log.or]]（`||`）是 C++ 中仅有的三个带内置控制流的二元运算符中的两个（另一个是逗号，[[expr.comma]]；三元的 `?:` 见 [[expr.cond]]）。它们不仅计算一个值，还决定是否求值右操作数，并保证求值顺序，这就是[[g:short-circuit-evaluation|短路求值]]。`p && p->ok()`、`i < n && a[i] != x` 这类先检查再访问的写法正依赖于此。

两节的结构完全对称，各两段：¶1 讲转换与短路，¶2 讲结果类型与顺序。

## 语境转换与短路（¶1）

!!! std
    Unlike &, && guarantees left-to-right evaluation: the second operand is not evaluated if the first operand is false.

    与 `&` 不同，`&&` 保证从左往右求值：若第一操作数为 `false`，第二操作数不被求值。

`||` 与之对称：第一操作数为 `true` 时不求值第二操作数。两者都从左往右结合，`a && b && c` 是 `(a && b) && c`，于是一串 `&&` 从左往右逐个检查，遇到第一个 `false` 即停止。

两个操作数都**语境转换为 `bool`**（contextually converted to `bool`，[[conv]]），即进行直接初始化 `bool t(e);`。这意味着带 `explicit operator bool` 的类型（智能指针、`std::optional`、流对象）可以直接作为操作数，就像在 `if` 条件中一样：

```cpp run title="logand-contextual.cpp" ok
#include <memory>
#include <optional>

struct Flag { explicit operator bool() const { return true; } };

int main() {
    auto p = std::make_unique<int>(42);
    std::optional<int> o = 7;
    Flag f;
    bool ok = p && *p == 42 && o && f;   // 每个操作数都语境转换为 bool
    // bool b = f;                       // error: explicit 转换函数不参与复制初始化
    return ok ? 0 : 1;
}
```

`&&` 的结果为真当且仅当两个操作数都为真；`||` 的结果为真当且仅当至少一个为真。

## 结果类型与顺序（¶2）

¶2 结果类型是 `bool`。

!!! std
    If the second expression is evaluated, the first expression is sequenced before the second expression.

    若第二个表达式被求值，第一个表达式先于它求值。

先于（sequenced before，[[intro.execution#8]]）意味着第一操作数的所有值计算和副作用都在第二操作数的任何求值之前完成。所以下面的代码有定义：

```cpp run title="logand-sequencing.cpp" ok
int main() {
    int i = 0;
    bool r = (i++ == 0) && (i == 1);   // OK: i++ 的副作用在读取第二个 i 之前完成
    int j = 0;
    bool s = (j = 5) || (j = 6);       // OK: 第二个赋值不会执行
    return (r && s && j == 5) ? 0 : 1;
}
```

C++98 用第一操作数之后有一个序列点来表达同一件事；C++11 起改用 sequenced-before 关系描述（见 [[topics/order-of-evaluation]]）。

## 重载的 `&&` 与 `||`：失去短路

`&&` 和 `||` 可以重载（[[over.binary]]），但重载版本是普通函数调用：调用之前两个实参都要求值，于是**短路消失**。C++17 之前，连先左后右的顺序也没有保证（函数实参之间顺序不确定）；C++17 起，[[over.match.oper]] 规定用运算符语法调用重载运算符时，操作数按内置运算符规定的顺序求值，于是左操作数仍然先于右操作数，但两个都会求值：

```cpp run title="logand-overload.cpp" ok
#include <cstdio>

struct B {
    bool v;
    friend B operator&&(B a, B b) { return {a.v && b.v}; }
};

B make(bool v, const char* name) { std::printf("eval %s\n", name); return {v}; }

int main() {
    B r = make(false, "left") && make(true, "right");
    // 输出 "eval left" 和 "eval right"：右操作数照样被求值（无短路）；
    // C++17 起保证 left 先于 right 打印。
    return r.v ? 1 : 0;
}
```

因此几乎所有编码规范都建议**不要重载 `&&`、`||` 和逗号**：用户无法从调用点看出语义已经改变。重载它们的合理场景只有表达式模板（expression templates）这类领域特定语言，例如构造查询条件、`std::valarray<bool>` 的逐元素与运算，在这些场景中本来就不存在短路的概念。

## 短路与编译期

### 常量求值

短路对常量求值同样有效：未被求值的操作数不会让表达式成为非常量。

```cpp title="logand-constexpr.cpp" error
int runtime_only();     // 非 constexpr

constexpr bool a = false && runtime_only();   // OK: 右操作数未被求值
constexpr bool b = true  || runtime_only();   // OK
constexpr bool c = true  && runtime_only();   // error: 求值了非 constexpr 函数
```

不过，未求值的操作数仍然必须良构：它仍然会被编译，其中的名字仍然要查找，也构成 odr-use（[[basic.def.odr]]）。**短路是求值层面的概念，不是编译层面的概念。**

### 模板：`&&` 不会阻止实例化

最常见的误用是在模板中用 `&&` 来保护后面的表达式：

```cpp title="logand-template.cpp" error
#include <type_traits>

template<class T>
constexpr bool has_true_value() {
    return std::is_class_v<T> && T::value;   // 右边仍然要实例化！
}

constexpr bool x = has_true_value<int>();    // error: int::value 非良构
```

`T::value` 在实例化时就必须有意义，与运行期是否求值无关。正确的做法是使用 `if constexpr`（[[stmt.if]]）、`std::conjunction`（它的特化在遇到第一个 `false` 时就不再实例化后续的 `::value`），或者使用约束：

```cpp run title="logand-concept.cpp" ok
#include <type_traits>

template<class T>
concept HasTrueValue = std::is_class_v<T> && T::value;   // 约束中的 && 是"合取"

static_assert(!HasTrueValue<int>);   // OK: 第一个原子约束不满足，第二个不再检查

int main() {}
```

在 *constraint-expression* 中，顶层的 `&&` 和 `||` 不是运算符，而是约束的**合取**（conjunction）与**析取**（disjunction）（[[temp.constr.op]]）。满足性检查从左往右进行，合取的左操作数不满足时，右操作数不做替换，因此不会触发硬错误。这与 `bool` 表达式里的 `&&` 是两套不同的规则。

### 折叠表达式

`(... && args)` 与 `(... || args)` 是一元折叠的常见形式。空包时，`&&` 折叠得 `true`、`||` 折叠得 `false`（[[expr.prim.fold]]）。由于展开后就是普通的 `&&` 链，短路同样适用：`(f(args) && ...)` 遇到第一个 `false` 即停止调用后续的 `f`。

## 优先级

`&&` 的优先级高于 `||`：`a || b && c` 是 `a || (b && c)`。这与数学中乘法优先于加法类似（布尔代数中与对应乘、或对应加），但混用时可读性差，Clang 的 `-Wlogical-op-parentheses`（`-Wparentheses` 的一部分）会建议加括号。两者都低于位运算 `|`，高于 `?:` 和赋值。替代记号分别是 `and`、`or`（[[lex.digraph]]）。

!!! impl "实现视角"
    短路通常编译为条件跳转。但 as-if 规则（[[intro.abstract]]）允许编译器在右操作数没有副作用、不会出错且代价低时，把 `a && b` 编译为无分支的 `a & b`（例如两个整数比较），以避免分支预测失败。反过来，用 `a & b` 表达的无分支意图也不一定能保留，优化器可能为了跳过昂贵的右操作数而引入分支。想要可靠的无分支代码，应检查生成的汇编。

## 陷阱

!!! pitfall "以为重载的 `&&` 也会短路"
    重载后两边都会求值。C++17 只保证了顺序，没有恢复短路。

!!! pitfall "以为 `&&` 能阻止模板实例化"
    短路只影响运行期（或常量）求值；右操作数仍然要良构。用 `if constexpr`、`std::conjunction` 或约束。

!!! pitfall "以为 `a || b && c` 是 `(a || b) && c`"
    `&&` 优先级更高。

!!! pitfall "为了优化把 `&&` 换成 `&`"
    失去短路后，依赖左操作数做守卫的右操作数可能出错（空指针、越界）；而且两边的求值变成无序的。

## 思考题

!!! question "思考题 1"
    `bool r = f() || g() && h();` 中，若 `f()` 返回 `true`，哪些函数会被调用？

<details markdown="1">
<summary>答案</summary>

表达式解析为 `f() || (g() && h())`。`f()` 为 `true` 时整个右操作数 `g() && h()` 都不被求值，所以只调用 `f()`。
</details>

!!! question "思考题 2"
    在 C++14 中，`struct B { ... }; B operator&&(B, B);` 被用于 `make("left") && make("right")`，两次调用的顺序有保证吗？C++17 呢？

<details markdown="1">
<summary>答案</summary>

C++14：`a && b` 被改写为函数调用 `operator&&(a, b)`，两个实参的求值顺序未指定（且在 C++14 中实参的求值甚至可以交错），没有保证。C++17：[[over.match.oper#2]] 规定操作数按内置运算符规定的顺序求值，内置 `&&` 先左后右，所以 `make("left")` 先于 `make("right")`，但两者都会被调用。如果写成显式的函数调用 `operator&&(make("left"), make("right"))`，就不适用这条规则，两个实参之间只是不确定顺序（indeterminately sequenced，[[expr.call]]）。
</details>

## 小结

| 方面 | `&&` | `\|\|` |
|---|---|---|
| 操作数转换 | 语境转换为 `bool` | 同左 |
| 短路 | 左为 `false` 不求值右 | 左为 `true` 不求值右 |
| 顺序 | 左先于右（若右被求值） | 同左 |
| 结果 | `bool` | `bool` |
| 重载后 | 无短路；C++17 起仍左先右后 | 同左 |
| 在约束中 | 合取（短路地检查满足性） | 析取 |
