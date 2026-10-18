---
title: 反射与常量求值
summary: C++26 静态反射让常量求值可以产生声明：注入声明、合成点与特征序列、consteval 块的作用域限制，以及决定反射查询结果的求值点与求值上下文
status: done
since: c++26
papers: P2996R13, P3289
related: expr.const.core, expr.const.defns, module.reach, lex.phases, dcl.pre, basic.def.odr, topics/compile-time-programming
tags: 常量求值, 反射, C++26
updated: 2026-10-17
---

{{c++26}} 本节是静态反射（[[P2996R13]]）在常量求值规则中的落脚点。在 C++23 及之前，常量求值是纯计算：它读取程序，算出一个值，但不改变程序本身。C++26 改变了这一点，`std::meta::define_aggregate` 可以在常量求值中**完成一个不完整类的定义**。这带来了一系列此前不存在的问题：

- 产生的声明位于程序的什么位置？哪些代码能看到它？
- 如果两个翻译单元各自产生了同一个类的定义，如何保证 ODR？
- 如果一次常量求值先查询 S 是否完整，再定义 S，然后再查询，结果应该是什么？
- 编译器可能多次试算常量求值（例如 [[expr.const.init#4]] 的 tentative 求值），也可能在模板实例化的任意时刻进行常量求值。如果常量求值有副作用，程序语义就会依赖编译器内部的求值顺序。

本节用三个机制回答这些问题：注入声明及其合成点（¶1–¶2），consteval 块的作用域限制（¶3–¶4，配合 [[expr.const.core#2.32]]），以及求值点与求值上下文（¶5）。

!!! impl "实现状态"
    截至写作时，本站使用的 Clang 23 发行版不支持反射（没有 `<meta>` 头文件，不识别 `^^`）。已有实验性实现（例如 Bloomberg 维护的 Clang 分支），可以在 Compiler Explorer 上试用。本页的例子都依据草案文字分析，未经本地编译验证。

## 注入声明（¶1）

表达式的求值可以引入一个或多个**注入声明**（injected declaration），称这次求值**产生**（produce）了这些声明。注 1：调用库函数模板 `std::meta::define_aggregate` 会产生一个注入声明（[[meta.reflection.define.aggregate]]），这是目前唯一的来源。

每个注入声明都有：

- ¶1.1 一个关联的**合成点**（synthesized point），它位于所在翻译单元的最后一个非合成程序点之后；
- ¶1.2 一个关联的**特征序列**（characteristic sequence），由若干值组成。

### 合成点：声明放在哪里

注入声明不出现在源代码里，需要一个虚拟的位置。标准把它放在整个翻译单元之后。这看起来很奇怪，岂不是谁都看不见它？确实如此：按普通的可达性规则（[[module.reach#3.1]]：声明出现在 P 之前），任何非合成的点都看不到它。可达性另有一条专门规则（[[module.reach#3.2]]）：注入声明从它自己的合成点可达。¶5 又规定常量求值中的求值上下文包含相应的合成点。这样，反射查询能看到注入的定义，而普通的名字查找与可达性在相应时刻之前不受影响。

这种设计避免了把声明插入源代码中间某处带来的问题。如果把注入的定义放在 consteval 块所在的位置，那么块之前已经分析完的代码看到的是不完整类型，块之后看到的是完整类型。这本身没有问题，但对于在模板实例化中产生的注入声明，源代码中的位置根本无法确定。合成点加上求值上下文，给出了一个与实例化时机无关的精确语义。

[[lex.phases]] 进一步规定：consteval 块对应的表达式作为完整表达式，其求值（包括产生注入声明这一副作用）在某些程序点视为已经完成，后续代码因此能看到被定义的类型。

### 特征序列与跨 TU 的 ODR

注 3：如果不同翻译单元中特征序列不同的注入声明定义了同一个实体，程序 ill-formed（[[basic.def.odr]]）。

特征序列大体上就是决定这个声明内容的那些值。对 `define_aggregate` 来说，就是被定义的类的反射以及成员描述（类型、名字、对齐、位宽等）。传统的 ODR 比较的是记号序列，要求两个 TU 中的定义逐记号相同；注入声明没有记号，所以改为比较特征序列。

## 保留名字（¶2）

注入声明所定义的实体，其成员不得具有保留给实现的名字（[[lex.name]]，如 `__x`、`_X`）；不要求诊断。

这条规定防止用户借助反射合成出与标准库内部实现冲突的名字，例如用 `data_member_spec(^^int, {.name = "__value"})` 制造一个双下划线成员。名字可能来自任意常量求值的结果（字符串运算），要求编译器诊断的代价过高，所以规定为 IFNDR。

## consteval 块的作用域限制（¶3–¶4）

按 [[expr.const.core#2.32]]，会产生注入声明的表达式，只有在作为 *consteval-block-declaration*（`consteval { ... }`，[[dcl.pre#15]]，来自 [[P3289]]）对应的表达式求值时，才可以是核心常量表达式。在其他地方调用 `define_aggregate`，例如在 `constexpr` 变量的初始化器、模板实参或 `static_assert` 中，都会使表达式成为非常量。

为什么只允许 consteval 块？因为 consteval 块是声明，它的求值时机由它在程序中的位置决定，而且每个块恰好求值一次。一般的常量表达式则可能被试算、被缓存，或在 SFINAE 中被丢弃，如果允许它们产生副作用，程序语义就会依赖编译器的内部策略。

¶3 进一步限制 consteval 块 C 与被定义实体 E 的相对位置。如果 C 的求值产生了定义 E 的注入声明，那么出现下列任一情况时程序 ill-formed：

- ¶3.1 C 被与 E 关联的作用域包围，即在类 S 自己的定义里定义 S；
- ¶3.2 令 P 为一个直接作用域是 E 所属作用域的点，存在一个函数形参作用域或类作用域恰好包围 C 与 P 中的一个。

¶3.2 的直观含义是：consteval 块与被定义的类必须处在同一层，不能跨越函数或类的边界。否则就会出现在函数 f 的某次调用（或某次实例化）里定义一个命名空间作用域的类这种语义不清的情况。

标准例子（有改编，逐条说明）：

```cpp
#include <meta>

struct S0 {
    consteval {
        std::meta::define_aggregate(^^S0, {});   // error: ¶3.1，S0 的类作用域包围了这个块
    }
};

struct S1;
consteval { std::meta::define_aggregate(^^S1, {}); }   // OK：同在命名空间作用域

template <std::meta::info R> consteval void tfn1() {
    std::meta::define_aggregate(R, {});
}
struct S2;
consteval { tfn1<^^S2>(); }      // OK：consteval 块在命名空间作用域；
                                 //     define_aggregate 是在块的求值过程中被调用的，块的位置才是关键

template <std::meta::info R> consteval void tfn2() {
    consteval { std::meta::define_aggregate(R, {}); }
}
struct S3;
consteval { tfn2<^^S3>(); }      // error: 产生声明的是 tfn2<^^S3> 内部的 consteval 块，
                                 //        tfn2 的函数形参作用域包围了它，却不包围 S3

struct S5;
struct Cls {
    consteval { std::meta::define_aggregate(^^S5, {}); }   // error: Cls 的类作用域包围块而不包围 S5
};

struct S6;
consteval {                                   // #1
    struct S7;                                // 局部类
    std::meta::define_aggregate(^^S7, {});    // error: 块 #1 的（lambda 函数）形参作用域包围 S7 却不包围 #1 自身

    struct S8;
    consteval {                               // #2
        std::meta::define_aggregate(^^S6, {});   // error: #1 包围 #2 但不包围 S6
        std::meta::define_aggregate(^^S8, {});   // OK：#1 同时包围 #2 与 S8
    }
}
```

`S7` 的情形值得细看。consteval 块对应的表达式是 `[] static consteval -> void { ... }()`（[[dcl.pre#15]]），所以块体位于一个 lambda 的函数形参作用域中。`S7` 声明在这个作用域里，而块 #1 本身作为声明位于命名空间作用域。这个形参作用域包围 S7 而不包围 #1，违反了 ¶3.2。嵌套块 #2 则与 S8 处于同一个形参作用域（#1 的），两者在同一层，所以没有问题。

## 求值点与求值上下文（¶5）

反射查询（如 `std::meta::is_complete_type`、`members_of`）的结果取决于在当前的时间和位置程序里有哪些声明。¶5 精确地定义了这个时间和位置。

### 求值点

在把表达式、转换或初始化 E 作为核心常量表达式的一次求值 V 中，E 在 V 中的**求值点**（point of evaluation）P 定义如下：

- ¶5.1 如果 E 是默认成员初始化器 I 的子表达式，且 V 是作为某次（可能是聚合）初始化的直接子表达式对 I 的求值，那么 P 是那次初始化的求值点。也就是说，默认成员初始化器借用使用它的地方的位置；
- ¶5.2 否则，如果 E 是默认实参 A 的子表达式，且 V 是作为函数调用的直接子表达式对 A 的求值，那么 P 是那次调用的求值点，默认实参同理；
- ¶5.3 否则，P 就是 E 出现的位置。

这与 [[expr.const.imm]] 中默认实参属于调用者的思路一致：默认成员初始化器和默认实参的文本写在一处，但语义上每次都在使用处求值。

### 求值上下文

在 E 的求值 V 中，某个求值 X 的**求值上下文**（evaluation context）是一个程序点的集合 C：

- ¶5.4 如果 X 发生在某个显然常量求值表达式的求值 Y 之中，而 Y 发生在 V 中，那么 C 是 X 在 Y 中的求值上下文。换句话说，**嵌套的常量求值重新计算上下文**；
- ¶5.5 否则，C 包含：
    - ¶5.5.1 E 在 V 中的求值点，以及其实例化上下文中的每个合成点；
    - ¶5.5.2 在 V 中执行的、按顺序先于 X 的求值所产生的注入声明对应的合成点。

注 5：求值上下文决定了某些反射函数的行为（[[meta.reflection]]）。

### 标准例子精读

```cpp
struct S;
consteval std::size_t f(int p) {
    constexpr std::size_t r = /* Q */
        std::meta::is_complete_type(^^S) ? 1 : 2;   // #1
    if (!std::meta::is_complete_type(^^S)) {        // #2
        std::meta::define_aggregate(^^S, {});
    }
    return (p > 0) ? f(p - 1) : r;
}

consteval {
    if (f(1) != 2) {
        throw;          // OK：不会被求值
    }
}
```

逐步推演 consteval 块中 `f(1) != 2` 的求值 V：

1. 进入 `f(1)`。`r` 是 constexpr 变量，其初始化器是显然常量求值的，这是一个嵌套的求值 Y。按 ¶5.4，#1 处 `is_complete_type(^^S)` 的求值上下文是它在 Y 中的上下文，只包含 Q（Y 的求值点）和实例化上下文中的合成点，不包含之后才产生的注入声明。S 不完整，所以 `r = 2`。
2. #2 处的 `is_complete_type(^^S)` 不在嵌套的显然常量求值中。按 ¶5.5，它的上下文包含 V 中先于它产生的注入声明，而目前还没有。S 不完整，于是调用 `define_aggregate`，产生注入声明。
3. 递归调用 `f(0)`。`r` 的初始化器又是一次嵌套求值，上下文仍然只有 Q，看不到刚才的注入声明，所以 `r` 仍为 2。
4. 在 `f(0)` 的 #2 处，按 ¶5.5.2，上下文包含 V 中先于它产生的注入声明的合成点。S 现在是完整的，不再调用 `define_aggregate`。
5. `f(0)` 返回 `r == 2`，`f(1) != 2` 为 false，`throw;` 不会被求值。

这个例子的设计意图是：**constexpr 变量的值不应依赖于它在哪次调用中求值**。如果 #1 能看到注入声明，`f(1)` 与 `f(0)` 中的 `r` 就会取不同的值；而 `r` 是 constexpr 变量，编译器可能会缓存它，或者认为它在所有调用中都相同。¶5.4 让嵌套的常量求值看不到外层求值的副作用，从而保证了 constexpr 变量的确定性。

## 设计要点总结

!!! note "为什么反射的副作用要这样设计"
    C++ 社区早就知道可以利用友元注入等技巧实现有状态元编程（stateful metaprogramming）。它的结果依赖于模板实例化的顺序，普遍被视为语言的缺陷。反射正式提供了修改程序的能力，标准必须保证这种能力是确定性的：

    1. 只有 consteval 块能产生注入声明（[[expr.const.core#2.32]]），因此求值时机明确，且只求值一次；
    2. consteval 块必须与被定义实体处在同一层（¶3），不允许跨函数、跨类的远程定义；
    3. 注入声明位于合成点（¶1），只能通过求值上下文（¶5）看到，嵌套的显然常量求值看不到外层的副作用；
    4. 跨 TU 的一致性由特征序列保证（¶1 注 3）。

## 历史与演进

!!! history "从无到有"
    - C++23 及之前：常量求值没有任何产生声明的能力；有状态元编程只能依赖友元注入等标准未明确认可的技巧。
    - C++26：[[P2996R13]] 引入静态反射（`^^`、`std::meta::info`、`define_aggregate` 等）；[[P3289]] 引入 consteval 块。本节（[expr.const.reflect]），以及 [[expr.const.core#2.32]]、[[expr.const.core#1]] 中的 `std::meta::info` 和 [[expr.const.const#1]] 中的 consteval-only 值，都是由这些提案引入的。

## 思考题

!!! question "思考题 1"
    为什么下面的代码是错误的？

    ```cpp
    struct T;
    constexpr bool done = (std::meta::define_aggregate(^^T, {}), true);
    ```

<details markdown="1">
<summary>答案</summary>

`define_aggregate` 的求值会产生注入声明，而 `done` 的初始化器不是 *consteval-block-declaration* 对应的表达式，命中 [[expr.const.core#2.32]]，所以不是核心常量表达式。`done` 是 constexpr 变量，要求 constant-initializable，因此程序 ill-formed。正确的做法是 `consteval { std::meta::define_aggregate(^^T, {}); }`。
</details>

!!! question "思考题 2"
    在本节的标准例子中，如果把 `constexpr std::size_t r = ...` 改为 `std::size_t r = ...`（非 constexpr），`f(1)` 的值会变吗？

<details markdown="1">
<summary>答案</summary>

会。非 constexpr 局部变量的初始化器不是显然常量求值的，#1 不再是嵌套求值，按 ¶5.5，它的上下文包含 V 中先前产生的注入声明。在 `f(1)` 的 #1 处 S 不完整，`r = 2`，然后定义 S；在 `f(0)` 的 #1 处 S 已经完整，`r = 1`。`f(1)` 返回 `f(0)` 的结果 1，于是 `f(1) != 2` 为 true，`throw;` 被求值。此时没有正在处理的异常，命中 [[expr.const.core#2.25]]，consteval 块不是常量表达式，程序 ill-formed。
</details>

## 小结

| 概念 | 含义 | 段落 |
|---|---|---|
| 注入声明 | 常量求值产生的声明（目前来自 `define_aggregate`） | ¶1 |
| 合成点 | 注入声明的虚拟位置：TU 末尾之后，只经由求值上下文可见 | ¶1.1 |
| 特征序列 | 跨 TU 比较注入声明一致性的依据 | ¶1.2 |
| consteval 块限制 | 不得在被定义类内部；不得跨越函数形参/类作用域 | ¶3 |
| 求值点 | 默认成员初始化器/默认实参取使用处 | ¶5.1–5.3 |
| 求值上下文 | 嵌套的显然常量求值重新计算；否则包含先前产生的注入声明 | ¶5.4–5.5 |
