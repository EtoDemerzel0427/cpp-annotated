---
title: 表达式的性质
summary: 7.2 导读：每个表达式都有类型与值类别两个静态属性，并可能处于未求值或弃值的特殊语境
status: draft
related: basic.lval, expr.type, expr.context, topics/value-categories
tags: 导读, 值类别
updated: 2026-10-17
---

[expr.prop] 本身没有正文，只有三个子条款。它们共同回答一个问题：表达式本身有哪些属性。这些属性在看任何具体运算符之前就要确定：

| 子条款 | 讲什么 | 关键概念 |
|---|---|---|
| 7.2.1 [[basic.lval]] | 值类别 | lvalue / xvalue / prvalue，结果对象，glvalue ↔ prvalue 的自动转换，严格别名 |
| 7.2.2 [[expr.type]] | 类型的调整 | 引用被剥去、非类 prvalue 去 cv、复合指针类型 |
| 7.2.3 [[expr.context]] | 语境 | 未求值操作数、弃值表达式 |

## 三者如何配合

可以把任意表达式 `E` 的静态描述写成一个三元组：

> （类型，值类别，是否为位域）

- 类型由各运算符的条款给出，再经 [[expr.type]] 调整：它永远不是引用类型；如果表达式是非类非数组的 prvalue，类型不带 cv。
- 值类别同样由各运算符的条款给出；[[basic.lval]] 给出分类方法，以及运算符需要另一种类别时的自动转换（¶6：glvalue → prvalue；¶7：prvalue → xvalue）。
- 是否为位域：位域 glvalue 不能取地址，也不能绑定到非 const 引用；位域没有纯右值形式（[[basic.lval#6]] 注 7）。

`decltype` 正是把这个三元组的前两项重新编码成一个类型的工具：xvalue → `T&&`，lvalue → `T&`，prvalue → `T`（[[dcl.type.decltype]]）。

语境（[[expr.context]]）则决定表达式是否被求值，以及求值后如何处理结果：

- 在未求值操作数中，表达式只用来确定类型等静态信息（`sizeof`、`decltype`、`noexcept`、约束等）；
- 在弃值语境中，表达式被求值，但结果被丢弃。此时数组和函数不退化，只有特定形式的 volatile glvalue 才会被读取，prvalue 会被实质化。

## 阅读建议

1. 先读 [[basic.lval]] 的 ¶1–¶7，配合专题 [[topics/value-categories]] 建立直观认识；
2. 再读 [[expr.type]]，理解为什么表达式没有引用类型；
3. [[expr.context]] 可以等遇到 volatile、ODR、`sizeof` 相关的问题时再查。

[[basic.lval#6]]、[[basic.lval#7]] 提到的各种转换，会在后面的 [[conv]] 中逐一定义。

!!! summary
    - 表达式的静态属性包括类型（不是引用，标量 prvalue 不带 cv）、值类别（三者之一）以及是否为位域。
    - 语境决定表达式是否求值（未求值操作数），以及结果如何处理（弃值表达式）。
