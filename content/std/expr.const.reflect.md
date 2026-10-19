---
title: 反射与常量求值
summary: C++26 的常量求值可以产生声明（std::meta::define_aggregate）；这些注入声明放在哪里、谁能看到、只能在哪种 consteval 块里产生，以及反射查询按什么上下文给出结果。
status: done
since: c++26
papers: P2996R13, P3289
related: expr.const.core, expr.const.defns, module.reach, lex.phases, dcl.pre, basic.def.odr, topics/compile-time-programming
tags: 常量求值, 反射, C++26
updated: 2026-10-19
---

!!! tldr
    - {{c++26}} `std::meta::define_aggregate` 在常量求值中补全一个不完整类的定义。这样产生的声明叫注入声明，目前它是唯一的来源。
    - 只有 `consteval { … }` 块的求值能产生注入声明，其他常量表达式里调用 `define_aggregate` 都不是常量表达式。consteval 块还必须和被定义的类处在同一层，不能隔着函数或类的边界。
    - 注入声明的位置是翻译单元末尾之后的一个合成点。普通代码要等 consteval 块求值完成后才能看到它，反射查询则按求值上下文决定能否看到。
    - 嵌套的显然常量求值（例如 constexpr 局部变量的初始化器）看不到外层求值刚产生的注入声明，所以 constexpr 变量的值不依赖它在哪次调用里求值。
    - 不同翻译单元注入同一个类的定义时，比较的是特征序列（成员描述），而不是记号序列。

## 常量求值开始修改程序

```cpp
#include <meta>

struct Point;                       // 不完整类
consteval {
  std::meta::define_aggregate(^^Point, {
    std::meta::data_member_spec(^^int, {.name = "x"}),
    std::meta::data_member_spec(^^int, {.name = "y"}),
  });
}
Point p{1, 2};                      // OK：Point 已经有了定义
```

C++23 及之前，常量求值只是计算：它读取程序，算出一个值，不改变程序本身。C++26 的静态反射（[[P2996R13]]）改变了这一点。`^^Point` 得到类 `Point` 的反射值，`define_aggregate` 在常量求值中给它补上一个定义。`consteval { … }` 是 C++26 新增的 consteval 块声明（[[P3289]]），它的内容在翻译期执行一次。

常量求值一旦有了这种副作用，就会出现几个以前没有的问题：

- 产生的定义位于程序的什么位置，哪些代码能看到它？
- 两个翻译单元各自产生同一个类的定义时，怎样判断它们一致？
- 编译器可能试算常量表达式、缓存结果，或在模板实例化的任意时刻求值。如果这些求值能修改程序，程序的含义就会依赖编译器的内部策略。

标准用三个机制回答这些问题：合成点和特征序列（¶1），只允许 consteval 块产生声明并限制它的位置（¶3），以及求值点和求值上下文（¶5）。

!!! impl "实现状态"
    截至写作时，本机 Clang 23 不支持反射（没有 `<meta>` 头文件，不识别 `^^`）。Compiler Explorer 上有实验性实现（例如 Bloomberg 维护的 Clang 分支）。这些例子都依据草案原文分析，没有经过本地编译。

## 注入声明（¶1）

¶1 一个表达式的求值可以引入一个或多个**注入声明**（[[g:injected-declaration|injected declaration]]），称这次求值**产生**（produce）了这些声明。注 1 指出，调用 `std::meta::define_aggregate` 会产生一个注入声明（[[meta.reflection.define.aggregate]]）。每个注入声明有：

- ¶1.1 一个**合成点**（synthesized point），位于所在翻译单元最后一个非合成的程序点之后；
- ¶1.2 一个**特征序列**（characteristic sequence），由一串值组成。

### 合成点：声明放在翻译单元末尾之后

