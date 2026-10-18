---
title: 复合表达式
summary: 7.6 导读：由运算符把子表达式组合起来的全部表达式——后缀、一元、强制转换、成员指针、算术、移位、比较、位运算、逻辑、条件、yield、throw、赋值、逗号——按语法从紧到松排列的地图
status: draft
related: expr, expr.pre, expr.prim, basic.lval, conv, expr.arith.conv, intro.execution, topics/casts
tags: 表达式, 导读
updated: 2026-10-17
---

[[expr.prim]] 讲的是表达式的"原子"：字面量、名字、`this`、lambda……**复合表达式**（compound expressions）是第 7.6 节的总称，涵盖所有"用某个运算符把一个或多个子表达式组合起来"的表达式。7.6 本身没有任何规范性文字，它只是一个容器；但它的**子条款顺序就是运算符的优先级顺序**——这是理解这一节最重要的一把钥匙（见 [[expr]] 导读中"标准里没有优先级表"一节）。

读每个子条款时，可以带着同样的五个问题：

1. **语法**：操作数是哪一级非终结符？（这决定优先级与结合性。）
2. **操作数要求**：要求 glvalue 还是 prvalue？要不要完整类型？施行哪些标准转换（[[conv]]）？
3. **结果**：类型是什么？值类别是什么（[[basic.lval]]）？是不是位域？
4. **求值顺序**：操作数之间是先序、非决定性先序，还是无序（[[intro.execution]]）？C++17 为多个运算符补上了顺序。
5. **未定义 / 未指定 / 实现定义的情形**：什么时候 UB？

## 7.6 的地图

| 小节 | 非终结符 | 形式 | 本站笔记 | 一句话 |
|---|---|---|---|---|
| 7.6.1 | *postfix-expression* | 总览 | [[expr.post]] | 后缀表达式从左到右结合 |
| 7.6.1.2 | | `a[b]` | [[expr.sub]] | 内置下标 ≡ `*((a)+(b))`；C++23 起逗号分隔多实参 |
| 7.6.1.3 | | `f(args)` | [[expr.call]] | 函数调用：求值顺序、形参初始化与销毁、可变实参、契约 |
| 7.6.1.4 | | `T(x)` `T{x}` `auto(x)` | [[expr.type.conv]] | 函数式转换：单个实参时等价于 C 风格转换 |
| 7.6.1.5 | | `a.b` `a->b` | [[expr.ref]] | 成员访问：结果的类型与值类别、cv 传播、`mutable` |
| 7.6.1.6 | | `a++` `a--` | [[expr.post.incr]] | 后缀自增：结果是旧值的 prvalue |
| 7.6.1.7 | | `dynamic_cast` | [[expr.dynamic.cast]] | 运行期检查的多态转换 |
| 7.6.1.8 | | `typeid` | [[expr.typeid]] | 类型识别：多态 glvalue 取动态类型 |
| 7.6.1.9 | | `static_cast` | [[expr.static.cast]] | "有道理的"转换：隐式转换及其逆、向下转换、`void*` |
| 7.6.1.10 | | `reinterpret_cast` | [[expr.reinterpret.cast]] | 重新解释位置/位模式：指针 ↔ 整数、无关指针 |
| 7.6.1.11 | | `const_cast` | [[expr.const.cast]] | 只改 cv 限定 |
| 7.6.2 | *unary-expression* | `*a` `&a` `-a` `!a` `~a` `++a` `sizeof` `alignof` `noexcept` `new` `delete` `co_await` `^^` | [[expr.unary]] | 一元运算符（右结合） |
| 7.6.3 | *cast-expression* | `(T)e` | [[expr.cast]] | C 风格转换：依次尝试五种具名转换组合 |
| 7.6.4 | *pm-expression* | `.*` `->*` | [[expr.mptr.oper]] | 成员指针运算 |
| 7.6.5–7.6.6 | *multiplicative / additive* | `* / %`、`+ -` | [[expr.mul]]、[[expr.add]] | 算术；指针算术 |
| 7.6.7 | *shift-expression* | `<< >>` | [[expr.shift]] | 移位；C++17 起左操作数先序于右操作数 |
| 7.6.8 | *compare-expression* | `<=>` | [[expr.spaceship]] | 三路比较（C++20） |
| 7.6.9–7.6.10 | *relational / equality* | `< > <= >=`、`== !=` | [[expr.rel]]、[[expr.eq]] | 比较；指针比较的未指定情形 |
| 7.6.11–7.6.13 | | `& ^ \|` | [[expr.bit.and]]、[[expr.xor]]、[[expr.or]] | 位运算 |
| 7.6.14–7.6.15 | | `&& \|\|` | [[expr.log.and]]、[[expr.log.or]] | 短路求值，左先序于右 |
| 7.6.16 | *conditional-expression* | `a ? b : c` | [[expr.cond]] | 条件运算符：复杂的公共类型 / 值类别规则 |
| 7.6.17 | *yield-expression* | `co_yield` | [[expr.yield]] | 协程产出 |
| 7.6.18 | *throw-expression* | `throw` | [[expr.throw]] | 抛出异常 |
| 7.6.19 | *assignment-expression* | `= += -= …` | [[expr.assign]] | 赋值；C++17 起右操作数先序于左操作数 |
| 7.6.20 | *expression* | `a, b` | [[expr.comma]] | 逗号：左先序于右，结果是右操作数 |

