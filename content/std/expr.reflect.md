---
title: 反射运算符
summary: C++26 的 ^^ 把类型、变量、函数、命名空间、模板等程序构造变成 std::meta::info 值；本页讲它怎样解析、每种操作数得到什么、哪些操作数非良构，以及反射值为什么只能留在编译期。
status: draft
since: c++26
papers: P2996R13, P3381R0
related: basic.fundamental, expr.prim.splice, basic.splice, expr.const.const, expr.const.imm, expr.const.reflect, meta.reflection, stmt.expand, expr.context
tags: 反射, C++26, 元编程, std::meta::info
updated: 2026-10-19
---

!!! tldr
    - `^^x` 产生一个 `std::meta::info` 类型的值，代表程序构造 `x`；`[: r :]` 把它拼回代码。两者之间用 `<meta>` 里的 `consteval` 函数查询。
    - 非空的反射值只能存在于编译期：可以放进 `constexpr` 变量、作模板实参、在 `consteval` 函数里使用，不能进入运行期。
    - `^^` 后面按最长匹配解析，`^^int && x` 会把 `&&` 当成类型的一部分；表示模板的 `^^X` 后面不能直接跟 `<`。
    - 类型别名的反射是别名本身，不是它指向的类型；模板形参 `^^T` 则是实例化时的实际类型。
    - 不能反射：经 using 声明找到的名字、隔着 lambda 的外层局部变量、`__func__`、常量模板形参。

## 反射与拼接

{{c++26}} 静态反射（[[P2996R13]]）由一对互逆的操作构成：`^^` 把程序构造变成值，拼接（splice）`[: r :]` 把值变回代码（[[expr.prim.splice]]、[[basic.splice]]）。中间由 `<meta>` 提供的 `consteval` 函数，如 `members_of`、`type_of`、`identifier_of`，对反射值做查询和变换（[[meta.reflection]]）。

```cpp title="enum-to-string.cpp"
#include <meta>
#include <string_view>

template<typename E>
    requires std::is_enum_v<E>
constexpr std::string_view to_string(E value) {
    template for (constexpr auto e : std::define_static_array(std::meta::enumerators_of(^^E))) {
        if (value == [:e:])
            return std::meta::identifier_of(e);
    }
    return "<unnamed>";
}

enum class Color { red, green, blue };
static_assert(to_string(Color::green) == "green");
```

`^^E` 得到枚举类型的反射；`enumerators_of` 列出它的枚举项；`template for`（[[stmt.expand]]）对每个枚举项展开一份循环体；`[:e:]` 把枚举项的反射拼回成 `Color::red` 这样的表达式；`identifier_of` 取出名字。这类代码过去只能靠宏或外部代码生成器。

`enumerators_of` 返回的 `std::vector` 只能存在于常量求值中，所以要用 `std::define_static_array` 换成静态存储期的数组，才能作为展开语句的范围。`to_string` 本身仍是普通的 `constexpr` 函数模板，可以在运行期调用。

!!! warning "本页例子未经编译验证"
    本机的 Clang 23 还没有实现静态反射：没有 `<meta>` 头文件，也不认识 `^^`。本页代码都按当前草案的文字分析，因此不标判定。Compiler Explorer 上有实现了 P2996 的实验性 Clang 分支可以试验，但它的行为可能与当前草案的措辞有出入。

本页只讲 `^^`：它的操作数可以是什么，结果代表什么。

## 文法

```text
reflect-expression:
    ^^ ::
    ^^ reflection-name
    ^^ type-id
    ^^ id-expression

reflection-name:
    nested-name-specifier-opt identifier
    nested-name-specifier template identifier
```

四种形式依次对应：全局命名空间；按名字查找得到的构造，如命名空间、模板、概念、类型别名；类型；表达式中的实体，如变量、函数、枚举项、数据成员。

`^^` 是一个单独的记号（[[lex.operators]]）。P2996 早期用的是单个 `^`，但 Clang 的 blocks 扩展已经用 `^` 写块字面量（`^{ ... }`），在 Objective-C++ 里会产生歧义，[[P3381R0]] 比较了多种候选后改成了 `^^`。

## 结果：只能留在编译期的值（¶1）

