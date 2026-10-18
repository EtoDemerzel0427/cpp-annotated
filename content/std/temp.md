---
title: 模板
summary: 第 13 章导读：模板如何声明、如何被命名与给出实参、如何被约束、模板中的名字如何决议、何时实例化与特化、实参如何推导——以及读这一章时最容易混淆的几组概念。
status: draft
related: temp.pre, temp.param, temp.names, temp.arg, temp.constr, temp.type, temp.concept, topics/concepts
tags: 模板, 泛型编程
updated: 2026-10-17
---

第 13 章 [temp] 是整本核心语言标准里篇幅最大、最"法律化"的一章。它回答的不是"模板能做什么"，而是一组非常机械的问题：

1. 一个模板**声明**长什么样，哪些实体可以是模板，哪些实体"沾上了模板"（templated）？
2. 模板形参有哪几种，各自能接受什么样的实参？`template<auto>`、类类型的常量模板形参、概念模板形参分别有什么限制？
3. 一个 `X<...>` 写出来之后，`<` 到底是不是小于号？这个 *template-id* 是否**有效**？两个 *template-id* 什么时候指同一个类型？
4. 约束（constraints）如何被规范化、如何判定满足、如何比较"谁更受约束"？
5. 模板定义中的名字什么时候查找、在哪里查找（两阶段查找）？
6. 特化什么时候被实例化？显式特化、部分特化、显式实例化之间是什么关系？
7. 函数模板的实参如何推导，失败时（SFINAE）是硬错误还是安静地退出重载集？

读这一章之前，最好已经熟悉：名字查找（[[basic.lookup]]）、ODR（[[basic.def.odr]]）、常量表达式（[[expr.const]]）、重载决议（[[over.match]]）。第 13 章大量借用这些概念，而且往往在它们之上再加一层"待决"（dependent）的修饰。

## 本章地图

按"从声明到使用"的顺序，第 13 章可以分成六块：

| 块 | 节 | 内容 | 本站笔记 |
|---|---|---|---|
| **声明** | 13.1 [[temp.pre]] | *template-head*、可模板化的声明、templated entity、*requires-clause* 的位置 | [[temp.pre]] |
| | 13.2 [[temp.param]] | 五种模板形参；结构化类型；默认模板实参；形参包 | [[temp.param]] |
| | 13.7 [[temp.decls]] | 类模板成员、成员模板、变参模板、友元、部分特化、函数模板重载与偏序、别名模板、概念定义 | [[temp.concept]] 等 |
| **名字与实参** | 13.3 [[temp.names]] | *template-id* 的文法、`<` 的消歧、`template` 关键字、`>>`、有效性、concept-id | [[temp.names]] |
| | 13.4 [[temp.arg]] | 类型/常量/模板模板实参各自的匹配规则；访问检查 | [[temp.arg]] |
| | 13.6 [[temp.type]] | 两个 *template-id* 何时相同；模板实参等价 | [[temp.type]] |
| **约束** | 13.5 [[temp.constr]] | 约束的五种形式、满足、规范化、按约束偏序 | [[temp.constr]]、[[temp.constr.order]] |
| **名字决议** | 13.8 [[temp.res]] | 待决名、待决类型/表达式、两阶段查找、实例化点 | — |
| **实例化与特化** | 13.9 [[temp.spec]] | 隐式实例化、显式实例化、显式特化 | — |
| **函数模板特化** | 13.10 [[temp.fct.spec]] | 显式模板实参、模板实参推导（SFINAE 的出处）、重载决议中的模板 | — |

专题 [[topics/concepts]] 把散落在 [[temp.constr]]、[[temp.concept]]、[[expr.prim.req]]、[[over.match.best]] 里的概念相关规则串成一条线。

## 贯穿全章的几个思想

### 1. 模板不是实体的"宏"，而是一族实体的生成器

