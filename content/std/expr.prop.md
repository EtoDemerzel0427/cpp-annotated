---
title: 表达式的性质
summary: 不看具体运算符，每个表达式都有类型和值类别两个静态属性，并且可能出现在不求值或弃值的语境中；7.2 的三个子条款分别讲这三件事。
status: done
related: basic.lval, expr.type, expr.context, topics/value-categories
tags: 导读, 值类别
updated: 2026-10-19
---

!!! tldr
    - 每个表达式都有一个类型和一个值类别（lvalue、xvalue、prvalue 三者之一），各运算符的条款负责给出它们。
    - 表达式的类型永远不是引用类型；非类、非数组的 prvalue 的类型不带 cv。
    - 运算符需要另一种值类别时，标准会自动插入转换：glvalue 变 prvalue（读值），prvalue 变 xvalue（实质化临时对象）。
    - 同一个表达式出现在 `sizeof` 里不会被求值，单独写成一条语句时被求值但结果被丢弃，这两种语境各有专门规则。

[expr.prop] 本身没有正文，只有三个子条款：

| 子条款 | 回答的问题 |
|---|---|
| 7.2.1 [[basic.lval]] | 表达式属于哪种值类别；类别不符时怎样自动转换；什么时候可以通过别的类型访问一个对象（严格别名） |
| 7.2.2 [[expr.type]] | 引用类型和 cv 限定怎样从表达式的类型上去掉；两个指针比较时统一成什么类型（复合指针类型） |
| 7.2.3 [[expr.context]] | 未求值操作数和弃值表达式：表达式是否被求值，结果怎样处理 |

## 一个表达式的静态描述

```cpp ok
#include <type_traits>
#include <utility>
int x = 0;
int& r = x;

static_assert(std::is_same_v<decltype((r)), int&>);             // 类型 int，lvalue
static_assert(std::is_same_v<decltype((std::move(x))), int&&>); // 类型 int，xvalue
static_assert(std::is_same_v<decltype((x + 1)), int>);          // 类型 int，prvalue
```

三个表达式的类型都是 `int`，区别只在值类别。`decltype((e))` 把这两个属性编码成一个类型：lvalue 编码为 `T&`，xvalue 编码为 `T&&`，prvalue 编码为 `T`（[[dcl.type.decltype]]）。`r` 虽然声明为引用，表达式 `r` 的类型仍是 `int`，因为 [[expr.type]] 在分析表达式之前就把引用去掉了。

**值类别**（[[g:value-category]]）描述表达式产生的是什么：**左值**（lvalue）指代一个已经存在的对象或函数；**亡值**（xvalue）也指代一个对象，但它的资源可以被拿走；**纯右值**（prvalue）不指代对象，只用来初始化一个对象或算出一个值。详细定义和判断方法见 [[basic.lval]] 和专题 [[topics/value-categories]]。

内置运算符对操作数的值类别有要求，不符合时由 [[basic.lval]] 自动转换。例如 `x + 1` 中 `+` 需要 prvalue，`x` 是左值，于是对 `x` 施行左值到右值转换，也就是读出它的值；`f().m` 中成员访问需要一个对象，`f()` 是 prvalue，于是先实质化出一个临时对象。这些转换本身定义在 [[conv]]。

## 求值的语境

```cpp ok
int calls = 0;
int f() { return ++calls; }

auto a = sizeof(f());      // f 不会被调用：未求值操作数
void g() { f(); }          // f 被调用，返回值被丢弃：弃值表达式
```

`sizeof`、`decltype`、`noexcept` 的操作数是**未求值操作数**，只用来确定类型等静态信息。单独成句的 `f();`、逗号左边的表达式、`(void)e` 是**弃值表达式**，会被求值但结果不用。[[expr.context]] 规定了这两种语境的细节，比如弃值表达式什么时候会真的读取一个 `volatile` 对象。

建议的阅读顺序是先读 [[basic.lval]] 的前几段，再读 [[expr.type]]；[[expr.context]] 可以等遇到 `volatile`、ODR 或 `sizeof` 的问题时再查。
