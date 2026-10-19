---
title: 逻辑与、逻辑或运算符
summary: && 和 || 把操作数语境转换为 bool，左操作数先求值，结果已经确定时不求值右操作数；重载版本失去短路；短路只影响求值，不能阻止模板实例化；约束中的 && 和 || 是合取与析取。
status: done
covers: expr.log.and, expr.log.or
papers: P0145R3
related: conv, expr.bit.and, intro.execution, over.match.oper, expr.cond, expr.comma, temp.constr.op, expr.prim.fold, expr.const.core
tags: 短路求值, 求值顺序, 布尔
updated: 2026-10-19
---

!!! tldr
    - `&&` 和 `||` 把两个操作数语境转换为 `bool`，所以带 `explicit operator bool` 的智能指针、`std::optional` 可以直接作操作数。
    - 左操作数先求值，它的副作用在右操作数开始之前完成；`&&` 的左边为假、`||` 的左边为真时，右边不求值。这就是短路求值。
    - 重载的 `&&`、`||` 是普通函数调用，两边都会求值；C++17 起只保证左边先于右边。
    - 短路只影响求值，不影响编译：没有被求值的右操作数仍然必须良构，`std::is_class_v<T> && T::value` 不能保护 `T::value`。
    - 在约束表达式里，`&&` 和 `||` 是约束的合取与析取，左边不满足时右边不做替换，这是另一套规则。

```cpp run title="logand-guard.cpp" ok
#include <cstddef>

int find(const int* a, std::size_t n, int x) {
    std::size_t i = 0;
    while (i < n && a[i] != x) ++i;   // i == n 时不会读取 a[n]
    return i < n ? int(i) : -1;
}

int main() {
    int a[3] = {4, 5, 6};
    return find(a, 3, 6) == 2 && find(a, 3, 7) == -1 ? 0 : 1;
}
```

`i < n && a[i] != x`、`p && p->ok()` 这类先检查、再访问的写法，都依赖 [[expr.log.and]]（`&&`）和 [[expr.log.or]]（`||`）规定的[[g:short-circuit-evaluation|短路求值]]。两节结构对称，各有两段。

## 短路（¶1）

!!! std
    Unlike &, && guarantees left-to-right evaluation: the second operand is not evaluated if the first operand is false.

¶1 `&&` 从左往右求值：第一个操作数为 `false` 时，第二个操作数不求值。`||` 对称：第一个操作数为 `true` 时，第二个不求值。两者都从左往右结合，`a && b && c` 是 `(a && b) && c`，所以一串 `&&` 从左往右逐个检查，遇到第一个 `false` 就停下。

`&&` 的结果为真，当且仅当两个操作数都为真；`||` 的结果为真，当且仅当至少一个为真。

### 语境转换为 `bool`

两个操作数都**语境转换为 `bool`**（contextually converted to `bool`，[[conv]]），即按直接初始化 `bool t(e);` 的方式转换。直接初始化会考虑 `explicit` 转换函数，所以智能指针、`std::optional`、流对象可以直接作操作数，就像在 `if` 的条件里一样：

```cpp run title="logand-contextual.cpp" ok
#include <memory>
#include <optional>

struct Flag { explicit operator bool() const { return true; } };

int main() {
    auto p = std::make_unique<int>(42);
    std::optional<int> o = 7;
    Flag f;
    bool ok = p && *p == 42 && o && f;   // 每个操作数都语境转换为 bool
    // bool b = f;                       // error: 复制初始化不考虑 explicit 转换函数
    return ok ? 0 : 1;
}
```

## 结果类型与顺序（¶2）

