---
title: 可达性
summary: 模块把能否写出名字（可见）和声明的效果是否生效（可达）分开：哪些翻译单元从某处必然可达、哪些可能可达，声明何时可达，以及类型是否完整、默认实参能否使用由所有可达声明合起来决定。
status: done
since: c++20
papers: P1103R3
related: module.import, module.context, module.global.frag, module.private.frag, module.interface, basic.lookup, basic.def.odr, expr.const.reflect
tags: 模块, 可达性, 可见性
updated: 2026-10-19
---

!!! tldr
    - 可见决定名字查找能否找到一个声明，由导出和导入控制；可达决定一个声明的效果（类型完整、默认实参等）是否生效。是否导出与是否可达无关。
    - 直接导入的翻译单元，以及有接口依赖的模块接口单元，必然可达。只通过别的模块间接依赖的头文件单元和实现分区，是否可达是未指明的。
    - 没导出的类型，只要定义在接口单元里，导入者就能通过 `auto`、导出的别名等方式完整地使用它。
    - 一个实体在某处表现成什么样，由该处所有可达声明的属性合起来决定。默认实参在调用处求值，所以它用到的类型也要在调用处完整。

## 可见与可达

```cpp title="TU #1：A.cppm"
export module A;
struct X {};
export using Y = X;
```

```cpp title="TU #2：user.cpp" error
import A;
Y y;                // OK：X 的定义可达
X x;                // error: X 对无限定查找不可见
```

这是标准例 3（¶6）。`X` 没有导出，`user.cpp` 写不出这个名字，Clang 23 报 `unknown type name 'X'`。但导出的别名 `Y` 指的就是 `X`，而 `X` 的定义在 `A` 的接口单元里，从 `user.cpp` 可达，所以 `Y y;` 能定义一个完整的 `X` 对象。

模块把两件事分开了：