¶1 一元 `^^` 称为**反射运算符**（[[g:reflection-operator]]），结果是 `std::meta::info` 类型的纯右值。这个类型的值称为**反射**（reflection，[[basic.fundamental#17]]）。值初始化的 `std::meta::info{}` 是唯一的**空反射**（null reflection），不代表任何构造。

`^^` 本身可以出现在任何地方，但非空反射是 **consteval-only 值**（[[expr.const.const#1]]）。含有这种值的对象叫**立即对象**（immediate object），[[expr.const.const#3]] 要求每个立即对象都是下列之一：

- `constexpr` 变量的对象或其子对象；
- 模板形参对象，也就是作模板实参时生成的对象；
- 生命周期完全落在一次常量求值之内的对象。

odr-use 了这种变量的表达式，还必须处在立即函数语境中，比如 `consteval` 函数体内。所以反射值不会进入运行期：

```cpp title="reflect-consteval-only.cpp"
#include <meta>

template<std::meta::info R> struct C {};

constexpr std::meta::info r = ^^int;   // OK：constexpr 变量
auto c = C<^^char>();                   // OK：模板实参
auto d = ^^int;                         // error: 立即对象不属于 constexpr 变量

consteval bool is_int(std::meta::info x) { return x == ^^int; }   // OK：立即函数语境
static_assert(is_int(r));

std::meta::info null_r{};               // 空反射不是 consteval-only 值
```

按当前草案的措辞，最后一行的空反射不受这些限制，可以放在普通变量里。

模板代码里通常不必处处写 `consteval`。`constexpr` 函数模板的某个特化如果用到了只能在立即函数语境中做的事，它会自动升级为立即函数（[[expr.const.imm]]）。

注 1 说明，实现可以用反射表示标准没有描述的构造，比如编译器扩展。反过来，[[basic.fundamental#18]] 建议不要把 using 声明、偏特化、属性、语句、表达式这些标准中有描述、但不在反射清单里的构造表示为反射。

## 解析：最长匹配（¶2–¶3）

¶3 *reflect-expression* 按能在语法上构成它的最长记号序列来解析。所以 `^^` 后面的类型会尽量吞下 `&`、`&&`、`*`、`()` 这些声明符运算符。标准的例 1：

```cpp title="reflect-parse.cpp"
static_assert(std::meta::is_type(^^int()));   // OK：^^ 作用于函数类型 int()

template<bool> struct X {};
consteval bool operator<(std::meta::info, X<false>) { return false; }

consteval void g(std::meta::info r, X<false> xv) {
    r == ^^int && true;     // error: ^^ 作用于 int&&，之后的 true 接不上
    r == ^^int & true;      // error: ^^ 作用于 int&
    r == (^^int) && true;   // OK
    r == ^^int &&&& true;   // error: int &&&& 不是合法的 type-id
    ^^X < xv;               // error: 表示模板的 ^^X 后跟 <
    (^^X) < xv;             // OK
    ^^X<true> < xv;         // OK：^^X<true> 是特化（类型），不是模板
}
```

`int &&&&` 一行说明最长匹配不回退：解析器取到 `int &&&&` 发现不是合法类型就报错，不会退回去试 `int&&` 加 `&& true`。

¶3 第二句规定，不加括号、表示模板的 *reflect-expression* 后面不能跟 `<`。`^^X <` 后面是模板实参列表还是小于号，读者和解析器都难以分辨，标准直接要求加括号，而不是另立一条消歧规则。

¶2 *reflection-name* 的组成名是它的 *nested-name-specifier* 和 *identifier* 中的名字（[[basic.lookup.qual]]）。写成 `nested-name-specifier template identifier` 时，最后那个名字必须指代模板。这是在依赖语境中反射成员模板的写法：`^^T::template tmpl`。

## `^^::`（¶4）

¶4 `^^::` 表示全局命名空间。全局命名空间没有名字，这是不经名字查找取得它的唯一写法。

```cpp title="reflect-global.cpp"
#include <meta>
static_assert(std::meta::is_namespace(^^::));
static_assert(std::meta::parent_of(^^std) == ^^::);
```

## 按名字反射（¶5）

¶5 只要能匹配 `^^reflection-name`，就按这种形式解释：对 *identifier* 做名字查找，然后按第一条适用的规则确定结果。

| 列表项 | 查找找到 | 结果 |
|---|---|---|
| ¶5.1 | 替换了某个 using 声明符的声明 | 非良构 |
| ¶5.2 | 命名空间别名 | 该别名；找到的声明须在同一目标作用域 |
| ¶5.3 | 命名空间 | 该命名空间 |
| ¶5.4 | 概念 | 该概念 |
| ¶5.5 | 模板 | 见下文 |
| ¶5.6 | 类型别名 | 模板形参得到实际实体，否则得到别名本身 |
| ¶5.7 | 类或枚举 | 该类型 |
| ¶5.8 | 匿名联合体的成员 | 该成员 |
| ¶5.9 | 其他 | 当作 *id-expression* 处理，见 ¶7 |

`int` 是关键字，不是 *identifier*，所以 `^^int` 只能是 `^^type-id`。而 `^^Y`（`Y` 是 typedef 名）能匹配 `^^reflection-name`，就走 ¶5.6 得到类型别名，不会走 ¶6 得到类型。

### 类型别名与模板形参（¶5.6）

```cpp title="reflect-alias.cpp"
#include <meta>

template<typename T>
struct S {
    static constexpr std::meta::info r = ^^T;   // 模板形参：实际类型
    using type = T;
};
static_assert(S<int>::r == ^^int);
static_assert(^^S<int>::type != ^^int);                        // 成员别名不等于 int
static_assert(std::meta::dealias(^^S<int>::type) == ^^int);   // dealias 去掉别名

typedef struct X {} Y;
typedef struct Z {} Z;
constexpr std::meta::info e = ^^Y;   // 类型别名 Y
constexpr std::meta::info f = ^^Z;   // 类型别名 Z，不是类 Z
```

¶5.6.1 如果找到的是模板形参 `T`，结果是 `T` 的底层实体，即实例化时代入的类型，所以在 `S<int>` 里 `^^T == ^^int`。¶5.6.2 其他类型别名的反射是别名本身，需要底层类型时调用 `std::meta::dealias`。

这样区分是因为反射常用来生成诊断和序列化代码：`identifier_of(^^Y)` 应该是 `"Y"` 而不是 `"X"`。模板形参的名字则不是用户想看到的，`^^T` 理应代表实际类型。

¶5.6.2 还要求找到的声明都在同一个目标作用域。标准的例 3：

```cpp title="reflect-alias-ambig.cpp"
#include <meta>
namespace A { using T = int; }
namespace B { using T = int; }
using namespace A;
using namespace B;
auto r = ^^T;   // error: 找到两个不同作用域中的类型别名
```

普通代码里 `T x;` 是合法的，因为两个声明指代同一类型就不算歧义（[[basic.lookup]]）。但这是两个不同的别名，`^^T` 不知道该代表哪一个。

### 模板（¶5.5）

```cpp title="reflect-template.cpp"
#include <meta>
#include <vector>

template<class T> struct Box {
    static constexpr auto self = ^^Box;                   // 注入类名：特化 Box<T>
    static constexpr auto tmpl = ^^Box::template Box;     // 加 template：类模板 Box
};
static_assert(Box<int>::self == ^^Box<int>);
static_assert(Box<int>::tmpl == ^^Box);

constexpr auto v = ^^std::vector;                         // 类模板
static_assert(std::meta::is_template(v));

template<class T> void f(T);
constexpr auto rf = ^^f;                                  // 唯一的函数模板
```

- ¶5.5.1 在类模板内部，类名会找到**注入类名**（injected-class-name，[[class.pre]]），即类在自己作用域里的名字。写成 `... template identifier` 时得到类模板；否则得到当前特化，与在类模板内写 `Box` 表示 `Box<T>` 一致。
- ¶5.5.2 找到重载集时，它必须只含同一个函数模板的声明，结果就是这个模板。再加一个非模板重载 `void f(int);`，`^^f` 就非良构。
- ¶5.5.3 类模板、变量模板、别名模板，结果是该模板。

注 2：查找不会找到偏特化或显式特化，所以反射模板名得到的总是主模板。

### 经 using 声明找到的名字（¶5.1）

标准的例 2：

```cpp title="reflect-using-decl.cpp"
#include <meta>
struct A { struct S {}; };
struct B : A { using A::S; };
constexpr std::meta::info r1 = ^^B::S;   // error: A::S 是经 using 声明找到的

struct C : virtual B { struct S {}; };
struct D : virtual B, C {};
D::S s;                                  // OK：按类成员查找规则，D::S 是 C::S
constexpr std::meta::info r2 = ^^D::S;   // OK：C::S 不是经 using 声明找到的
```

using 声明本身不是实体，也不被表示为反射。如果 `^^B::S` 悄悄返回 `A::S` 的反射，`identifier_of`、`parent_of` 给出的会是 `A` 的信息，与代码里写的 `B::S` 对不上。标准选择直接拒绝。

## 反射类型（¶6）

```cpp title="reflect-type-id.cpp"
#include <meta>
#include <vector>

template<class T> using Vec = std::vector<T>;
constexpr auto a = ^^Vec<int>;                      // ¶6.2：类型别名 Vec<int>
static_assert(std::meta::is_type_alias(a));
static_assert(std::meta::dealias(a) == ^^std::vector<int>);

constexpr auto b = ^^const int*;                     // ¶6.3：类型 const int*
constexpr auto c = ^^int[3];                         // 数组类型
constexpr auto d = ^^auto;                           // error: 占位符类型（¶6.1）
```

¶6 对 `^^type-id`：

- ¶6.1 占位符类型，如 `auto`、`decltype(auto)`，非良构。占位符不是类型，这里也没有初始化器可以推导。
- ¶6.2 别名模板的特化，如 `Vec<int>`，结果是这个特化所命名的类型别名。
- ¶6.3 其他情况，结果是该类型。

## 反射变量、函数和成员（¶7）

```cpp title="reflect-id-expression.cpp"
#include <meta>

struct P { int x; int y; static int count; };
enum class Color { red, green };
int global = 0;

constexpr auto r1 = ^^global;          // 变量
constexpr auto r2 = ^^P::x;            // 非静态数据成员，不需要对象
constexpr auto r3 = ^^P::count;        // 静态数据成员，未定义也可以
constexpr auto r4 = ^^Color::red;      // 枚举项
static_assert(std::meta::identifier_of(r2) == "x");
static_assert(std::meta::type_of(r2) == ^^int);
```

¶7.3 *id-expression* 指代变量、结构化绑定、枚举项或非静态数据成员时，结果代表该实体。

¶7 最后一句规定，`^^` 后的 *id-expression* 是**未求值操作数**（[[expr.context]]）。所以 `^^x` 不是对 `x` 的 odr-use：只声明未定义的变量可以反射，lambda 里也不会因此触发捕获。反射关心的是实体本身，不是它的值。

### 重载集（¶7.2）

¶7.2 *id-expression* 指代重载集时，把 `&id-expression` 当作未求值操作数必须良构，也就是重载决议（[[over.over]]）能在没有目标类型的情况下唯一选出一个函数，结果代表这个函数。实际上这要求重载集里只有一个函数，或者写成能唯一确定特化的 *template-id*。标准的例 4：

```cpp title="reflect-overload.cpp"
#include <meta>
template<typename T> void fn() requires (^^T != ^^int);
template<typename T> void fn() requires (^^T == ^^int);
template<typename T> void fn() requires (sizeof(T) == sizeof(int));

constexpr std::meta::info a = ^^fn<char>;   // OK：只有第一个模板的约束满足
constexpr std::meta::info b = ^^fn<int>;    // error: 后两个模板的约束都满足，有歧义
```

选中的函数可以是被删除的。反射常用来检查函数是否被删除（`std::meta::is_deleted`），拿不到反射就无从检查。

### 不能反射的情形（¶7.1、¶7.4）

¶7.1 *id-expression* 指代下列实体时非良构：

- ¶7.1.1 由 init-capture 声明的变量，如 `[y = 1] { ^^y; }`；
- ¶7.1.2 函数局部的预定义变量 `__func__`（[[dcl.fct.def.general]]）；
- ¶7.1.3 *requires-expression* 引入的形参；
- ¶7.1.4 外层的局部实体（[[basic.pre#9]]：自动存储期变量、对应的结构化绑定、`*this` 等），而它与 `^^` 之间隔着一个 lambda 作用域。

```cpp title="reflect-local-error.cpp"
#include <meta>
void f() {
    int x = 0;
    constexpr auto ok = ^^x;          // OK：同一函数里的局部变量
    [] {
        constexpr auto r = ^^x;       // error: 隔着 lambda 作用域（¶7.1.4）
    };
    [&x] {
        constexpr auto r = ^^x;       // error: 捕获了也一样
    };
    [y = 1] {
        constexpr auto r = ^^y;       // error: init-capture（¶7.1.1）
    };
    constexpr auto g = ^^__func__;    // error: 函数局部预定义变量（¶7.1.2）
}
```

在 lambda 里写 `^^x`，它该代表外层的变量 `x`，还是闭包里因捕获而产生的成员？代表外层变量，那么拼接回来就能绕过捕获规则；代表捕获成员，没有捕获时这个实体又不存在。标准选择禁止，捕获与否都一样。需要时在 lambda 外写 `constexpr auto r = ^^x;`，`r` 是 `constexpr` 变量，在 lambda 里读它不需要捕获。

¶7.4 其他情况都非良构。注 3 指出，这包括常量模板形参 `^^N` 和包索引表达式 `^^ts...[0]`。常量模板形参在实例化中只是一个值，不是变量，要得到值的反射，用 `std::meta::reflect_constant(N)`（[[meta.reflection]]）：

```cpp title="reflect-constant-param.cpp"
#include <meta>
template<int N>
consteval std::meta::info bad() { return ^^N; }   // error: 常量模板形参
template<int N>
consteval std::meta::info good() { return std::meta::reflect_constant(N); }   // OK
```

!!! impl "实现视角"
    - `std::meta::info` 通常实现为指向编译器内部 AST 节点（声明、类型等）的不透明句柄，加一个表示种类的标签。
    - 反射值不进入运行期，所以不需要运行期的对象表示。但它能作模板实参（`C<^^int>`），名字修饰（mangling）必须能区分 `C<^^int>` 和 `C<^^char>`，ABI 规范要为此新增修饰形式。
    - `^^x` 本身几乎没有代价，名字查找在解析时已经完成，只是把结果包装成值。代价在后续的查询（如 `members_of` 要求类完整）和拼接上。

!!! history "从 Reflection TS 到 C++26"
    Reflection TS 用 `reflexpr(T)` 产生一个元对象类型，查询靠类型特征完成，基于模板的元编程写起来繁琐、编译也慢，这条路线没有进入标准。P2996 改为让反射产生值，查询是普通的 `consteval` 函数，可以用循环、`std::vector` 和算法。这依赖 C++20 以来常量求值能力的增强：`constexpr` 动态分配、`consteval`、立即函数升级。C++26 通过 [[P2996R13]] 加入静态反射，展开语句、注解等是配套的提案。

## 常见误解

!!! pitfall "`^^int && x` 是两个操作数的逻辑与"
    最长匹配会把 `&&` 当成类型的一部分。比较反射时加上括号：`(^^int) == r && cond`。

!!! pitfall "别名的反射等于它指向的类型"
    `^^std::string != ^^std::basic_string<char>`，前者是类型别名 `std::string` 的反射。判断是否同一类型，先 `std::meta::dealias`。

## 思考题

!!! question "思考题 1"
    设 `using I = int;`。`^^I == ^^int` 吗？`std::meta::dealias(^^I) == ^^int` 呢？在 `template<class T> struct W { static constexpr auto r = ^^T; };` 中，`W<I>::r == ^^int` 吗？

<details markdown="1">
<summary>答案</summary>

`^^I` 代表类型别名 `I`（¶5.6.2），不等于 `^^int`。`dealias(^^I)` 去掉别名，等于 `^^int`。

`W<I>::r` 中 `^^T` 找到的是模板形参，按 ¶5.6.1 代表实际类型。模板实参 `I` 代入时就是类型 `int`，`W<I>` 就是 `W<int>`，所以 `W<I>::r == ^^int` 成立。
</details>

!!! question "思考题 2"
    `constexpr auto a = ^^int();` 和 `constexpr auto b = ^^int{};` 分别是什么？

<details markdown="1">
<summary>答案</summary>

`int()` 能构成 *type-id*，即返回 `int`、没有形参的函数类型，按 ¶3 最长匹配，`a` 是这个函数类型的反射，标准例 1 的第一行就是它。

`int{}` 不是 *type-id*，能构成 *reflect-expression* 的最长序列是 `^^int`，剩下的 `{}` 接不上，非良构。`^^` 不能作用于任意表达式，要反射值 0，写 `std::meta::reflect_constant(0)`。
</details>

## 小结

| 操作数 | 段落 | 结果或限制 |
|---|---|---|
| `^^::` | ¶4 | 全局命名空间 |
| 命名空间、命名空间别名、概念 | ¶5.2–¶5.4 | 对应实体，别名就是别名 |
| 模板名 | ¶5.5 | 主模板；注入类名默认是当前特化，加 `template` 是模板 |
| 类型别名 | ¶5.6 | 别名本身；模板形参得到实际类型 |
| *type-id* | ¶6 | 类型；别名模板特化得到类型别名；占位符非良构 |
| 变量、结构化绑定、枚举项、非静态数据成员 | ¶7.3 | 该实体，不构成 odr-use |
| 重载集 | ¶7.2 | `&f` 须能唯一选出函数，可以是被删除的 |
| 非良构 | ¶5.1、¶7.1、¶7.4 | 经 using 声明找到的名字；init-capture、`__func__`、requires 形参、隔着 lambda 的局部实体；常量模板形参、包索引 |
| 解析 | ¶3 | 最长匹配，不回退；表示模板时不得后跟 `<` |
| 结果 | ¶1 | `std::meta::info` 纯右值；非空反射只能留在编译期 |
