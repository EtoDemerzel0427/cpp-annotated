---
title: 重载
summary: 第 12 章导读：同名函数怎样共存，一次调用怎样从中选出唯一的函数，以及运算符重载和用户定义字面量的规则。
status: draft
related: over.pre, over.match, over.match.best, over.best.ics, topics/overload-resolution-walkthrough
tags: 重载决议, 导读
updated: 2026-10-19
---

!!! tldr
    - 同一作用域里的同名函数只要形参列表等要素不同，就可以共存，这叫重载；不同作用域的同名函数是隐藏，不是重载。
    - 调用一个重载的名字时，编译器按三步选函数：列出候选函数，筛出可行函数，用隐式转换序列比出唯一的最佳函数。
    - 重载决议只看类型。选中之后才检查访问权限、是否 `= delete`，不合格时程序非良构，不会退回去选第二名。
    - 建议的顺序：[[over.pre]] → [[over.match]] → [[over.match.viable]] → [[over.best.ics]] → [[over.ics.rank]] → [[over.match.best]]，运算符相关的再读 [[over.match.oper]]。

C 没有重载，所以绝对值函数要写成 `abs`、`labs`、`fabs` 三个名字。C++ 允许它们都叫 `abs`，由编译器根据实参类型选择。第 12 章规定的就是这个选择：哪些同名声明可以共存，以及一次调用到底调用哪一个。

```cpp run ok
int    abs(int x)    { return x < 0 ? -x : x; }
double abs(double x) { return x < 0 ? -x : x; }

int main() {
  auto a = abs(1);     // abs(int)：int → int 不需要转换
  auto b = abs(1.0);   // abs(double)
  static_assert(sizeof(a) == sizeof(int) && sizeof(b) == sizeof(double));
}
```

## 哪些声明可以共存

[[over.pre]] 给出重载的定义。两个同名函数能否共存，当前草案用 [[basic.scope.scope]] 的**对应**（correspond）概念判断：形参类型列表（经过数组变指针、去掉顶层 const 等调整之后）、约束、对象形参都相同的两个声明是对应的，它们声明同一个函数，不构成重载。所以只差返回类型的两个声明不能共存。

## 怎样选出一个函数

重载决议（[[over.match]]）在名字查找找到的函数里挑选，分三步：

| 步骤 | 做什么 | 条款 |
|---|---|---|
| 候选函数 | 按调用的语境（普通调用、运算符、构造函数、转换函数等）列出参与竞争的函数 | [[over.match.funcs]]、[[over.match.oper]] |
| 可行函数 | 实参个数对得上、约束满足、每个实参都能隐式转换成对应形参 | [[over.match.viable]] |
| 最佳可行函数 | 逐个实参比较转换的好坏，再按一串决胜规则比较 | [[over.match.best]] |

比较转换好坏的依据是**隐式转换序列**（implicit conversion sequence），也就是把实参转换成形参类型所经过的步骤。[[over.best.ics]] 定义它由哪些转换组成，[[over.ics.rank]] 规定怎样比较两个序列，例如不需要转换优于整型提升，整型提升优于其他转换。

选中之后才检查访问控制、函数是否被删除等，见 [[over.match#3]]。重载决议成功不等于调用合法。

## 运算符与其他

| 条款 | 内容 |
|---|---|
| [[over.match.class.deduct]] | 类模板实参推导：在推导指引上做一次重载决议 |
| [[over.over]] | 取重载函数的地址：`&f` 按目标类型选择 |
| [[over.oper]] | 哪些运算符可以重载，以什么形式声明 |
| [[over.built]] | 为参与重载决议而设想的内建运算符候选 |
| [[over.literal]] | 用户定义字面量 `operator""_km` |

C++20 起，`a < b` 可以改写成 `(a <=> b) < 0`，`a != b` 可以改写成 `!(a == b)`，这些改写候选在 [[over.match.oper]] 里讲，预置的 `==` 和 `<=>` 在 [[class.compare]] 里讲。

## 需要先知道的

重载决议只在名字查找的结果里挑选（[[basic.lookup]]、[[basic.lookup.argdep]]）。查找没有找到的函数，重载决议看不见。隐式转换序列由标准转换（[[conv]]）和用户定义转换（[[class.conv]]）组成，实质上是在模拟用实参复制初始化形参（[[dcl.init]]）。函数模板先经模板实参推导（[[temp.deduct]]）得到特化，再进入重载决议。

[[topics/overload-resolution-walkthrough]] 用逐个实参的转换表，把几个经典的重载决议问题从头推到尾，适合读完本章后练习。