- **可见**：名字查找能否找到一个声明，它决定你能否写出这个名字。由导出和导入控制（[[module.interface]]、[[module.import]]、[[basic.lookup#2]]）。
- **可达**：一个声明的效果是否在某处生效，它决定类型是否完整、能否访问成员、默认实参能否使用。由本节规定。

为什么要分开？设想模块导出了 `export Widget make();`，而 `Widget` 没有导出。导入者写 `auto w = make(); w.draw();` 时从未写出 `Widget`，但编译器必须知道它的大小、成员和析构函数。如果可达等同于可见，模块就无法隐藏任何实现类型；反过来，如果可见等同于可达，导出就失去了意义。

¶6 的注 5 正是这个意思：一个实体的声明可能在某处可达，即使名字查找在那里找不到它。

## 哪些翻译单元可达（¶1、¶2）

先回顾几个术语。**模块接口单元**（[[g:module-interface-unit|module interface unit]]）是以 `export module` 开头的单元，包括主接口单元和接口分区；**实现分区**是 `module M:P;` 这样不带 `export` 的分区；**头文件单元**（[[g:header-unit|header unit]]）是 `import "x.h";` 导入的头文件。一个翻译单元导入了 U，或者导入的东西又（传递地）依赖 U，就说它对 U 有**接口依赖**（[[g:interface-dependency|interface dependency]]，[[module.import#10]]）。

¶1 在程序点 P 之前满足下面任一条件时，翻译单元 U 从 P **必然可达**（[[g:necessarily-reachable|necessarily reachable]]）：

- U 是模块接口单元，并且 P 所在的翻译单元对 U 有接口依赖；
- P 所在的翻译单元直接导入了 U。

| U 是什么 | 与 P 所在翻译单元的关系 | 必然可达 |
|---|---|---|
| 模块接口单元 | 直接导入 | 是 |
| 模块接口单元 | 间接接口依赖（例如经由非导出的 `import`） | 是 |
| 头文件单元 | 直接导入 | 是 |
| 头文件单元 | 只有间接接口依赖 | 否 |
| 实现分区 | 被同一模块的单元直接导入 | 是 |
| 实现分区 | 只有间接接口依赖（外部导入者 → 主接口 → 实现分区） | 否 |

注 1 补充：一个模块接口单元即使只是经由非导出的 `import` 传递地导入，也是可达的，只是名字查找找不到它在命名空间作用域里的名字。

¶2 所有必然可达的翻译单元都是**可达的**。P 有接口依赖的其他翻译单元也可能被视为可达，但哪些、在什么情况下，是未指明的。脚注说明，因此实现不必阻止参与编译的额外翻译单元的效果被观察到。注 2 建议可移植的程序不要依赖额外翻译单元的可达性。

标准给出一个下限（必然可达）和一个上限（有接口依赖），中间留给实现，因为实现方式差别很大：有的实现加载间接依赖的头文件单元或实现分区代价很高，有的本来就全部加载了。

## 声明何时可达（¶3、¶4）

¶3 在下列情况下，声明 D 从点 P 可达：

- ¶3.1 P 不是合成点，并且
    - ¶3.1.1 D 在同一个翻译单元里出现在 P 之前；或
    - ¶3.1.2 D 没有被丢弃（[[module.global.frag#3]]），出现在从 P 可达的翻译单元里，并且不在私有模块片段里；
- ¶3.2 D 是注入声明，P 是与它对应的合成点。{{c++26}}

¶3.1.2 的三个条件对应本章其他各节：全局模块片段里被丢弃的声明对外不可达；私有模块片段对外不可达（[[module.private.frag]]）；其余的声明无论是否导出，只要所在翻译单元可达就可达。

¶4 一个声明从实例化语境（[[module.context]]）中任何一点可达，它就是可达的。对普通代码，实例化语境就是当前这一点；对模板实例化，它可能包含模板定义所在模块的某些点。注 3 强调：**一个声明是否被导出，与它是否可达无关**。

### 合成点与注入声明 {{c++26}}

C++26 的静态反射可以在常量求值中用 `std::meta::define_aggregate` 补全一个不完整类，这会产生一个**注入声明**（[[g:injected-declaration|injected declaration]]，[[expr.const.reflect]]）。它不在源码里的某个位置出现，而是在一个与之关联的**合成点**上可达。标准例 1：

```cpp
class Incomplete;

consteval {
  int n = nonstatic_data_members_of(
      define_aggregate(^^Incomplete, {data_member_spec(^^int, {.name="x"})}),
      std::meta::access_context::current()
    ).size();               // n 为 1：成员 x 在合成点 P 上可达

  Incomplete y;             // error: 从这里（非合成点）注入声明不可达，类型不完整
}
/* P */                     // consteval 块之后，Incomplete 是完整的
```

本机 Clang 23 尚未实现静态反射，没有 `<meta>` 头文件，这个例子没有经过编译，注释依据标准原文。

## 语义属性的累积（¶5）

同一个实体可能在多个翻译单元里有多个声明：前置声明、定义、带默认实参的重声明。¶5 规定，在某个语境中，一个实体的所有可达声明的属性合起来，决定它在该语境中的行为。注 4 列举了这些属性：类型是否完整、类型定义、初始化器、函数或模板的默认实参、属性、绑定的名字等。

所以从某处可达的声明里有类定义，类型在那里就完整；有带默认实参的函数声明，那里就可以省略实参；有 `[[deprecated]]`，使用时就可能得到警告。

标准例 2：

```cpp title="TU #1：M-A.cppm"
export module M:A;
export struct B;              // 只有前置声明
```

```cpp title="TU #2：M-B.cppm"
module M:B;                   // 实现分区
struct B {
  operator int();
};
```

```cpp title="TU #3：M-C.cppm" error
module M:C;
import :A;
B b1;                         // error: 没有可达的 B 的定义
```

```cpp title="TU #4：M.cppm" ok
export module M;
export import :A;
import :B;                    // 直接导入实现分区：必然可达
B b2;                         // OK
export void f(B b = B());
```

```cpp title="TU #5：user.cpp" error
import M;
B b3;                         // error: 没有可达的 B 的定义
void g() { f(); }             // error: 同上，默认实参 B() 在调用处求值
```

在 TU #5 里，名字 `B` 可见，因为 `M` 经 `export import :A` 导出了它。`B` 的定义在实现分区 `M:B`。`user.cpp` 对 `M:B` 有接口依赖（user → M → M:B），但 `M:B` 不是模块接口单元，`user.cpp` 也不能直接导入它，所以它不是必然可达的。标准例子把这两行标为 error，前提是实现没有利用 ¶2 的自由把 `M:B` 视为可达；严格说是否合法是未指明的，可移植代码应当把它们当作错误。

`f()` 一行体现了注 4 的最后一句：默认实参在调用表达式的语境里求值，所以形参类型的可达属性也按调用处算。`B()` 需要 `B` 完整，而在调用处 `B` 不完整。`f` 的声明写在 TU #4，那里 `B` 是完整的，但这没有用。

!!! impl "Clang 23 的行为"
    对 TU #3，Clang 报 `variable has incomplete type 'B'`。对 TU #5 的 `B b3;`，报 `definition of 'B' must be imported from module 'M' before it is required`，附注 `definition here is not reachable`，说明 Clang 选择不把间接依赖的实现分区视为可达。

    但 Clang 没有诊断 `void g() { f(); }`，它没有在调用处重新检查默认实参对完整性的要求。写成 `void h(B* p) { f(*p); }`，在调用处显式需要复制 `B`，Clang 就会报同样的不可达错误。在 `f()` 这一行上，Clang 与标准例子不一致。

## 总表

| 想做的事 | 需要什么 | 规则 |
|---|---|---|
| 写出命名空间作用域的名字 `N::f` | 声明可见：被导入并且被导出，或在同一模块里且不是内部链接 | [[basic.lookup#2]] |
| 访问类成员 `obj.m`、`T::m` | 类定义可达 | ¶3–¶5 |
| 定义对象、`sizeof`、复制 | 类型定义可达 | ¶5 |
| 使用默认实参 | 带默认实参的声明可达，实参里用到的类型在调用处可达 | ¶5 注 4 |
| 依赖名的 ADL 找到函数 | 从实例化语境中某一点可见，或符合模块特例 | [[basic.lookup.argdep#4]]、[[module.context]] |
| odr-use 一个 inline 函数 | 定义在使用它的定义域末尾可达 | [[basic.def.odr]] |

!!! impl "可达性与 BMI"
    实现上，可达大致对应于编译器加载了相应的 BMI（预编译的模块接口文件），并且其中保留了这个声明。Clang 编译导入者时会按需加载传递依赖的 BMI，但判断可达时按标准建模：上面的 `definition here is not reachable` 说明 Clang 找到了那个定义，只是判定它不可达。这比让一切已加载的东西都可达更严格，也更利于写出可移植的代码。

## 历史与演进

!!! history
    - 可达性随模块合并提案 [[P1103R3]] 进入 C++20。Modules TS 的早期版本中，可见与可达的界限不清楚，合并提案明确区分了两者，并定义了必然可达。
    - C++23 对名字查找条款的重写（[[P1787R6]]）用先于（precedes）精确定义了可见性，与本节的可达性配套。
    - C++26 为静态反射的 `define_aggregate` 加入了合成点与注入声明（¶3.2）。

## 常见误解

!!! pitfall "没导出就是私有的"
    没导出的类型，只要定义在接口单元里，就对所有导入者可达。导入者能通过 `auto`、`decltype`、模板实参推导、导出的类型别名使用它的全部功能，包括访问它的公有成员。要真正隐藏，需要把定义放进实现单元或私有模块片段。

!!! pitfall "定义放在实现分区里，名字却在接口里导出"
    像 ¶5 的 `B` 那样，导入者只得到不完整类型（在 Clang 上确定如此，在其他实现上可能不同）。希望导入者能使用定义，就把它放进接口分区并 `export import`，或者直接放进主接口。导出函数的默认实参构造了这样的类型时，导入者调用也可能失败。

## 思考题

!!! question "思考题 1"
    模块 `M` 的主接口单元里有 `struct Impl { int x = 1; }; export Impl get();`。导入者能否写 `int v = get().x;`？能否写 `decltype(get()) i; i.x = 2;`？能否写 `Impl i;`？

<details markdown="1">
<summary>答案</summary>

前两者都能。`Impl` 的定义在 `M` 的接口单元里，导入者导入了 `M`，所以它必然可达。成员 `x` 通过类成员查找找到，只需要定义可达；`decltype` 不需要写出名字。

`Impl i;` 不能：`Impl` 没有导出，名字查找找不到它。本机 Clang 23 报 `unknown type name 'Impl'`。
</details>

!!! question "思考题 2"
    ¶3.1.2 要求 D 不在私有模块片段里，¶3.1.1（同一翻译单元中出现在 P 之前）为什么没有这个限制？

<details markdown="1">
<summary>答案</summary>

¶3.1.1 处理同一翻译单元内部：私有模块片段里的声明对片段里后面的代码当然可达，这就是普通的先声明后使用。¶3.1.2 处理跨翻译单元的情况，而私有模块片段的目的就是不影响其他翻译单元（[[module.private.frag#2]]），所以要把它排除。
</details>