注入声明不出现在源代码里，所以需要一个虚拟的位置。标准把它放在整个翻译单元之后。按普通的可达性规则，一个声明要出现在点 P 之前才能从 P 到达（[[module.reach#3.1]]），所以源代码里任何一处都看不到放在末尾之后的声明。

另外两条规则让它在需要的地方变得可见：

- [[lex.phases]] 第 7 阶段规定，分析程序点 P 处的代码时，只要某个 consteval 块从 P 可达（通常就是它写在 P 之前），这个块的副作用就视为已经完成。上例中的 `Point p{1, 2};` 因此能用完整的 `Point`。
- [[module.reach#3.2]] 规定注入声明从它自己的合成点可达，而 ¶5 把合成点放进反射查询的求值上下文。这样，同一次求值里稍后的反射查询能看到刚注入的定义。

在产生它的那个 consteval 块内部，普通代码仍然看不到这个定义。[[module.reach]] 的例子演示了这一点：

```cpp
class Incomplete;
consteval {
  int n = nonstatic_data_members_of(
      define_aggregate(^^Incomplete, {data_member_spec(^^int, {.name="x"})}),
      std::meta::access_context::current()
    ).size();      // n == 1：反射查询能看到成员 x
  Incomplete y;    // error: 这里 Incomplete 仍是不完整类型
}
```

为什么不把定义插到 consteval 块所在的位置？因为在模板实例化中产生的注入声明，在源代码里没有确定的位置。合成点加上求值上下文，给出了一个与实例化时机无关的语义。

### 特征序列与跨翻译单元的一致性

注 3 和 [[basic.def.odr#15]] 规定：如果一个类在某个翻译单元里由注入声明定义，另一个翻译单元里的定义也必须是注入声明，而且特征序列相同。只有类属于具名模块、且前一个定义在后一个定义处可达时才要求诊断，其余情况违反了也不要求诊断。

普通的 ODR 要求各个翻译单元中的定义逐个记号相同。注入声明没有记号，所以改为比较特征序列。对 `define_aggregate` 来说，特征序列就是传入的那串成员描述（[[meta.reflection.define.aggregate]]）。

## consteval 块的限制（¶3–¶4）

### 只有 consteval 块能产生声明

[[expr.const.core#2.32]] 规定：会产生注入声明的表达式不是核心常量表达式，除非它就是某个 consteval 块对应的那个表达式。在 constexpr 变量的初始化器、模板实参或 `static_assert` 里调用 `define_aggregate`，表达式都不再是常量表达式。

consteval 块是一个声明，它在程序中的位置决定了求值时机，而且只求值一次。一般的常量表达式可能被试算、缓存，或在 SFINAE 中被丢弃。只让 consteval 块产生副作用，程序的含义就不会依赖编译器怎样安排这些求值。

consteval 块对应的表达式是 `[] static consteval -> void { 块的内容 }()`（[[dcl.pre#15]]），这一点在下面判断作用域时会用到。

### 块必须和被定义的类在同一层（¶3）

¶3 设 consteval 块 C 的求值产生了定义实体 E 的注入声明。下面任一情况成立，程序就非良构：

- ¶3.1 C 被与 E 关联的作用域包围，也就是在类 S 自己的定义里定义 S；
- ¶3.2 取一个直接作用域就是 E 所属作用域的点 P，存在某个函数形参作用域或类作用域，恰好包围 C 和 P 中的一个。

¶3.2 的意思是，consteval 块和被定义的类之间不能隔着函数或类的边界。否则就会出现在函数 f 的某次调用里定义一个命名空间作用域的类这种含义不清的情况。

### 标准例子（¶4）

```cpp
struct S0 {
  consteval {
    std::meta::define_aggregate(^^S0, {});  // error: ¶3.1，S0 的作用域包围了这个块
  }
};

struct S1;
consteval { std::meta::define_aggregate(^^S1, {}); }   // OK：都在命名空间作用域

template <std::meta::info R> consteval void tfn1() {
  std::meta::define_aggregate(R, {});
}
struct S2;
consteval { tfn1<^^S2>(); }   // OK：看的是 consteval 块的位置，
                              //     不是 define_aggregate 写在哪个函数里

template <std::meta::info R> consteval void tfn2() {
  consteval { std::meta::define_aggregate(R, {}); }
}
struct S3;
consteval { tfn2<^^S3>(); }   // error: 产生声明的是 tfn2<^^S3> 里的块，
                              //        tfn2 的形参作用域包围它，却不包围 S3

template <typename> struct TCls {
  struct S4;
  static void sfn() requires ([] {
    consteval { std::meta::define_aggregate(^^S4, {}); }
    return true;
  }()) { }
};
consteval { TCls<void>::sfn(); }   // error: requires 子句里那个 lambda 的形参作用域
                                   //        包围了块，却不包围 TCls<void>::S4

struct S5;
struct Cls {
  consteval { std::meta::define_aggregate(^^S5, {}); }  // error: Cls 的类作用域包围块，不包围 S5
};

struct S6;
consteval {                                 // #1
  struct S7;                                // 局部类
  std::meta::define_aggregate(^^S7, {});    // error: 见下文

  struct S8;                                // 局部类
  consteval {                               // #2
    std::meta::define_aggregate(^^S6, {});  // error: #1 包围 #2，但不包围 S6
    std::meta::define_aggregate(^^S8, {});  // OK：#1 同时包围 #2 和 S8
  }
}
```

`S7` 的情形要回到 consteval 块的改写。块 #1 的内容是一个 lambda 的函数体，`S7` 声明在这个 lambda 的形参作用域之内；块 #1 本身作为声明，位于命名空间作用域。这个形参作用域包围 `S7` 而不包围 #1，违反了 ¶3.2。嵌套的块 #2 和 `S8` 都在 #1 的形参作用域里，处于同一层，所以合法。

## 求值点与求值上下文（¶5）

`std::meta::is_complete_type`、`members_of` 这类反射查询的结果，取决于查询时程序里已经有哪些声明。¶5 规定了查询所处的时间和位置。

### 求值点

¶5 在把表达式、转换或初始化 E 当作核心常量表达式的一次求值 V 中，E 在 V 中的**求值点**（point of evaluation）P 这样确定：

- ¶5.1 如果 E 位于默认成员初始化器中，并且这个初始化器是作为某次（可能是聚合）初始化的一部分被求值的，P 就是那次初始化的求值点；
- ¶5.2 否则，如果 E 位于默认实参中，并且这个默认实参是作为某次函数调用的一部分被求值的，P 就是那次调用的求值点；
- ¶5.3 否则，P 就是 E 出现的位置。

默认成员初始化器和默认实参写在一处，但每次都在使用它们的地方求值，所以借用使用处的位置。这与 [[expr.const.imm]] 中默认实参让调用者升级是同一个思路。

### 求值上下文

在 V 中，某个求值 X 的**求值上下文**（evaluation context）是一组程序点 C：

- ¶5.4 如果 X 发生在 V 内部某个显然常量求值表达式的求值 Y 之中，C 就是 X 在 Y 中的求值上下文。也就是说，嵌套的常量求值重新计算上下文；
- ¶5.5 否则，C 包含：
    - ¶5.5.1 E 在 V 中的求值点，以及它的实例化上下文中的每个合成点；
    - ¶5.5.2 V 中按顺序先于 X 的求值所产生的每个注入声明的合成点。

注 5 指出，求值上下文决定了某些反射函数的行为（[[meta.reflection]]）。

### 标准例子

```cpp
struct S;
consteval std::size_t f(int p) {
  constexpr std::size_t r = /* Q */
    std::meta::is_complete_type(^^S) ? 1 : 2;   // #1
  if (!std::meta::is_complete_type(^^S)) {      // #2
    std::meta::define_aggregate(^^S, {});
  }
  return (p > 0) ? f(p - 1) : r;
}

consteval {
  if (f(1) != 2) {
    throw;                                      // OK：不会被求值
  }
}
```

逐步看 consteval 块里 `f(1) != 2` 的求值 V：

1. 进入 `f(1)`。`r` 是 constexpr 变量，它的初始化器是显然常量求值的，构成嵌套的求值 Y。按 ¶5.4，#1 处查询的上下文只有 Q 和实例化上下文中的合成点，看不到 V 里产生的注入声明。`S` 不完整，`r` 为 2。
2. #2 处的查询不在嵌套求值中。按 ¶5.5，它能看到 V 中此前产生的注入声明，但目前还没有。`S` 不完整，于是调用 `define_aggregate`，产生注入声明。
3. 递归调用 `f(0)`。`r` 的初始化器又是一次嵌套求值，上下文仍然只有 Q，`r` 仍为 2。
4. `f(0)` 的 #2 处，按 ¶5.5.2，上下文包含刚才产生的注入声明的合成点。`S` 已经完整，不再定义。
5. `f(0)` 返回 2，`f(1) != 2` 为假，`throw;` 不被求值。

这个设计保证 constexpr 变量的值不依赖它在哪次调用中求值。如果 #1 能看到注入声明，`f(1)` 和 `f(0)` 里的 `r` 就会不同，而编译器完全可能把 constexpr 变量当作对所有调用都相同的值。

!!! note "为什么要把副作用管得这么严"
    借助友元注入等技巧，C++ 早就能写出有状态的元编程，结果依赖模板实例化的顺序，这被视为语言的缺陷（[[CWG2118]]）。反射正式提供了修改程序的能力，标准必须让它是确定的：只有 consteval 块能产生声明，而且只求值一次；块必须和被定义的类在同一层；注入的定义只通过求值上下文可见，嵌套求值看不到外层的副作用；跨翻译单元靠特征序列保持一致。

<details class="fine" markdown="1"><summary>其余条文</summary>

¶2 注入声明所定义的实体，其成员不得使用保留给实现的名字（[[lex.name]]，如 `__x`、`_X`），违反时不要求诊断。成员名可以由任意常量求值的字符串运算拼出来，要求编译器诊断的代价过高。这条规定防止借反射制造出与标准库内部实现冲突的名字，例如 `data_member_spec(^^int, {.name = "__value"})`。

</details>

## 历史与演进

!!! history
    C++23 及之前，常量求值不能产生声明。C++26 的 [[P2996R13]] 引入静态反射（`^^`、`std::meta::info`、`define_aggregate` 等），[[P3289]] 引入 consteval 块。[expr.const.reflect] 整节，以及 [[expr.const.core#2.32]] 和 [[expr.const.const#1]] 中的 consteval-only 值，都来自这两份提案。

## 思考题

!!! question "思考题 1"
    下面的代码为什么非良构？

    ```cpp
    struct T;
    constexpr bool done = (std::meta::define_aggregate(^^T, {}), true);
    ```

<details markdown="1">
<summary>答案</summary>

`define_aggregate` 的求值会产生注入声明，而 `done` 的初始化器不是 consteval 块对应的表达式，命中 [[expr.const.core#2.32]]，不是核心常量表达式。`done` 是 constexpr 变量，初始化器必须是常量表达式，所以程序非良构。应该写成 `consteval { std::meta::define_aggregate(^^T, {}); }`。
</details>

!!! question "思考题 2"
    在 ¶5 的标准例子里，如果把 `constexpr std::size_t r` 改成 `std::size_t r`，结果会怎样？

<details markdown="1">
<summary>答案</summary>

非 constexpr 局部变量的初始化器不是显然常量求值的，#1 不再是嵌套求值，按 ¶5.5 能看到 V 中此前产生的注入声明。`f(1)` 中 #1 处 `S` 不完整，`r` 为 2，然后定义 `S`；`f(0)` 中 #1 处 `S` 已经完整，`r` 为 1。`f(1)` 返回 `f(0)` 的结果 1，`f(1) != 2` 为真，`throw;` 被求值。此时没有正在处理的异常，命中 [[expr.const.core#2.25]]，consteval 块对应的表达式不是常量表达式，违反 [[dcl.pre#15]]，程序非良构。
</details>
