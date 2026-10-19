---
title: 复合表达式
summary: 用运算符把子表达式组合起来的全部表达式，按优先级从紧到松排成的一张地图，以及读每个运算符条款时要找的几项规定。
status: done
related: expr, expr.pre, expr.prim, basic.lval, conv, expr.arith.conv, intro.execution, topics/casts
tags: 表达式, 导读
updated: 2026-10-19
---

!!! tldr
    - 7.6 的子条款顺序就是内置运算符的优先级顺序：越靠前结合得越紧。
    - 后缀表达式（7.6.1）是最紧的一层，函数调用、成员访问、下标、后缀自增、四个具名转换和函数式转换都在这里。
    - C 风格转换 `(T)e` 不在后缀层，单独排在 7.6.3，介于一元运算符和 `.*` 之间。
    - 每个运算符条款规定同样几件事：操作数要求、结果的类型与值类别、求值顺序、哪些情形是 UB。
    - 7.6 描述的都是内置运算符。操作数是类或枚举类型时，运算符可能变成一次函数调用，但求值顺序仍按内置运算符的规则。

```cpp run ok
int main() {
  int a[] = {1, 2, 3};
  int* p = a;
  int x = *p++;     // *(p++)：后缀 ++ 比一元 * 紧
  int y = -a[1];    // -(a[1])：下标比一元 - 紧
  return x + y;     // 1 + (-2)
}
```

`*p++` 为什么是 `*(p++)`？标准里没有优先级表。优先级来自语法：后缀 `++` 的操作数只能是后缀表达式，而一元 `*` 的操作数可以是任何更紧的一层，所以 `*p++` 只有一种分析方式，即 `*` 作用于后缀表达式 `p++`（见 [[expr]] 导读）。**复合表达式**（compound expressions）是第 7.6 节的总称，指所有用运算符把子表达式组合起来的表达式；它的子条款就按这个语法层次从紧到松排列。7.6 本身没有规范性文字。

## 7.6 的地图

| 小节 | 层（非终结符） | 形式 | 本站笔记 | 要点 |
|---|---|---|---|---|
| 7.6.1 | *postfix-expression* | 总览 | [[expr.post]] | 后缀运算符从左到右结合 |
| 7.6.1.2 | | `a[b]` | [[expr.post]] | 内置下标就是 `*((a)+(b))`；C++23 起可有多个实参 |
| 7.6.1.3 | | `f(args)` | [[expr.call]] | 求值顺序、形参的初始化与销毁、可变实参、契约 |
| 7.6.1.4 | | `T(x)` `T{x}` `auto(x)` | [[expr.type.conv]] | 单个圆括号实参时等价于 C 风格转换 |
| 7.6.1.5 | | `a.b` `a->b` | [[expr.ref]] | 结果的类型与值类别、cv 的合并、`mutable` |
| 7.6.1.6 | | `a++` `a--` | [[expr.post]] | 结果是旧值的 prvalue |
| 7.6.1.7 | | `dynamic_cast` | [[expr.dynamic.cast]] | 运行时检查的多态转换 |
| 7.6.1.8 | | `typeid` | [[expr.typeid]] | 多态 glvalue 取动态类型 |
| 7.6.1.9 | | `static_cast` | [[expr.static.cast]] | 隐式转换及其逆、向下转换、`void*` |
| 7.6.1.10 | | `reinterpret_cast` | [[expr.reinterpret.cast]] | 指针与整数互转、无关类型的指针互转 |
| 7.6.1.11 | | `const_cast` | [[expr.const.cast]] | 只改 cv 限定 |
| 7.6.2 | *unary-expression* | `*a` `&a` `-a` `!a` `~a` `++a` `sizeof` `alignof` `noexcept` `new` `delete` `co_await` `^^` | [[expr.unary]] | 一元运算符，右结合 |
| 7.6.3 | *cast-expression* | `(T)e` | [[expr.cast]] | 依次尝试几种具名转换的组合 |
| 7.6.4 | *pm-expression* | `.*` `->*` | [[expr.mptr.oper]] | 成员指针运算 |
| 7.6.5–7.6.6 | *multiplicative / additive* | `* / %`、`+ -` | [[expr.mul]]、[[expr.add]] | 算术；指针算术 |
| 7.6.7 | *shift-expression* | `<< >>` | [[expr.shift]] | C++17 起左操作数先序于右操作数 |
| 7.6.8 | *compare-expression* | `<=>` | [[expr.spaceship]] | 三路比较（C++20） |
| 7.6.9–7.6.10 | *relational / equality* | `< > <= >=`、`== !=` | [[expr.rel]]、[[expr.eq]] | 指针比较中的未指定情形 |
| 7.6.11–7.6.13 | | `& ^ \|` | [[expr.bit.and]]、[[expr.xor]]、[[expr.or]] | 位运算 |
| 7.6.14–7.6.15 | | `&& \|\|` | [[expr.log.and]]、[[expr.log.or]] | 短路求值，左先序于右 |
| 7.6.16 | *conditional-expression* | `a ? b : c` | [[expr.cond]] | 第二、三操作数的公共类型与值类别 |
| 7.6.17 | *yield-expression* | `co_yield` | [[expr.yield]] | 协程产出 |
| 7.6.18 | *throw-expression* | `throw` | [[expr.throw]] | 抛出异常 |
| 7.6.19 | *assignment-expression* | `= += -= …` | [[expr.assign]] | C++17 起右操作数先序于左操作数 |
| 7.6.20 | *expression* | `a, b` | [[expr.comma]] | 左先序于右，结果是右操作数 |

