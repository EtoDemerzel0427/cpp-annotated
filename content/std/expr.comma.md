---
title: 逗号运算符
summary: "逗号运算符从左往右求值、左操作数是弃值表达式且先于右操作数；结果的类型、值与值类别都取右操作数；重载的逗号（C++17 起也左先右后）与 void() 防御惯用法；下标中的逗号：C++20 弃用、C++23 改作多维下标"
status: done
papers: P0145R3, P1161R3, P2128R6
related: expr.context, intro.execution, over.match.oper, expr.call, expr.sub, dcl.init, temp.names, expr.prim.fold, expr.log.and
tags: 逗号, 求值顺序
updated: 2026-10-18
---

逗号运算符是优先级**最低**的运算符：`a, b` 先求值 `a` 并丢弃其结果，再求值 `b`，整个表达式就是 `b`。它最常见于 `for` 循环的第三部分（`++i, --j`）和折叠表达式（`(f(args), ...)`）中。

本节规则很少，但有三个值得 language lawyer 留意的点：

1. 逗号是少数几个**保证求值顺序**的运算符之一（另外几个是 `&&`、`||`、`?:`，以及 C++17 起的 `<<`、`>>`、`=`、`.*`、`->*`、`[]` 等）；
2. 结果保留右操作数的**值类别**——`(a, b) = 5` 合法；
3. 逗号可以**重载**，这让泛型代码里的 `,` 变得不可信，于是有了 `void()` 惯用法。

## 文法与语义（¶1）

```text
expression:
    assignment-expression
    expression , assignment-expression
```

*expression* 这个非终结符本身就是"逗号表达式"——这就是为什么文法中"需要一个完整表达式"的地方（如 `( expression )`、条件运算符的中间操作数、`for` 的条件）都能出现逗号，而"只要一个赋值表达式"的地方（函数实参、初始化器）不能。

¶1 的规定：

- 逗号运算符**从左往右结合**；
- 一对用逗号分隔的表达式**从左往右求值**；左表达式是一个**弃值表达式**（discarded-value expression，[[expr.context]]）；
- 左表达式**先于**右表达式（sequenced before，[[intro.execution]]）：左边的所有值计算和副作用都在右边开始之前完成；
- 结果的**类型和值**是右操作数的类型和值；结果的**值类别**与右操作数相同；若右操作数是位域，结果也是位域。

```cpp run title="comma-basics.cpp" ok
#include <type_traits>
#include <utility>

int a = 1, b = 2;
static_assert(std::is_same_v<decltype((a, b)), int&>);              // 右操作数是 lvalue
static_assert(std::is_same_v<decltype((a, 3)), int>);               // prvalue
static_assert(std::is_same_v<decltype((a, std::move(b))), int&&>);  // xvalue

int main() {
    (a, b) = 5;                 // OK: 结果是 b 这个左值
    int i = 0;
    int r = (i++, i++, i);      // OK: 从左往右、逐个有序，r == 2
    return (b == 5 && r == 2) ? 0 : 1;
}
```

