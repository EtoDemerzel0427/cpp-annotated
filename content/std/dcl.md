---
title: 声明
summary: 第 9 章导读：一个声明如何拆成说明符 + 声明符 + 初始化器，以及函数定义、结构化绑定、枚举、命名空间、using、asm、链接规格、属性各自在哪一节
status: draft
related: dcl.pre, dcl.spec, dcl.decl, dcl.init, basic.pre, basic.def
tags: 声明, 导读
updated: 2026-10-17
---

第 9 章 [dcl] 回答的问题是：一行声明到底声明了什么。第 6 章（[[basic.pre]]、[[basic.def]]）给出了名字、实体、声明、定义这些抽象概念；第 9 章则给出具体的语法，以及从语法到语义（类型、存储期、链接、是否 inline、是否 constexpr 等）的映射规则。

读这一章之前，需要先熟悉作用域与名字的引入（[[basic.scope]]）、声明与定义的区别（[[basic.def]]）、ODR（[[basic.def.odr]]）、链接（[[basic.link]]）和存储期（[[basic.stc]]）。

## 一个声明的三段式

最常见的声明是 *simple-declaration*，它在语法上分为三段（[[dcl.pre#4]]）：

```text
[[属性]]   static constexpr unsigned long   *const p = nullptr, a[3] = {};
└ 属性 ┘   └──── decl-specifier-seq ────┘   └── init-declarator-list ──────┘
                                              声明符 + 初始化器（逗号分隔）
```

- **说明符**（*decl-specifier*，9.2）作用于整行声明中的每一个被声明的名字，如 `static`、`constexpr`、类型说明符 `unsigned long` 等。
- **声明符**（*declarator*，9.3）只作用于一个名字：`*const p` 中的 `*const` 只属于 `p`，`[3]` 只属于 `a`。这就是 `int* a, b;` 中 `b` 不是指针的根本原因。
- **初始化器**（*initializer*，9.5）跟在各自的声明符后面。

类型的确定分两步：先由 *decl-specifier-seq* 里的定义类型说明符（*defining-type-specifier*）给出基础类型，再由声明符从内向外逐层包装（[[dcl.meaning]]）。说明符里非类型的部分（`static`、`inline`、`constexpr` 等）不参与类型构造，只决定存储期、链接、是否 inline 等性质。

```cpp run ok
#include <type_traits>
int* a, b;             // a: int*，b: int —— * 是声明符的一部分
typedef int* IP;
IP c, d;               // c、d 都是 int* —— 类型来自说明符
static_assert(std::is_same_v<decltype(b), int>);
static_assert(std::is_same_v<decltype(d), int*>);
int main() { }
```

## 本章的组织方式

| 小节 | 内容 | 本站笔记 |
|---|---|---|
| 9.1 | 序言：声明的总语法；*simple-declaration*、`static_assert`、`consteval` 块、空声明、属性声明 | [[dcl.pre]] |
| 9.2 | 说明符：存储类、函数说明符、`typedef`、`friend`、`constexpr`/`consteval`、`constinit`、`inline`、类型说明符（cv、简单类型、包索引、详述类型、`decltype`、`auto`、CTAD、类型拼接） | [[dcl.spec]] 及子页 |
| 9.3 | 声明符：指针、引用、成员指针、数组、函数（含默认实参）；类型名（*type-id*）；歧义消解（最令人烦恼的解析） | [[dcl.decl]] |
| 9.4 | 函数契约说明符 `pre` / `post` {{c++26}} | [[dcl.contract]] |
| 9.5 | 初始化器：默认/值/零初始化、聚合初始化、字符数组、引用绑定、列表初始化 | [[dcl.init]] |
| 9.6 | 函数定义：`= default`、`= delete`、协程、可替换函数 | [[dcl.fct.def]] |
| 9.7 | 结构化绑定 | [[dcl.struct.bind]] |
| 9.8 | 枚举与 `using enum` | [[dcl.enum]]、[[enum.udecl]] |
| 9.9 | 命名空间：定义、无名命名空间、别名、using 指令 | [[basic.namespace]] |
| 9.10 | using 声明 | [[namespace.udecl]] |
| 9.11 | `asm` 声明 | [[dcl.asm]] |
| 9.12 | 链接规格 `extern "C"` | [[dcl.link]] |
| 9.13 | 属性 | [[dcl.attr]] |

可以把 9.1–9.6 看作声明的通用机制，9.7–9.13 则是若干特殊形式的声明，各有独立的语法。

## 说明符 vs 声明符：为什么要分两层？

这种设计继承自 C，即声明仿照使用（declaration mirrors use）：`int *p[3];` 读作 `*p[i]` 是一个 `int`。声明符的语法和表达式的语法同构，优先级也一样（后缀 `[]`、`()` 比前缀 `*` 结合得更紧）。代价是：

1. 一行声明多个名字时，指针/引用/数组/函数这些修饰只属于各自的名字；
2. 复杂类型（函数指针数组之类）要靠括号改变结合（`int (*fp)(int);`）；
3. 语法上产生大量歧义，需要按 [[dcl.ambig.res]] 的原则（凡是能解析为声明的都按声明解析）来裁决。

C++ 在这套机制上又加了大量说明符：`constexpr`、`consteval`、`constinit`、`inline`、`friend`、`explicit(bool)`、占位类型 `auto`/`decltype(auto)`、CTAD 的模板名等。它们的共同点是**作用于整行声明**，并且不（直接）改变声明符包装出来的类型结构。

!!! lawyer "说明符可以随便排列"
    *decl-specifier-seq* 中各说明符的顺序不受语法约束，`int const static x = 0;`、`long unsigned long y;` 都合法（[[dcl.type.simple#4]]）。只有一点和顺序有关：在 *decl-specifier-seq* 里遇到一个类型名时，它是否算作说明符（[[dcl.spec.general#3]]）。

## 本章与其他章的边界

- 类的定义（*class-specifier*）在语法上是一种类型说明符，但内容在第 11 章 [[class]]；成员声明用 *member-declaration* 语法，复用了本章的说明符与声明符。
- 模板声明在第 13 章 [[temp]]；本章的很多规则（如占位类型推导 [[dcl.type.auto.deduct]]）借用了模板实参推导（[[temp.deduct.call]]）。
- 模块相关的声明（`export`、`import`）在第 10 章 [[module]]。
- 初始化的时机（静态初始化 vs 动态初始化）在 [[basic.start]]；本章 9.5 只管用什么值、怎样初始化。

## 建议的阅读路线

1. [[dcl.pre]]：声明的总语法与 `static_assert`。
2. [[dcl.spec.general]] → [[dcl.type]]：说明符如何组合；顺带弄清 `typedef` 名在什么时候被当作所声明的名字这类问题。
3. 按需阅读 [[dcl.stc]]、[[dcl.inline]]、[[dcl.constexpr]]、[[dcl.constinit]]：它们决定了变量和函数的存储期、链接、ODR 行为与常量求值资格。
4. [[dcl.type.decltype]]、[[dcl.spec.auto]]、[[dcl.type.class.deduct]]：现代 C++ 的三种类型推导机制。
5. 然后进入 [[dcl.decl]] 与 [[dcl.init]]。

!!! summary "小结"
    - 声明 = 说明符（作用于整行）+ 声明符（作用于单个名字）+ 初始化器。
    - 9.2 决定性质与基础类型，9.3 决定类型的包装结构，9.5 决定初值，9.6 决定函数体。
    - 9.7 之后是各种特殊声明形式；类、模板、模块的声明分别在第 11、13、10 章。
