---
title: 拼接说明符
summary: C++26 静态反射的"反方向"——[: r :] 把一个 std::meta::info 反射值变回程序中的构造（实体、值、类型、模板、命名空间……）；本节定义它"指称"什么，以及 [: r :]< ... > 中的 < 何时是模板实参列表。
status: done
since: c++26
papers: P2996R13
related: basic.pre, expr.prim.splice, dcl.type.splice, expr.reflect, expr.const, temp.names, basic.def.odr, basic.link
tags: 反射, C++26, splice
updated: 2026-10-17
---

{{c++26}} 静态反射（P2996，"Reflection for C++26"）给 C++ 加上了两个方向相反的运算：

- **反射**（reflect）：`^^x` 把程序中的一个构造——变量、函数、类型、模板、命名空间、值……——变成一个**值**，类型是 `std::meta::info`（[[expr.reflect]]）。这个值可以在常量求值中被传递、存进容器、交给 `std::meta::members_of` 之类的元函数查询。
- **拼接**（splice）：`[: r :]` 把一个常量 `std::meta::info` 值**变回**程序中的构造，让它重新出现在源代码的语法位置上——作为表达式、类型、模板名、命名空间名、嵌套名说明符……

本节 [basic.splice] 只定义拼接的**核心语法单元** *splice-specifier* 与 *splice-specialization-specifier*，以及它们"**指称**"（designate）什么。具体在表达式、类型、作用域限定中怎样使用，分别由 [[expr.prim.splice]]、[[dcl.type.splice]]、[[expr.prim.id.qual]]、[[temp.names]] 等规定。

在 C++23 及之前，没有任何办法把"关于程序的信息"重新变回程序本身——只能靠模板元编程（类型可以作为模板实参"往返"，但函数、成员、命名空间不行）或者宏。拼接是反射真正有用的前提：没有它，反射只能"看"而不能"用"。

!!! warning "编译器支持"
    截至写作时，主流编译器的默认版本（包括本机的 Clang 23）**不支持**静态反射；`<meta>` 头文件不存在。反射有实验性实现（例如基于 Clang 的实验分支、以及 GCC 的实现工作），但本页的例子都按标准草案判定，**未经本机编译器验证**，也不提供一键运行按钮。

## 文法

```text
splice-specifier:
    [: constant-expression :]

splice-specialization-specifier:
    splice-specifier < template-argument-list(opt) >
```

`[:` 和 `:]` 是两个新的记号（[[lex.operators]]）。之所以选这个看起来古怪的括号，是为了在语法上和数组下标 `[ ]`、属性 `[[ ]]`、lambda 引导 `[ ]` 都区分开。

## 拼接说明符指称什么（¶1）

¶1 *splice-specifier* 中的 *constant-expression* 必须是类型为 `std::meta::info` 的**转换后的常量表达式**（converted constant expression，[[expr.const.const]]）。如果这个转换后的表达式**表示**（represents）构造 X，则 *splice-specifier* **指称**（designate）：

