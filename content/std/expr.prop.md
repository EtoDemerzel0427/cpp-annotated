---
title: 表达式的性质
summary: 7.2 导读：每个表达式都有类型与值类别两个静态属性，并可能处于未求值或弃值的特殊语境
status: draft
related: basic.lval, expr.type, expr.context, topics/value-categories
tags: 导读, 值类别
updated: 2026-10-17
---

[expr.prop] 本身没有正文，只有三个子条款。它们共同回答"一个表达式**本身**有哪些属性"——在看任何具体运算符之前就要确定的东西：

| 子条款 | 讲什么 | 关键概念 |
|---|---|---|
| 7.2.1 [[basic.lval]] | **值类别** | lvalue / xvalue / prvalue，结果对象，glvalue ↔ prvalue 的自动转换，严格别名 |
| 7.2.2 [[expr.type]] | **类型**的调整 | 引用被剥去、非类 prvalue 去 cv、复合指针类型 |
| 7.2.3 [[expr.context]] | **语境** | 未求值操作数、弃值表达式 |

## 三者如何配合

可以把任意表达式 `E` 的静态描述写成一个三元组：

> （**类型**，**值类别**，是否为位域）

- **类型**由各运算符的条款给出，然后经 [[expr.type]] 调整：永远不是引用类型；若是非类非数组的 prvalue，则不带 cv。
- **值类别**同样由各运算符条款给出；[[basic.lval]] 给出分类法，以及当运算符需要另一种类别时的自动转换（¶6：glvalue → prvalue；¶7：prvalue → xvalue）。
- **是否为位域**：位域 glvalue 不能被取地址、不能绑定到非 const 引用；位域没有纯右值形式（[[basic.lval#6]] 注 7）。

`decltype` 正是把这个三元组（的前两项）重新编码成一个类型的工具：xvalue → `T&&`，lvalue → `T&`，prvalue → `T`（[[dcl.type.decltype]]）。

**语境**（[[expr.context]]）则决定这个表达式是否会被求值、以及求值后如何处理结果：

- 在未求值操作数中，表达式只用于"问类型"（`sizeof`、`decltype`、`noexcept`、约束……）；
- 在弃值语境中，表达式被求值但结果丢弃，此时数组/函数不退化、只有 volatile glvalue 的特定形式才会被读取、prvalue 会被实质化。

## 阅读建议

1. 先读 [[basic.lval]] 的 ¶1–¶7，配合专题 [[topics/value-categories]] 建立直觉；
2. 再读 [[expr.type]]，理解"表达式没有引用类型"；
3. [[expr.context]] 可以在遇到 volatile、ODR、`sizeof` 问题时再查。

后续的 [[conv]] 会把 [[basic.lval#6]]、[[basic.lval#7]] 提到的各种转换逐一定义。

!!! summary
    - 表达式的静态属性 = 类型（无引用、标量 prvalue 无 cv）+ 值类别（三选一）+ 是否位域。
    - 语境决定是否求值（未求值操作数）以及结果如何被处理（弃值表达式）。