`(i++, i++, i)` 有定义，而 `i++ + i++` 是 UB——区别就在于逗号规定了顺序，`+` 没有（[[intro.execution#10]]）。

"保留值类别"是 C++ 与 C 的差别：C 中逗号表达式的结果从不是左值。C++ 这样设计，使得逗号表达式能透明地出现在需要左值的地方（例如宏展开中的 `(check(), obj).member = v`）。

### 左操作数是弃值表达式

弃值表达式的规则见 [[expr.context#2]]：结果被丢弃；对某些形式的 `volatile` glvalue 会进行左值到右值转换（即确实读一次）；若是 prvalue 则进行临时量实质化（于是类类型的临时对象会被创建并在完整表达式结束时销毁）。编译器对"左操作数没有效果"的逗号表达式通常给出 `-Wunused-value` 警告，这常常能发现把 `a[i][j]` 误写成 `a[i, j]` 之类的错误。

## 逗号与特殊语境（¶2）

¶2（注 1）：在逗号有特殊含义的语境中——函数调用实参列表（[[expr.call]]）、下标（[[expr.sub]]）、初始化器列表（[[dcl.init]]）、模板实参列表（[[temp.names]]）——逗号**运算符**只能出现在**括号**中。标准的例子：

```cpp run title="comma-context.cpp" ok
int f(int a, int b, int c) { return a * 100 + b * 10 + c; }

int main() {
    int a = 1, t = 0, c = 3;
    int r = f(a, (t = 3, t + 2), c);   // 三个实参，第二个是 5
    return r == 153 ? 0 : 1;
}
```

注意：函数实参之间的逗号**不是**逗号运算符，所以实参之间**没有**顺序保证（C++17 起是"不确定顺序"，[[expr.call]]）。

### 下标中的逗号 {{removed:C++23}}

`a[i, j]` 在 C++20 之前是合法的，含义是 `a[(i, j)]`，即 `a[j]`——几乎总是笔误。C++20 由 [[P1161R3]] **弃用**了下标中不带括号的逗号表达式；C++23 由 [[P2128R6]] 把这个语法**重新利用**为多维下标：`a[i, j]` 现在调用 `a.operator[](i, j)`（可以有多个参数的 `operator[]`，[[over.sub]]）。对内置下标（数组、指针），方括号中必须恰好是一个 *assignment-expression*，所以：

```cpp title="comma-subscript.cpp" error
int main() {
    int arr[3]{};
    int x = arr[1, 2];      // error: 内置下标只接受一个表达式（C++23 起；C++20 弃用，此前等同 arr[2]）
    int y = arr[(1, 2)];    // OK: 带括号的逗号表达式，即 arr[2]
    return x + y;
}
```

参见 [[diff.cpp20.expr]]。`std::mdspan`（C++23）正是利用多维 `operator[]` 写成 `m[i, j]`。

## 重载的逗号

逗号运算符可以重载（[[over.binary]]）。重载后它是一个普通的二元函数调用：

- **C++17 之前**：两个"实参"的求值顺序未指定，逗号的顺序保证消失；
- **C++17 起**：[[over.match.oper#2]] 规定用运算符语法调用重载运算符时，操作数按内置运算符的顺序求值，所以重载的逗号**仍然左先右后**（[[P0145R3]]）。

即便如此，重载逗号仍然很危险：在泛型代码里，`f(x), g(y)` 可能因为 `f` 的返回类型有一个（经 ADL 找到的）`operator,` 而调用到完全意想不到的函数。标准库实现和严谨的泛型代码因此习惯性地把左操作数转为 `void`——`void` 类型的操作数不可能匹配任何用户定义的 `operator,`：

```cpp run title="comma-overload.cpp" ok
#include <cstdio>

struct Evil {
    template<class T>
    friend Evil operator,(Evil, T) { std::puts("evil comma called"); return {}; }
};
Evil make() { return {}; }

int main() {
    make(), 1;          // 调用重载的 operator,（输出一次）
    void(make()), 1;    // 内置逗号：左操作数是 void，不可能匹配重载
}
```

在 `for` 循环中你会看到 `++first1, (void)++first2` 这样的写法（libc++ 和 libstdc++ 的算法实现中很常见），在折叠表达式中则是 `(void(f(args)), ...)`。

## 折叠表达式中的逗号

一元折叠 `(expr, ...)` 展开为 `(e1, (e2, (e3, ...)))` 一类的逗号链（[[expr.prim.fold]]），因此**按顺序**对每个包元素求值，这是在 C++17 中"对每个参数调用一次函数"的标准写法：

```cpp run title="comma-fold.cpp" ok
#include <cstdio>

template<class... Ts>
void print_all(const Ts&... xs) {
    (void(std::printf("%d ", xs)), ...);   // 保证按参数顺序输出；void() 防御重载的逗号
    std::puts("");
}

int main() { print_all(1, 2, 3); }   // 输出 "1 2 3"
```

空包时 `(e, ...)` 展开为 `void()`。

## 常量表达式中的逗号

C++11 起，逗号运算符可以出现在常量表达式中（C++98/03 的整型常量表达式不允许逗号）：`int arr[(1, 2)];` 声明一个 2 元素数组；`static_assert((check(), true));` 也是常见写法。

!!! impl "实现视角"
    内置逗号不产生任何指令：左操作数的代码先生成，结果丢弃，然后生成右操作数。若左操作数没有副作用，它会被完全删除（Clang/GCC 同时给出 `-Wunused-value` 警告）。逗号的"顺序保证"在优化后的代码里只体现为可观察行为的顺序——编译器仍可以按 as-if 规则重排没有可观察差异的计算。

## 陷阱

!!! pitfall "`a[i, j]` 当作二维下标"
    对数组和指针，它在 C++23 起非良构；C++20 前它是 `a[j]`。

!!! pitfall "以为函数实参之间的逗号保证顺序"
    实参分隔符不是逗号运算符。`f(i++, i++)` 的两次自增是不确定顺序的（C++17 起不再是 UB，但结果未指定）。

!!! pitfall "泛型代码中直接写 `f(x), g(y)`"
    可能命中用户重载的 `operator,`。写 `void(f(x)), g(y)`。

!!! pitfall "`return a, b;` 以为返回两个值"
    返回的是 `b`。需要多个值请用 `std::pair`/`std::tuple`/结构体。

## 思考题

!!! question "思考题"
    `int x = 1, y = 2;` 中的逗号是逗号运算符吗？`x = 1, y = 2;`（作为表达式语句）呢？`int z = (x = 1, y = 2);` 中 `z` 的值是多少？

<details markdown="1">
<summary>答案</summary>

- `int x = 1, y = 2;` 中的逗号是**声明符列表**的分隔符，不是运算符：声明了两个变量。
- `x = 1, y = 2;` 是一个表达式语句，其中的逗号**是**逗号运算符：赋值优先级高于逗号，所以是 `(x = 1), (y = 2)`。
- `int z = (x = 1, y = 2);`：括号内是逗号表达式，结果是右操作数 `y = 2` 的结果（`y` 的左值，值为 2），`z == 2`。若去掉括号写 `int z = x = 1, y = 2;`，就变成声明 `z`（初始化为 `x = 1` 的值 1）以及再声明一个新变量 `y`——与外层的 `y` 冲突则非良构。
</details>

## 小结

| 方面 | 规则 |
|---|---|
| 结合与求值 | 从左往右；左先于右（含全部副作用） |
| 左操作数 | 弃值表达式 |
| 结果 | 类型、值、值类别、位域性都取右操作数 |
| 特殊语境 | 函数实参、下标、初始化列表、模板实参中需加括号 |
| 下标中的逗号 | C++20 弃用；C++23 起成为多维下标，内置下标非良构 |
| 重载 | 普通二元函数；C++17 起仍左先右后；用 `void()` 防御 |
