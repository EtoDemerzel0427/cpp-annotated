---
title: 逗号运算符
summary: a, b 先求值并丢弃 a，再求值 b，结果的类型、值和值类别都取 b；函数实参之间的逗号不是这个运算符；重载的逗号与 void() 防御写法；下标中的逗号从 C++23 起表示多维下标。
status: done
papers: P0145R3, P1161R3, P2128R6
related: expr.context, intro.execution, over.match.oper, expr.call, expr.sub, dcl.init, temp.names, expr.prim.fold
tags: 逗号, 求值顺序
updated: 2026-10-19
---

!!! tldr
    - `a, b` 先完整求值 `a` 并丢弃结果，再求值 `b`；`a` 的所有副作用都在 `b` 开始之前完成。
    - 结果的类型、值、值类别都取右操作数，所以 `(a, b) = 5` 给 `b` 赋值。
    - 函数实参、初始化器列表、模板实参之间的逗号是分隔符，不是逗号运算符，不保证顺序。
    - 逗号可以重载。泛型代码写 `void(f(x)), g(y)`，让左操作数是 `void`，就不会碰到用户的 `operator,`。
    - C++23 起 `a[i, j]` 是多维下标，对内置数组和指针非良构；要用逗号运算符得写 `a[(i, j)]`。

## 规则（¶1）

```cpp run title="comma-basics.cpp" ok
#include <type_traits>
#include <utility>

int a = 1, b = 2;
static_assert(std::is_same_v<decltype((a, b)), int&>);              // 右操作数是 lvalue
static_assert(std::is_same_v<decltype((a, 3)), int>);               // prvalue
static_assert(std::is_same_v<decltype((a, std::move(b))), int&&>);  // xvalue

int main() {
    (a, b) = 5;                 // OK：结果就是 b 这个左值
    int i = 0;
    int r = (i++, i++, i);      // OK：从左往右逐个完成，r == 2
    return (b == 5 && r == 2) ? 0 : 1;
}
```

¶1 逗号运算符从左往右结合，求值也从左往右：