- **¶1.1** 若 X 是一个**实体**（[[basic.pre#8]]），则是 X 的**底层实体**；
- **¶1.2** 否则，就是 X 本身。

!!! std
    A *splice-specifier* whose converted *constant-expression* represents a construct X is said to *designate* either the underlying entity of X if X is an entity, or X otherwise.

这一条里有三个值得注意的设计：

**必须是常量表达式**。拼接发生在编译期——编译器要据此决定这段源代码到底是什么（变量？类型？模板？），所以反射值必须在翻译时已知。这就是标准例子里 `bad_splice` 出错的原因：

```cpp
consteval int bad_splice(std::meta::info v) {
  return [:v:];          // error: v 是函数形参，不是常量表达式
}
```

即使 `bad_splice` 是 `consteval` 函数、每次调用都在编译期，它的**形参**在函数体内也不是常量表达式——函数体只被分析一次，不可能针对每个实参分别决定 `[:v:]` 是变量还是枚举项。要做"按参数拼接"，必须把反射值作为**模板实参**传入（`template<std::meta::info R> ... [:R:]`），每个特化各自实例化一次。

**穿透别名：指称底层实体**。`^^Alias`（类型别名）表示的是别名本身——这是一个独立的实体，反射可以分辨 `using I = int;` 中的 `I` 和 `int`（`std::meta::dealias` 才把它还原）。但一旦拼接回去，`[:^^I:]` 指称的是**底层实体** `int`。这与 [[basic.pre#8]] "名字指代底层实体"的规则一致：拼接的行为就像写了一个名字。

**¶1.2 可以指称非实体**。反射值除了表示实体，还可以表示**值**（`std::meta::reflect_constant(42)`）、**对象**、**直接基类关系**、**数据成员描述**、注解等（[[basic.fundamental]]）。拼接这些东西时，它指称的就是那个构造本身：例如 [[expr.prim.splice]] 规定，拼接一个值得到一个计算该值的 prvalue；拼接一个直接基类关系 (D, B) 得到一个指称该基类子对象的左值。

Note 1：如果转换后的常量表达式是**值依赖**的，*splice-specifier* 就是**依赖**的（[[temp.dep.splice]]）——在模板中 `[:R:]`（R 是模板形参）要等到实例化才知道指称什么，它的解释规则与依赖名类似，因此需要 `typename`、`template` 来消歧义。

## 拼接特化说明符（¶2）

¶2 *splice-specialization-specifier* 中，非依赖的 *splice-specifier* 必须指称一个**模板**。

即：`[: r :]<args>` 要求 `r` 反射的是模板（类模板、函数模板、变量模板、别名模板、概念），然后用实参列表形成它的特化——这就是"用反射值当模板名"。

## `<` 什么时候是模板实参列表（¶3）

¶3（注）*splice-specifier* 后面的 `<` 只有在以下情况下才被解释为模板实参列表的开始：

- *splice-specifier* 前面有关键字 `template` 或 `typename`；或
- 它出现在**仅类型上下文**（type-only context，[[temp.names]]）中。

否则 `<` 就是**小于号**。

为什么？这是 C++ 解析中老问题的翻版。`[:r:]` 指称什么，可能要到实例化才知道（依赖时），也可能需要对常量表达式求值才知道——而解析器必须在**解析时**决定 `<` 的含义。标准选择了和依赖名一样的策略：默认把 `<` 当小于号，需要模板实参列表时由程序员用 `template`/`typename` 明说（参见 [[temp.res]] 中 `t.template foo<int>()` 的规则）。在仅类型上下文中（例如 `using` 别名的右侧），只可能是类型，没有歧义，因此可以省略。

Example 1（加注）：

```cpp
constexpr int v = 1;
template<int V> struct TCls {
  static constexpr int s = V + 1;
};

using alias = [:^^TCls:]<([:^^v:])>;
  // OK：alias-declaration 的右侧是仅类型上下文，< 开始模板实参列表；
  //     模板实参 ([:^^v:]) 是加了括号的 splice-expression

static_assert(alias::s == 2);

auto o1 = [:^^TCls:]<([:^^v:])>();              // error: 这里 < 是小于号
auto o2 = typename [:^^TCls:]<([:^^v:])>();     // OK：typename 明示这是类型，o2 是 TCls<1> 类型的对象

consteval int bad_splice(std::meta::info v) {
  return [:v:];                                 // error: v 不是常量
}
```

两个细节：

- 作为模板实参的 *splice-expression* 必须加括号：`TCls<[:^^v:]>` 是错误的，要写 `TCls<([:^^v:])>`（[[temp.names]]）。原因是 `[:^^v:]` 在模板实参位置上可能被理解为类型或模板，加括号强制它成为表达式。
- `o1` 那一行：`[:^^TCls:]` 在表达式位置，`<` 是小于号，`[:^^TCls:]` 作为表达式指称一个类模板，是非良构的。

## 拼接在各处的用法一览

本节只定义说明符本身，下表汇总它在其他条款中的用法，便于建立整体印象：

| 语法形式 | 指称 | 规定在 | 例子 |
|---|---|---|---|
| *splice-expression* `[: r :]` | 变量、函数、枚举项、值、非静态数据成员、结构化绑定…… | [[expr.prim.splice]] | `int n = [:^^x:];` |
| `template [: r :]` / `template [: r :]<...>` | 函数模板（及其特化） | [[expr.prim.splice]] | `template [:^^f:]<int>(0)` |
| *splice-type-specifier* `typename [: r :]` | 类型、类模板、别名模板 | [[dcl.type.splice]] | `typename [:^^int:] i = 0;` |
| *splice-scope-specifier* `[: r :]::` | 类、命名空间、枚举 | [[expr.prim.id.qual]] | `[:^^S:]::a` |
| `namespace A = [: r :];` | 命名空间 | [[namespace.alias]] | |
| `using namespace [: r :];` | 命名空间 | [[namespace.udir]] | |
| 作为模板实参 | 类型、模板、值 | [[temp.arg.general]] | `std::vector<typename [:t:]>` |

```cpp
struct S { static constexpr int a = 1; using type = int; };

constexpr int c = [:^^S:]::a;          // OK：[:^^S:]:: 是 splice-scope-specifier，不是表达式
typename [:^^S::type:] *p = nullptr;   // OK：声明 int* 类型的变量
// [:^^S::type:] *q;                   // error: 不在仅类型上下文、又没有 typename，
                                       //   [:^^S::type:] 被当作表达式
using T = [:^^S::type:];               // OK：仅类型上下文
```

## 与 ODR 和链接的关系

拼接引入了"不通过名字也能指称实体"的方式，于是全标准中凡是依赖"名字"的规则都要补上拼接：

- [[basic.def.odr#3]]：*splice-expression* 和 *id-expression* 一样构成潜在结果；[[basic.def.odr#5]]：被 *splice-expression* 指称的变量同样被"命名"、可能被 odr-use。标准例子 `int o = [:^^S::x:];` 就是一个只读值、不 odr-use 的拼接。
- [[basic.def.odr#16]]：多个 TU 中的定义里，对应的 *reflect-expression* 必须计算出等价的值（¶16.12）。
- [[basic.link#13]]：声明中出现的 *splice-specifier* 指称某个实体时，这个声明就"命名"了该实体——这影响 TU-local 实体的**暴露**判定（模块接口中不能通过拼接把内部链接的实体泄漏出去）。

## 实现视角

!!! impl "实现上的挑战"
    - 解析器要在看到 `[:` 时就知道接下来是否需要先做常量求值。非依赖的拼接在解析时立即求值；依赖的拼接延迟到实例化，类似依赖名。
    - 拼接与"名字查找"无关：`[:^^x:]` 不会再去查一次 `x`，它直接得到反射值里记录的那个声明/实体。这意味着拼接可以访问一些"按名字找不到"的东西（例如被隐藏的声明）。访问控制也不在拼接这一层检查：[[class.access.base#5]] 明确规定，由 *splice-expression* 指称的成员总是可访问的；能否拿到私有成员的反射，由反射查询 API 的 `access_context` 参数把关。
    - 反射值在 ABI 层面不会出现在运行期（`std::meta::info` 是只能在常量求值中存在的"consteval-only"类型），但它可以作为模板实参出现在特化中，因此需要定义相应的名字修饰（mangling）规则——这部分属于 ABI 规范的工作，标准本身不涉及。

## 历史与演进

!!! history "C++26"
    - 静态反射的主提案是 P2996（"Reflection for C++26"），2025 年被采纳进 C++26 工作草案。早期版本的反射运算符写作 `^`，后来改为 `^^`，以避免与 Objective-C++ 的块语法（block）冲突。
    - 拼接语法 `[: :]` 在 P2996 的多个修订中保持稳定；与之配套的 `typename`/`template` 消歧义规则、模板实参中必须加括号等细节在标准化过程中逐步明确。
    - 在 C++23 及之前，没有拼接；最接近的东西是把类型当作模板实参传递，或者用宏拼接记号。

## 陷阱

!!! pitfall "形参不是常量表达式——即使在 consteval 函数里"
    `consteval void f(std::meta::info r) { [:r:]; }` 是错误的。拼接需要的是**常量表达式**，而 consteval 函数的形参在函数体内不是。正确做法是把反射值放进模板形参：`template<std::meta::info R> consteval void f() { [:R:]; }`，或者用 `template for` 展开语句（[[stmt.expand]]）遍历反射值序列——展开语句的每次"迭代"都会把循环变量变成常量表达式。

!!! pitfall "`<` 默认是小于号"
    `[:r:]<int>` 在表达式里不会被当作模板特化，要写 `template [:r:]<int>` 或 `typename [:r:]<int>`。

## 思考题

!!! question "思考题"
    `using I = int; constexpr auto r = ^^I;` 那么 `r == ^^int` 吗？`typename [:r:]` 是什么类型？

<details markdown="1">
<summary>答案</summary>

`r == ^^int` 为 **false**：`^^I` 表示的是类型别名 `I` 这个实体本身（[[basic.pre#8]] 说类型别名是一种实体，其底层实体是 `int`），与 `^^int` 不是同一个反射值；`std::meta::dealias(r) == ^^int` 才为真。但 `typename [:r:]` 就是 `int`：按 ¶1.1，*splice-specifier* 指称的是实体的**底层实体**。
</details>

## 小结

- `[: r :]` 中 `r` 必须是 `std::meta::info` 类型的常量表达式。
- 若 `r` 表示实体，拼接指称其**底层实体**（穿透别名）；否则指称那个构造本身（值、对象、基类关系……）。
- `[: r :]< ... >` 要求 `r` 指称模板；`<` 只有在前置 `template`/`typename` 或仅类型上下文中才开始模板实参列表。
- 依赖的拼接在实例化时解析，规则类似依赖名。
- 编译器支持尚在实验阶段，本页例子未经本机验证。