[[temp.pre#1]]：模板定义的是**一族**类、函数或变量，一个类型族的别名，或者一个概念。模板本身并不是类、函数或变量；它的**特化**（specialization）才是。`std::vector` 不是类型，`std::vector<int>` 才是。这一区分在全章反复出现：

- 特化可以由实例化**隐式**生成，也可以由程序员**显式**提供（[[temp.spec]]）；
- 一个模板的特化与任何其他模板的特化都不同（[[temp.pre#6]]）；
- 但**概念**是例外：概念不会被实例化，concept-id 是一个 `bool` prvalue，而不是"概念的特化"（[[temp.concept#5]]、[[temp.names#15]]）。

### 2. "templated"：不是模板，但沾了模板

C++ 中大量实体本身不是模板，却定义在模板之内：类模板的成员函数、函数模板里的局部类、泛型 lambda 的闭包类型……[[temp.pre#8]] 把它们统称为 **templated entity**。很多规则（例如"只有 templated 函数才能有尾随 *requires-clause*"、[[stmt.select]] 中 `if constexpr` 的弃置语句不被实例化）的适用范围就是 templated entity，而不是"模板"。

### 3. 待决与非待决：两阶段

模板定义里的每个构造，要么**待决**（依赖模板形参，等到实例化才能确定），要么**非待决**（在定义处就能确定）。非待决的东西在定义处就检查（第一阶段），待决的东西推迟到实例化（第二阶段）。这一思想渗透到：

- `<` 的解析与 `template` 关键字（[[temp.names#7]]）；
- *template-id* 的约束只在实参都非待决时才检查（[[temp.names#14]]）；
- 模板定义"不可能有任何有效特化"时 IFNDR（[[temp.res]]）。

### 4. 等价（equivalent）与功能等价（functionally equivalent）

两个涉及模板形参的表达式何时被视为"相同"？[[temp.over.link]] 给出了**等价**的定义——按 ODR 的记号比较，而不是按语义比较。如果两个构造语义相同但写法不同（功能等价而不等价），而程序的含义又取决于它们是否相同，那么程序 IFNDR。这条规则在函数模板重声明、约束的原子性比较（[[temp.constr.atomic#2]]）中都起作用，也是 [[temp.constr.order|概念包含关系]]"必须用同一个具名概念"的根源。

### 5. 大量的 IFNDR

第 13 章是标准里 IFNDR（ill-formed, no diagnostic required）最密集的地方。原因很简单：模板被分别编译在不同 TU 里，实例化点可能有多个，而编译器不可能跨 TU、跨实例化点比较一切。典型的 IFNDR 包括：

- 隐式实例化处看不到函数模板的定义，又没有显式实例化（[[temp.pre#10]]）；
- 同一个原子约束在程序不同位置的满足结果不同（[[temp.constr.atomic#3]]）；
- 偏特化在实例化点不可达、而它本应被选中（[[temp.arg.template#2]]）；
- 约束规范化中形成了无效类型（[[temp.constr.normal]]）。

## C++26 草案中本章的主要变化

{{c++26}} 当前草案相对 C++23 在本章的变化很多，读者在后面各页会反复遇到：

- **术语**：原来的"非类型模板形参"（non-type template parameter）在草案中改称**常量模板形参**（constant template parameter），"非类型模板实参"相应改称常量模板实参。本站新写的页面统一使用新术语，并在首次出现处注明旧称。
- **概念模板形参与变量模板模板形参**（[[temp.param]]）：模板模板形参不再只能接受类模板/别名模板。
- **折叠展开约束**（fold expanded constraint，[[temp.constr.fold]]）：`(C<T> && ...)` 之间可以比较包含关系。
- **包索引**：`Ts...[N]` 与 *pack-index-template-name*（[[temp.names]]）。
- **静态反射**：*splice-specifier* 可以出现在模板实参列表前（[[temp.names#7]]），`std::meta::info` 可以作为常量模板实参（[[temp.type#2]]）。

## 阅读建议

- 第一次读：[[temp.pre]] → [[temp.param]] → [[temp.names]] → [[temp.arg]] → [[temp.type]]，建立"模板 = 头 + 声明；*template-id* = 名字 + 实参"的基本模型。
- 想搞懂 concepts：[[temp.concept]] → [[expr.prim.req]] → [[temp.constr]] → [[temp.constr.order]]，或者直接读专题 [[topics/concepts]]。
- 想搞懂"为什么这里要写 `typename`/`template`"：[[temp.names#7]] 与 [[temp.res]]。
- 想搞懂 SFINAE：[[temp.deduct]]。