- 左操作数是**弃值表达式**（[[g:discarded-value-expression]]）：求值只为副作用，结果被丢弃（[[expr.context#2]]）。
- 左操作数**先于**（[[g:sequenced-before]]）右操作数：左边的值计算和副作用全部完成后，右边才开始（[[intro.execution]]）。
- 结果的类型和值是右操作数的类型和值，值类别与右操作数相同；右操作数是位域时，结果也是位域。

所以 `(i++, i++, i)` 有定义，而 `i++ + i++` 是 UB：逗号规定了顺序，`+` 没有（[[intro.execution#10]]）。

在 C 中，逗号表达式的结果从来不是左值。C++ 保留右操作数的值类别，逗号表达式就能透明地出现在需要左值的地方，例如宏展开出的 `(check(), obj).member = v`。

左操作数没有任何效果时，Clang、GCC 会给出 `-Wunused-value` 警告。这个警告常能抓到把 `a[i][j]` 误写成 `a[i, j]` 之类的错误。

## 哪些逗号是运算符（¶2）

```text
expression:
    assignment-expression
    expression , assignment-expression
```

非终结符 *expression* 本身就是逗号表达式。文法要求 *expression* 的地方，比如括号里、条件运算符的中间操作数、`for` 的各部分，可以直接出现逗号运算符；只要求 *assignment-expression* 的地方，比如函数实参、初始化器，不行。

¶2 的注 1 说明，在逗号另有含义的语境里，即函数调用（[[expr.call]]）、下标（[[expr.sub]]）、初始化器列表（[[dcl.init]]）和模板实参列表（[[temp.names]]），逗号运算符只能出现在括号里：

```cpp run title="comma-context.cpp" ok
int f(int a, int b, int c) { return a * 100 + b * 10 + c; }

int main() {
    int a = 1, t = 0, c = 3;
    int r = f(a, (t = 3, t + 2), c);   // 三个实参，第二个是 5
    return r == 153 ? 0 : 1;
}
```

函数实参之间的逗号不是逗号运算符，实参之间也就没有从左往右的保证。C++17 起，实参的求值彼此顺序不确定（[[expr.call]]）：`f(i++, i++)` 不再是 UB，但哪个先算是未指定的。

### 下标中的逗号 {{removed:C++23}}

C++20 之前，`a[i, j]` 就是 `a[(i, j)]`，也就是 `a[j]`，这几乎总是笔误。C++20 的 [[P1161R3]] 弃用了下标中不带括号的逗号表达式；C++23 的 [[P2128R6]] 把这种写法改作多维下标，`a[i, j]` 调用 `a.operator[](i, j)`（[[over.sub]]），`std::mdspan` 的 `m[i, j]` 就靠它。内置下标的方括号里必须恰好是一个表达式：

```cpp title="comma-subscript.cpp" error
int main() {
    int arr[3]{};
    int x = arr[1, 2];      // error：内置下标只接受一个表达式（C++23 起）
    int y = arr[(1, 2)];    // OK：带括号的逗号表达式，即 arr[2]
    return x + y;
}
```

参见 [[diff.cpp20.expr]]。

## 重载的逗号

逗号运算符可以重载（[[over.binary]]）。重载后它是一次普通的函数调用。C++17 之前，两个实参的求值顺序未指定，逗号的顺序保证随之消失；C++17 起，[[over.match.oper#2]] 规定用运算符语法调用的重载运算符按对应内置运算符的顺序求值操作数，重载的逗号也先左后右（[[P0145R3]]）。

顺序问题解决了，意外调用的问题还在。在泛型代码里，如果 `f(x)` 的返回类型能经 ADL 找到一个 `operator,`，`f(x), g(y)` 就会调用它。把左操作数转换为 `void` 可以避开：`void` 类型的操作数不可能匹配任何用户定义的 `operator,`。

```cpp run title="comma-overload.cpp" ok
#include <cstdio>

struct Evil {
    template<class T>
    friend Evil operator,(Evil, T) { std::puts("evil comma called"); return {}; }
};
Evil make() { return {}; }

int main() {
    make(), 1;          // 调用重载的 operator,（输出一次）
    void(make()), 1;    // 内置逗号：左操作数是 void
}
```

libc++、libstdc++ 的算法实现里常见 `++first1, (void)++first2` 这样的写法，就是这个原因。

## 折叠表达式中的逗号

一元折叠 `(E, ...)` 按逗号展开成 `E1, (E2, (E3, ...))` 的形式（[[expr.prim.fold]]），所以会按顺序对每个包元素求值。C++17 中对每个实参调用一次函数，标准写法就是它：

```cpp run title="comma-fold.cpp" ok
#include <cstdio>

template<class... Ts>
void print_all(const Ts&... xs) {
    (void(std::printf("%d ", xs)), ...);   // 按实参顺序输出；void() 防御重载的逗号
    std::puts("");
}

int main() { print_all(1, 2, 3); }   // 输出 1 2 3
```

包为空时，`(E, ...)` 展开为 `void()`。

## 常见误解

!!! pitfall "以为 `return a, b;` 返回两个值"
    返回的是 `b`。需要多个值时用 `std::pair`、`std::tuple` 或结构体。

!!! pitfall "以为 `int x = 1, y = 2;` 里的逗号是逗号运算符"
    这里是声明符之间的分隔符，声明了两个变量。

## 思考题

!!! question "思考题"
    `x = 1, y = 2;` 作为表达式语句时是什么结构？`int z = (x = 1, y = 2);` 中 `z` 是多少？去掉括号呢？

<details markdown="1">
<summary>答案</summary>

`x = 1, y = 2;` 中的逗号是逗号运算符。赋值的优先级高于逗号，所以它是 `(x = 1), (y = 2)`。

`int z = (x = 1, y = 2);` 的括号里是逗号表达式，结果是右操作数 `y = 2` 的结果，即值为 2 的 `y`，所以 `z == 2`。

去掉括号写成 `int z = x = 1, y = 2;`，它就成了一个声明：`z` 初始化为 `x = 1` 的值 1，再声明一个新变量 `y`。如果同一作用域里已经有 `y`，这就是重复定义，非良构。
</details>

## 小结

| 方面 | 规则 |
|---|---|
| 求值 | 从左往右；左先于右，包括全部副作用 |
| 左操作数 | 弃值表达式 |
| 结果 | 类型、值、值类别、位域性都取右操作数 |
| 实参、初始化器、模板实参中 | 逗号是分隔符；要用逗号运算符得加括号 |
| 下标中的逗号 | C++20 弃用；C++23 起表示多维下标，内置下标非良构 |
| 重载 | 普通函数调用；C++17 起仍先左后右；用 `void()` 防御 |