### 为什么 C 风格转换单独排在后面

四个具名转换自带括号，`static_cast<T>(e)` 在语法上和函数调用一样是后缀表达式，所以放在 7.6.1。函数式转换 `T(x)` 也是后缀表达式。C 风格的 `(T)e` 则是 *cast-expression*，它的操作数是另一个 *cast-expression*，结合得比一元运算符松、比 `.*` 紧，所以排在 7.6.3。

```cpp run ok
struct S { int m; };
int main() {
  S s{1};
  S* p = &s;
  long n = (long)p->m;   // (long)(p->m)：-> 比转换紧
  return static_cast<int>(n) - 1;
}
```

把各种转换放在一起比较的专题见 [[topics/casts]]。

## 每个运算符条款规定什么

7.6 下的子条款写法相似，每一条都回答下面几件事：

1. 操作数要求：要 glvalue 还是 prvalue，要不要完整类型，对操作数施行哪些标准转换（[[conv]]）。
2. 结果：类型、值类别（[[basic.lval]]），是否是位域。
3. 求值顺序：操作数之间是先序、非决定性先序还是无序（[[intro.execution]]）。C++17 给下标、移位、赋值、成员访问等运算符补上了顺序。
4. 未定义、未指定和实现定义的情形。

## 与运算符重载的关系

如果某个操作数是类或枚举类型，`a + b` 可能被解释为 `operator+(a, b)` 的调用（[[expr.pre#2]]、[[over.match.oper]]）。这时结果的类型和值类别按函数调用的规则（[[expr.call]]）确定，而不是按 [[expr.add]]。

求值顺序是例外。C++17 起，用运算符写法调用重载运算符时，操作数按内置运算符规定的顺序求值（[[expr.call#8]] 注 8）。所以 `std::cout << f() << g()` 中 `f()` 一定先于 `g()`。重载的 `&&`、`||` 也是左操作数先求值，但两个操作数都会求值，不再短路。

```cpp run ok
#include <cstdio>
#include <sstream>
int f() { std::puts("f"); return 1; }
int g() { std::puts("g"); return 2; }
int main() {
  std::ostringstream os;
  os << f() << g();   // 先输出 f，再输出 g（C++17 起保证）
}
```
