---
title: 可达性
summary: 哪些翻译单元从某点必然可达、哪些可能可达；声明何时可达；可达与可见的区别；一个实体的语义属性（完整性、默认实参等）由所有可达声明累积决定。
status: done
since: c++20
papers: P1103R3
related: module.import, module.context, module.global.frag, module.private.frag, module.interface, basic.lookup, basic.def.odr, expr.const.reflect
tags: 模块, 可达性, 可见性
updated: 2026-10-18
---

模块把传统上混为一谈的两件事拆开了：

- **可见**（visible）：名字查找能否找到一个声明，它决定你能否写出这个名字。可见性由导出和导入控制（[[module.interface]]、[[module.import]]、[[basic.lookup#2]]）。
- **可达**（reachable）：一个声明的语义效果是否在某处生效，它决定类型是否完整、默认实参能否使用、类成员能否被找到。可达性由本节规定。

为什么要拆开？考虑一个模块导出的函数 `export Widget make();`，`Widget` 未导出。导入者写 `auto w = make(); w.draw();` 时，它从未写出 `Widget` 这个名字，但编译器必须知道 `Widget` 的定义（大小、成员、析构函数）。如果可达性等同于可见性，这段代码就无法编译，模块就无法隐藏任何实现类型。反之，如果可见性等同于可达性，导出就失去了意义。

阅读前需要：[[module.import]]（导入、接口依赖）、[[module.context]]（实例化语境）。

## 可达的翻译单元（¶1–¶2）

¶1 如果在 P 之前满足下列条件之一，则 TU U 从程序点 P [[g:necessarily-reachable|必然可达]]（necessarily reachable）：

- U 是一个模块接口单元，且包含 P 的 TU 对 U 有接口依赖（[[module.import#10]]）；或
- 包含 P 的 TU 导入了 U（[[module.import]]）。

Note 1：模块接口单元即使只是经由非导出的导入声明传递地导入，也是可达的；但名字查找不会找到其中的命名空间作用域名字。

对比两种情况：

| U 是…… | 与 P 所在 TU 的关系 | 必然可达？ |
|---|---|---|
| 模块接口单元（主接口或接口分区） | 直接导入 | 是 |
| 模块接口单元 | 间接接口依赖（经由非导出 `import`） | 是（第一种情形） |
| 头文件单元 | 直接导入 | 是 |
| 头文件单元 | 只有间接接口依赖 | 否（不是模块接口单元） |
| 实现分区 | 被同一模块的单元直接导入 | 是 |
| 实现分区 | 只有间接接口依赖（如外部导入者 → 主接口 → 实现分区） | 否 |
| 普通实现单元 | 无法被导入 | 否 |

¶2 所有必然可达的 TU 都是**可达的**。P 所在 TU 有接口依赖的其他 TU 可能也被视为可达，但哪些 TU、在什么情况下可达，是未指明的。（脚注：因此，参与编译的额外 TU 的语义效果如果能被观察到，实现不必加以阻止。）

Note 2：希望可移植的程序最好不要依赖额外 TU 的可达性。

为什么不干脆规定所有有接口依赖的 TU 都可达？因为实现方式差异很大：有的实现（如 BMI 中只记录直接导入）加载间接依赖的头文件单元或实现分区代价高，有的实现则本来就把它们都加载了。标准给出了一个最低保证（必然可达）和一个上限（有接口依赖），中间部分留给实现。

## 可达的声明（¶3–¶4）

¶3 在以下情况下，声明 D 从点 P 可达：

- **¶3.1** P 是非合成点，并且
    - **¶3.1.1** D 在同一 TU 中出现在 P 之前；或
    - **¶3.1.2** D 没有被丢弃（[[module.global.frag#3]]），出现在从 P 可达的 TU 中，并且不在私有模块片段中；或
- **¶3.2** D 是注入声明，而 P 是与之对应的合成点。{{c++26}}

¶3.1.2 的三个条件对应本章其他各节的设计：被丢弃的全局模块片段声明对外不可达；私有模块片段对外不可达；其余的一切，无论是否导出，只要所在 TU 可达就可达。

¶3.2 与 Example 1 来自 C++26 静态反射：`std::meta::define_aggregate` 在常量求值中补全一个不完整类，产生一个**注入声明**（[[expr.const.reflect]]）。它在一个**合成点**上可达，而不是在它在源码文本中出现的位置。

```cpp
class Incomplete;

consteval {
  int n = nonstatic_data_members_of(
      define_aggregate(^^Incomplete, {data_member_spec(^^int, {.name="x"})}),
      std::meta::access_context::current()
    ).size();               // n 为 1：注入的成员 x 在合成点上可达

  Incomplete y;             // error: y 的类型不完整——注入声明从这里（非合成点）不可达
}
/* P */                     // consteval 块之后，Incomplete 完整
```

（本机 Clang 23 尚未实现静态反射，没有 `<meta>` 头文件，此例未经编译验证，注释依据标准例子。）

¶4 如果一个声明从实例化语境（[[module.context]]）中的任何点可达，它就是可达的。

Note 3：**一个声明是否被导出，与它是否可达无关。**

理解本节的关键就在这句 Note。导出只影响名字查找，可达性只看 TU 和位置。

## 语义属性的累积（¶5）

¶5 在某个语境中，一个实体的**所有可达声明的累积属性**决定了该实体在该语境中的行为。

Note 4：这些可达语义属性包括：类型完整性、类型定义、初始化器、函数或模板声明的默认实参、属性、绑定的名字等等。由于默认实参在调用表达式的语境中求值，对应形参类型的可达语义属性在那个语境中适用。

这条规则的意思是：同一个实体可能在多个 TU 中有多个声明（前置声明、定义、带默认实参的重声明等）。在某处使用它时，它表现成什么样子，取决于从这里可达的那些声明合起来提供了什么：

- 可达的声明中有类定义 → 类型完整；
- 可达的声明中有带默认实参的函数声明 → 可以省略实参；
- 可达的声明中有 `[[deprecated]]` → 使用时可能产生警告。

¶5 Example 2（加注）：

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
B b1;                         // error: B 没有可达的定义（只导入了 :A）
```

```cpp title="TU #4：M.cppm" ok
export module M;
export import :A;
import :B;                    // 直接导入实现分区 → 必然可达
B b2;                         // OK
export void f(B b = B());
```

```cpp title="TU #5：user.cpp" error
import M;
B b3;                         // error: B 没有可达的定义
void g() { f(); }             // error: B 没有可达的定义（默认实参 B() 在调用处求值）
```

分析 TU #5：`B` 这个名字可见（经 `export import :A` 导出）。`B` 的定义在实现分区 `M:B` 中。user.cpp 对 `M:B` 有接口依赖（user → M → M:B），但 `M:B` 不是模块接口单元，user.cpp 也没有（也不能）直接导入它，所以它不是必然可达的；按标准例子的设定，`B` 的定义不可达。注意例子把这两行标为 error，前提是实现没有利用 ¶2 的自由把 `M:B` 视为可达。严格地说，这两行是否合法是未指明的，可移植代码应当把它们视为错误。

`f()` 的情况说明了 Note 4 的最后一句：默认实参 `B()` 在调用处的语境中求值，需要 `B` 完整，而在调用处 `B` 不完整。尽管 `f` 的声明（带默认实参）写在 TU #4 中，`B` 在那里是完整的，也无济于事。

!!! impl "本机验证"
    Clang 23 对 TU #3 报 "variable has incomplete type 'B'"；对 TU #5 的 `B b3;` 报 "definition of 'B' must be imported from module 'M' before it is required"，附注 "definition here is not reachable"，可见 Clang 选择了不把间接依赖的实现分区视为可达。但它**没有诊断 `void g() { f(); }`**：默认实参中 `B()` 对完整性的要求没有在调用处重新检查。若写成 `void h(B* p) { f(*p); }`（在调用处显式需要拷贝 `B`），Clang 会报同样的不可达错误。所以对 `f()` 这一行，Clang 的行为与标准例子不一致。

## 可达但不可见（¶6）

¶6 Note 5：一个实体的声明可能在某处可达，即使名字查找在那里找不到它。

Example 3（加注）：

```cpp title="TU #1：A.cppm"
export module A;
struct X {};
export using Y = X;
```

```cpp title="TU #2：user.cpp" error
import A;
Y y;                // OK：X 的定义可达
X x;                // error: X 对非限定查找不可见
```

`Y` 是导出的类型别名，它表示 `X`；`X` 的定义在 A 的接口单元中，从 user.cpp 必然可达。所以 `Y y;` 能创建一个完整的 `X` 对象。但 `X` 这个名字没有导出，user.cpp 写不出它。

!!! impl "本机诊断"
    Clang 23 对 `X x;` 报 "unknown type name 'X'"。如果名字存在于某个已加载的模块中但不可见，Clang 还有一种更友好的诊断，形如 "declaration of 'QS' must be imported from module 'Q' before it is required"（见 [[module.import]] 的例子）。

## 可见、可达、导出、导入：总表

| 你想做的事 | 需要 | 由谁决定 |
|---|---|---|
| 写出命名空间作用域的名字 `N::f` | 声明先于此处：被导入且被导出（或同模块且非内部链接） | [[basic.lookup#2]] |
| 访问类成员 `obj.m`、`T::m` | 类定义可达 | ¶3–¶5、[[module.interface#7]] |
| 定义某类型的对象、`sizeof`、拷贝 | 类型定义可达（完整） | ¶5 |
| 使用默认实参 | 带默认实参的声明可达，且实参中的类型在调用处可达 | ¶5 Note 4 |
| 依赖名的 ADL 找到函数 | 先于实例化语境中的某个点，或由 [[basic.lookup.argdep#4]] 的模块特例找到 | [[module.context]] |
| 调用 inline 函数 | 定义可达（[[basic.def.odr]] 要求 inline 函数的定义在 odr-use 它的定义域末尾可达） | [[basic.def.odr]] |

## 实现视角

!!! impl "可达性与 BMI"
    在实现上，可达大致对应于编译器加载了这个 BMI，并且其中保留了这个声明。Clang 的 BMI 记录了对其他 BMI 的依赖，编译导入者时会按需加载传递依赖的接口单元 BMI，但它判断哪些声明可达时是按标准建模的。上面的诊断 "definition here is not reachable" 表明 Clang 找到了那个定义（它在已加载的 BMI 中），只是判定它不可达。这比简单地让一切已加载的东西都可达更严格，也更有利于写出可移植的代码。

    ¶2 的未指明性为采用不同加载与建模策略的实现留了余地。要写可移植代码，就只依赖必然可达的声明。

## 历史与演进

!!! history "C++20 → C++26"
    - 可达性的概念随 [[P1103R3]] 进入 C++20。Modules TS 早期版本中，可见与可达的界限并不清晰，合并提案明确区分了两者，并规定了必然可达。
    - C++23 前后对名字查找的重写（[[P1787R6]]）用先于（precedes）精确定义了可见性，与本节的可达性配套。
    - C++26 加入合成点与注入声明（¶3.2）以支持静态反射的 `define_aggregate`。

## 陷阱

!!! pitfall "把定义放在实现分区里，却在接口中导出名字"
    如 ¶5 的 `B`，导入者只得到不完整类型（在 Clang 上确定如此，在其他实现上可能不同）。若希望导入者能使用定义，就把它放进接口分区并 `export import`，或者放进主接口本身。

!!! pitfall "以为没导出就是私有"
    未导出的类型，只要定义在接口单元中，就对所有导入者可达。导入者能通过 `auto`、`decltype`、模板实参推导、导出的类型别名使用它的全部功能（包括访问它的公有成员）。要真正隐藏，需要把定义放进实现单元或私有模块片段。

!!! pitfall "默认实参中的类型"
    导出函数的默认实参若构造了一个只在模块内部可达的类型，导入者调用时可能失败（¶5 的 `f()`）。

## 思考题

!!! question "思考题 1"
    模块 M 的主接口单元中：`struct Impl { int x = 1; }; export Impl get();`。导入者能否写 `int v = get().x;`？能否写 `decltype(get()) i; i.x = 2;`？能否写 `Impl i;`？

<details markdown="1">
<summary>答案</summary>

前两者都能：`Impl` 的定义在 M 的接口单元中，导入者导入了 M，所以必然可达；成员 `x` 通过类成员查找找到（只需定义可达），`decltype` 不需要写出名字。`Impl i;` 不能：`Impl` 未导出，名字查找找不到它（不可见）。
</details>

!!! question "思考题 2"
    为什么 ¶3.1.2 要求 D 不在私有模块片段中，而 ¶3.1.1（同一 TU 中出现在 P 之前）没有这个限制？

<details markdown="1">
<summary>答案</summary>

¶3.1.1 处理的是同一 TU 内部：私有片段中的声明对私有片段中后面的代码当然可达，这就是普通的先声明后使用。¶3.1.2 处理的是跨 TU 的情况：私有片段的目的就是不对其他 TU 产生影响（[[module.private.frag#2]]），所以要把它排除。
</details>

## 小结

| 概念 | 定义 | 段落 |
|---|---|---|
| 必然可达的 TU | 有接口依赖的模块接口单元，或直接导入的 TU | ¶1 |
| 可达的 TU | 必然可达的，加上实现可选择的有接口依赖的 TU（未指明） | ¶2 |
| 声明从 P 可达 | 同 TU 中在 P 前；或在可达 TU 中、未被丢弃、不在私有片段中；或注入声明对应的合成点 | ¶3 |
| 声明可达 | 从实例化语境中任一点可达；与导出无关 | ¶4 |
| 语义属性 | 所有可达声明的累积属性：完整性、默认实参、属性…… | ¶5 |
| 可达 ≠ 可见 | 定义可达但名字不可见是常态 | ¶6 |