¶2 结果类型是 `bool`。如果第二个操作数被求值，第一个操作数**先于**（sequenced before，[[intro.execution#8]]）它求值：第一个操作数的所有值计算和副作用，都在第二个操作数的任何求值开始之前完成。所以下面的代码有定义：

```cpp run title="logand-sequencing.cpp" ok
int main() {
    int i = 0;
    bool r = (i++ == 0) && (i == 1);   // i++ 的副作用在读取第二个 i 之前完成
    int j = 0;
    bool s = (j = 5) || (j = 6);       // 第二个赋值不执行
    return (r && s && j == 5) ? 0 : 1;
}
```

C++98 用第一个操作数之后有一个序列点来表达同一件事，C++11 起改用先于关系描述（见 [[topics/order-of-evaluation]]）。按位运算 `&`、`|` 没有这种保证，两个操作数的求值彼此无序（[[expr.bit.and]]）。

## 重载后失去短路

`&&` 和 `||` 可以重载（[[over.binary]]），但重载版本是普通的函数调用：调用之前两个实参都要求值，于是短路消失了。

```cpp run title="logand-overload.cpp" ok
#include <cstdio>

struct B {
    bool v;
    friend B operator&&(B a, B b) { return {a.v && b.v}; }
};

B make(bool v, const char* name) { std::printf("eval %s\n", name); return {v}; }

int main() {
    B r = make(false, "left") && make(true, "right");
    // 输出 eval left 和 eval right：右操作数照样求值
    return r.v ? 1 : 0;
}
```

C++17 之前，连左右的先后都没有保证，因为函数实参之间的顺序是未指定的。C++17 的 [[P0145R3]] 之后，[[over.match.oper#2]] 规定用运算符语法调用重载运算符时，操作数按对应内置运算符的顺序求值，于是左边仍然先于右边，但两边都会求值。

因为调用处看不出语义已经改变，多数编码规范都建议不要重载 `&&`、`||` 和逗号。合理的用途只有表达式模板这类领域特定语言，例如构造查询条件；`std::valarray<bool>` 的逐元素 `&&` 也属于这一类，那里本来就没有短路的概念。

## 短路与编译期

### 常量求值

没有被求值的操作数，不会让表达式失去常量性：

```cpp title="logand-constexpr.cpp" error
int runtime_only();     // 不是 constexpr 函数

constexpr bool a = false && runtime_only();   // OK: 右操作数没有被求值
constexpr bool b = true  || runtime_only();   // OK
constexpr bool c = true  && runtime_only();   // error: 求值了非 constexpr 函数
```

但没有被求值的操作数仍然要编译：其中的名字要查找、类型要检查，用到的变量和函数仍然算作 odr-use（[[basic.def.odr]]）。短路是求值层面的概念，不是编译层面的概念。

### `&&` 不能阻止实例化

一个常见的误用是在模板里用 `&&` 保护后面的表达式：

```cpp title="logand-template.cpp" error
#include <type_traits>

template<class T>
constexpr bool has_true_value() {
    return std::is_class_v<T> && T::value;   // T::value 照样要实例化
}

constexpr bool x = has_true_value<int>();    // error: int::value 非良构
```

实例化 `has_true_value<int>` 时，`int::value` 就必须有意义，与运行期会不会求值无关。可以改用 `if constexpr`（[[stmt.if]]）；或者用 `std::conjunction`，它遇到第一个 `false` 后就不再访问后续类型的 `::value`；或者用约束：

```cpp run title="logand-concept.cpp" ok
#include <type_traits>

template<class T>
concept HasTrueValue = std::is_class_v<T> && T::value;   // 约束的合取

static_assert(!HasTrueValue<int>);   // 第一个原子约束不满足，第二个不再检查

int main() {}
```

在约束表达式中，顶层的 `&&` 和 `||` 不是运算符，而是约束的**合取**（conjunction）与**析取**（disjunction）（[[temp.constr.op]]）。检查合取时先检查左操作数，不满足就不再对右操作数做模板实参替换，所以 `int::value` 不会引发错误。

### 折叠表达式

`(... && args)` 和 `(... || args)` 是常见的一元折叠。空包时，`&&` 折叠得 `true`，`||` 折叠得 `false`（[[expr.prim.fold]]）。展开后就是普通的 `&&` 链，所以短路同样适用：`(f(args) && ...)` 遇到第一个 `false` 就不再调用后面的 `f`。

## 优先级

`&&` 的优先级高于 `||`，`a || b && c` 是 `a || (b && c)`。这与布尔代数中与对应乘法、或对应加法一致，但混用时不易读，Clang 的 `-Wlogical-op-parentheses`（属于 `-Wparentheses`）会建议加括号。两者都低于按位运算 `|`，高于 `?:` 和赋值。替代记号分别是 `and` 和 `or`（[[lex.digraph]]）。

!!! impl "实现视角"
    短路通常编译为条件跳转。按 as-if 规则（[[intro.abstract]]），右操作数没有副作用、不会出错而且代价很低时，编译器可以把 `a && b` 编译成无分支的 `a & b`，例如两个整数比较，以避免分支预测失败。反过来，用 `a & b` 表达的无分支意图不一定会保留，优化器也可能为了跳过昂贵的右操作数而引入分支。需要可靠的无分支代码时，应检查生成的汇编。

## 常见误解

!!! pitfall "重载的 `&&` 也会短路"
    重载后两边都会求值。C++17 只保证了顺序，没有恢复短路。

!!! pitfall "`a || b && c` 是 `(a || b) && c`"
    `&&` 的优先级更高。

!!! pitfall "为了性能把 `&&` 换成 `&`"
    失去短路后，依赖左操作数做检查的右操作数可能出错，例如空指针或越界；而且两边的求值变成无序的。

## 思考题

!!! question "思考题 1"
    `bool r = f() || g() && h();` 中，如果 `f()` 返回 `true`，哪些函数会被调用？

<details markdown="1">
<summary>答案</summary>

表达式解析为 `f() || (g() && h())`。`f()` 为 `true` 时，整个右操作数 `g() && h()` 都不求值，所以只调用 `f()`。
</details>

!!! question "思考题 2"
    有重载的 `B operator&&(B, B);`，表达式 `make("left") && make("right")` 中两次调用的顺序在 C++14 中有保证吗？C++17 呢？

<details markdown="1">
<summary>答案</summary>

C++14：`a && b` 被改写为函数调用 `operator&&(a, b)`，两个实参的求值顺序未指定，没有保证。

C++17：[[over.match.oper#2]] 规定操作数按内置运算符的顺序求值，内置 `&&` 先左后右，所以 `make("left")` 先于 `make("right")`，但两个都会调用。如果显式写成 `operator&&(make("left"), make("right"))`，这条规则不适用，两个实参之间仍然只是顺序不确定（indeterminately sequenced，[[expr.call]]）。
</details>

## 小结

| 方面 | `&&` | `\|\|` |
|---|---|---|
| 操作数 | 语境转换为 `bool` | 同左 |
| 短路 | 左为 `false` 时不求值右边 | 左为 `true` 时不求值右边 |
| 顺序 | 右边被求值时，左边先于右边 | 同左 |
| 结果 | `bool` | `bool` |
| 重载后 | 不短路；C++17 起仍是先左后右 | 同左 |
| 在约束中 | 合取 | 析取 |
