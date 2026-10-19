---
title: 声明
summary: 第 9 章导读：一条声明由说明符、声明符和初始化器组成；说明符作用于整条声明，声明符只作用于一个名字；各小节分别讲什么。
status: draft
related: dcl.pre, dcl.spec, dcl.decl, dcl.init, basic.pre, basic.def
tags: 声明, 导读
updated: 2026-10-19
---

!!! tldr
    - 一条普通声明分三段：说明符序列、声明符、初始化器。`int* a, b;` 中 `b` 不是指针，因为 `*` 属于声明符 `*a`，不属于说明符 `int`。
    - 说明符（`static`、`constexpr`、`unsigned long` 等）作用于这条声明里的每个名字；声明符（`*`、`&`、`[3]`、`(int)`）只作用于它自己那个名字。
    - 变量的类型由说明符里的类型说明符给出基础类型，再由声明符一层层包装出来；`static`、`inline` 这类说明符不影响类型。
    - 9.1–9.6 是声明的通用机制（说明符、声明符、初始化、函数定义），9.7–9.13 是结构化绑定、枚举、命名空间、`using`、`asm`、链接规格、属性这些特殊形式。

第 6 章（[[basic.pre]]、[[basic.def]]）定义了名字、实体、声明、定义这些概念。第 9 章给出声明的具体语法，以及从语法得出类型、存储期、链接、是否 inline、是否 constexpr 的规则。

## 一条声明的三段

```cpp run ok
#include <type_traits>
int* a, b;             // a 是 int*，b 是 int
typedef int* IP;
IP c, d;               // c、d 都是 int*：指针来自说明符 IP
static_assert(std::is_same_v<decltype(b), int>);
static_assert(std::is_same_v<decltype(d), int*>);
int main() { }
```

最常见的声明是 *simple-declaration*，它分成三段（[[dcl.pre#4]]）：

```text
[[属性]]   static constexpr unsigned long   *const p = nullptr, a[3] = {};
└ 属性 ┘   └──── decl-specifier-seq ────┘   └──── init-declarator-list ────┘
                                              声明符和各自的初始化器，逗号分隔
```

- **说明符**（*decl-specifier*，9.2）作用于这条声明的每一个名字，例如 `static`、`constexpr` 和类型说明符 `unsigned long`。
- **声明符**（*declarator*，[[g:declarator]]，9.3）只作用于一个名字：`*const` 只属于 `p`，`[3]` 只属于 `a`。
- **初始化器**（*initializer*，9.5）跟在各自的声明符后面。

类型分两步得出：先由说明符序列里的类型说明符给出基础类型，再由声明符从名字向外逐层包装（[[dcl.meaning]]）。上例中 `p` 是 `unsigned long* const`，`a` 是 `const unsigned long[3]`（`constexpr` 让对象带 const）。说明符里不表示类型的部分，如 `static`、`inline`、`constexpr`，决定的是存储期、链接这些性质，不参与类型的包装结构。

说明符之间的顺序是自由的：*decl-specifier-seq* 的语法就是任意说明符的序列，`int const static x = 0;` 合法；`unsigned long` 这类多个词组成的类型也可以和其他说明符穿插，`long static unsigned long y = 0;` 同样合法（[[dcl.type.simple#4]]）。与顺序有关的只有一条：说明符序列里出现一个类型名时，它算说明符还是被声明的名字（[[dcl.spec.general#3]]）。

## 为什么分说明符和声明符两层

这套语法继承自 C，C 的设计原则是声明仿照使用：`int *p[3];` 读作表达式 `*p[i]` 的类型是 `int`。声明符的语法和表达式同构，优先级也相同，后缀的 `[]`、`()` 比前缀的 `*` 结合得紧。由此带来三个后果：

1. 一条声明里声明多个名字时，指针、引用、数组、函数这些修饰只属于各自的名字；
2. 函数指针、指向数组的指针这类类型要用括号改变结合，如 `int (*fp)(int);`；
3. 语法上产生大量歧义，由 [[stmt.ambig]] 和 [[dcl.ambig.res]] 裁决，原则是能读成声明的就读成声明。

C++ 在这套机制上又加了许多说明符：`constexpr`、`consteval`、`constinit`、`inline`、`friend`、`explicit`、占位类型 `auto` 和 `decltype(auto)`、用于 CTAD 的模板名等。它们都写在说明符序列里，作用于整条声明。

## 本章各节

| 小节 | 内容 | 本站页面 |
|---|---|---|
| 9.1 | 声明的总语法；`static_assert`、`consteval` 块、空声明、属性声明 | [[dcl.pre]] |
| 9.2 | 说明符：存储类、函数说明符、`typedef`、`friend`、`constexpr`/`consteval`、`constinit`、`inline`、各种类型说明符 | [[dcl.spec]] 及其子页 |
| 9.3 | 声明符：指针、引用、成员指针、数组、函数、默认实参；类型名；歧义消解 | [[dcl.decl]] |
| 9.4 | {{c++26}} 函数契约说明符 `pre`、`post` | [[dcl.contract]] |
| 9.5 | 初始化：默认、值、零初始化，聚合初始化，引用绑定，列表初始化 | [[dcl.init]] |
| 9.6 | 函数定义：`= default`、`= delete`、协程 | [[dcl.fct.def]] |
| 9.7 | 结构化绑定 | [[dcl.struct.bind]] |
| 9.8 | 枚举与 `using enum` | [[dcl.enum]]、[[enum.udecl]] |
| 9.9 | 命名空间、无名命名空间、命名空间别名、using 指令 | [[basic.namespace]] |
| 9.10 | using 声明 | [[namespace.udecl]] |
| 9.11 | `asm` 声明 | [[dcl.asm]] |
| 9.12 | 链接规格 `extern "C"` | [[dcl.link]] |
| 9.13 | 属性 | [[dcl.attr]] |

与其他章的分工：类的定义在语法上是一种类型说明符，但内容在第 11 章 [[class]]；模板声明在第 13 章 [[temp]]，本章的占位类型推导（[[dcl.type.auto.deduct]]）借用了模板实参推导；`export` 和 `import` 在第 10 章 [[module]]；变量在什么时候初始化（静态初始化还是动态初始化）在 [[basic.start]]，9.5 只规定用什么值、怎样初始化。

## 阅读顺序

1. [[dcl.pre]]：声明的总语法和 `static_assert`。
2. [[dcl.spec]]、[[dcl.type]]：说明符怎样组合，类型名什么时候是被声明的名字。
3. 按需阅读 [[dcl.stc]]、[[dcl.inline]]、[[dcl.constexpr]]、[[dcl.constinit]]：它们决定变量和函数的存储期、链接、ODR 行为和能否在常量求值中使用。
4. [[dcl.type.decltype]]、[[dcl.spec.auto]]、[[dcl.type.class.deduct]]：三种类型推导机制。
5. [[dcl.decl]] 和 [[dcl.init]]。