!!! note "为什么 `expr.cast` 不挨着其他转换？"
    四个具名转换（`static_cast` 等）在语法上是**后缀表达式**（它们自带括号，像函数调用一样紧），所以住在 7.6.1；而 C 风格的 `(T)e` 是 *cast-expression*，它的操作数是另一个 *cast-expression*，优先级介于一元运算符和 `.*` 之间，所以单独排在 7.6.3。函数式转换 `T(x)` 也是后缀表达式（7.6.1.4）。把这些转换放在一起讲的专题见 [[topics/casts]]。

## 后缀表达式的地位

后缀表达式是优先级最高的一层运算符，而且它们**左结合**：`a.b[c](d)->e++` 从左到右依次套上去。这一层聚集了几乎所有"需要特殊规则"的操作——函数调用、成员访问、下标和五种转换——所以 7.6.1 是整个第 7 章里篇幅最大、被引用最多的部分之一。阅读建议：

1. 先读 [[expr.post]]（语法与下标、后缀自增），对"后缀"这一层有个整体印象；
2. 再读 [[expr.call]] 和 [[expr.ref]]：这两节定义了"调用"和"成员访问"的值类别规则，后面的运算符重载、`std::invoke`、移动语义都依赖它们；
3. 然后读四个具名转换：[[expr.static.cast]] → [[expr.const.cast]] → [[expr.reinterpret.cast]] → [[expr.dynamic.cast]]，最后读把它们串起来的 [[expr.cast]]；
4. [[expr.typeid]] 与 [[expr.dynamic.cast]] 一起读，它们共享 RTTI 机制。

## 与运算符重载的关系

7.6 下的每一条描述的都是**内置**运算符。若操作数之一是类或枚举类型，`a + b` 可能被解释为 `operator+(a, b)` 的调用，此时适用的是函数调用（[[expr.call]]）的规则，而不是 [[expr.add]] 的规则（见 [[expr.pre#2]] 与 [[over.match.oper]]）。但有一个重要例外：C++17 之后，**以运算符写法**调用重载运算符时，操作数的求值顺序按内置运算符的规则（[[expr.call]] 注 8），所以 `std::cout << f() << g()` 中 `f()` 一定先于 `g()`。

## 小结

!!! summary
    - 7.6 是一个容器条款，子条款按优先级从高到低排列；优先级是语法的推论。
    - 每读一个运算符，问五件事：语法、操作数要求、结果类型与值类别、求值顺序、UB。
    - 后缀表达式（7.6.1）是最复杂的一层：调用、成员访问、下标、五种转换中的四种都在这里；C 风格转换单独在 7.6.3。
