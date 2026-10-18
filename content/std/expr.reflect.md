---
title: 反射运算符
summary: C++26 的 ^^ 运算符把命名空间、类型、类型别名、模板、概念、变量、函数、枚举项、数据成员等构造变成 std::meta::info 值；本节规定它的解析（最长匹配、不得后接 <）、各操作数形式代表什么、哪些操作数非良构，以及反射值只能存在于编译期
status: draft
since: c++26
papers: P2996R13, P3381R0
related: basic.fundamental, expr.prim.splice, basic.splice, expr.const.const, expr.const.imm, expr.const.reflect, meta.reflection, stmt.expand, expr.context
tags: 反射, C++26, 元编程, std::meta::info
updated: 2026-10-17
---

{{c++26}} 静态反射（[[P2996R13]]）由一对互逆的操作构成：

- **反射**：`^^x` 把一个程序构造（类型、变量、函数、命名空间……）"提升"为一个**值**，类型是 `std::meta::info`；
- **拼接**（splice）：`[: r :]` 把一个 `std::meta::info` 值"降回"代码，见 [[expr.prim.splice]]、[[basic.splice]]。

在两者之间，`<meta>` 头文件提供的 `consteval` 函数（`members_of`、`type_of`、`identifier_of`……，[[meta.reflection]]）对反射值做查询和变换。本节 [expr.reflect] 只管第一步：**`^^` 的操作数可以是什么，结果代表什么**。

!!! warning "例子未经本地验证"
    截至写作时，本机的 Homebrew Clang 23 尚未实现静态反射（`<meta>` 头文件不存在，`^^` 不被识别）。本页的所有代码例子都**没有**在本地编译验证，判定完全依据当前草案的文字。若要试验，可以使用实现了 P2996 的实验性编译器（例如 Bloomberg 维护的 clang-p2996 分支，在 Compiler Explorer 上可以选到），但其行为可能与当前草案的措辞有出入。

预备知识：`std::meta::info` 是一种基础类型，它的值称为**反射**（reflection，[[basic.fundamental#17]]）；反射值是**consteval-only 值**（[[expr.const.const#1]]），只能存在于常量求值中；*id-expression* 的含义见 [[expr.prim.id]]；名字查找见 [[basic.lookup]]。

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

四种形式分别对应：全局命名空间、"按名字查找得到的东西"（命名空间、模板、概念、类型别名……）、类型、表达式中的实体（变量、函数、枚举项、数据成员……）。

!!! note "为什么是 `^^` 而不是 `^`"
    P2996 早期版本使用单个 `^`。但 `^` 在 Clang 的 Objective-C/C 扩展"blocks"中已经被用于块字面量（`^{ ... }`、`^int (int x) { ... }`），在 Objective-C++ 中会产生真正的歧义。[[P3381R0]] 比较了多种候选记号，最终选定 `^^`（因此 `^^` 是一个新的单独记号，[[lex.operators]]）。

## 结果类型（¶1）

¶1 一元 `^^` 称为**反射运算符**（[[g:reflection-operator]]），结果是 `std::meta::info` 类型的 **prvalue**。

注 1：标准**不限制**实现用反射表示标准中未描述的构造（例如编译器扩展），也不限制把这些构造的名字用作 `^^` 的操作数。（与之相对，[[basic.fundamental#18]] 建议实现**不要**把 *using-declarator*、偏特化、属性、语句、表达式等标准中有描述但不在 ¶17 清单里的构造表示为反射。）

### 反射值只能活在编译期

`^^` 本身不要求出现在常量表达式中，但它产生的是一个**consteval-only 值**（非空反射，[[expr.const.const#1]]）。持有这种值的对象是**立即对象**（immediate object），而 [[expr.const.const#3]] 要求每个立即对象都必须是：

- `constexpr` 变量关联的对象（或其子对象）；
- 模板形参对象；或者
- 生命周期完全落在一次核心常量表达式求值之内的对象。

此外，*odr-use* 持有立即对象的变量的表达式必须处在**立即函数语境**中。效果就是：反射值可以存进 `constexpr` 变量、作为模板实参、在 `consteval` 函数里随意使用，但**永远不会进入运行期**：

```cpp title="reflect-consteval-only.cpp"
#include <meta>

template<std::meta::info R> struct C {};

constexpr std::meta::info r = ^^int;   // OK：constexpr 变量
auto c = C<^^char>();                   // OK：模板实参（模板形参对象）
// auto d = ^^int;                      // error: 立即对象未与 constexpr 变量关联

consteval bool is_int(std::meta::info x) { return x == ^^int; }   // OK：立即函数语境
static_assert(is_int(r));

std::meta::info null_r{};               // OK：空反射不是 consteval-only 值，可以存在于运行期
```

最后一行展示了一个细节：只有**非空**反射才是 consteval-only 值。值初始化的 `std::meta::info{}` 是唯一的**空反射**（null reflection），它不代表任何构造，可以出现在普通变量里。

借助"立即函数升级"机制（[[expr.const.imm]]，作为对 C++20 的缺陷报告引入）：`constexpr` 函数模板的特化中，若出现了只能在立即函数语境中进行的反射用法（例如把 `^^T` 存进一个非 `constexpr` 的局部变量），该特化会被**升级为立即函数**，于是"在模板代码里写反射"通常不需要处处标 `consteval`。

## 解析：最长匹配（¶2–¶3）

¶2 *reflection-name* 的**组成名**（component names，[[basic.lookup.qual]]）是其 *nested-name-specifier*（若有）和 *identifier* 中的名字。形如 `nested-name-specifier template identifier` 的 *reflection-name*，其**终结名**必须指代一个模板——这是依赖语境中反射一个成员模板的写法：`^^T::template tmpl`。

¶3 *reflect-expression* 被解析为**能在语法上构成 *reflect-expression* 的最长记号序列**。另外，一个**不加括号**、表示**模板**的 *reflect-expression* 不能后跟 `<`。

最长匹配的后果是：`^^` 后面的类型会尽可能"吞掉"声明符运算符 `&`、`&&`、`*`、`()`：

```cpp title="reflect-parse.cpp" error
#include <meta>

static_assert(std::meta::is_type(^^int()));   // OK：^^ 作用于 type-id int()（函数类型）

template<bool> struct X {};
consteval bool operator<(std::meta::info, X<false>) { return false; }

consteval void g(std::meta::info r, X<false> xv) {
    r == ^^int && true;     // error: ^^ 作用于 type-id int&&，然后 "true" 无法衔接
    r == ^^int & true;      // error: ^^ 作用于 type-id int&
    r == (^^int) && true;   // OK
    r == ^^int &&&& true;   // error: int &&&& 不是合法的 type-id（最长匹配不回退）
    ^^X < xv;               // error: 表示模板的 reflect-expression 后跟 <
    (^^X) < xv;             // OK
    ^^X<true> < xv;         // OK：^^X<true> 表示特化（类型），不是模板
}
```

为什么禁止 `^^X < xv`？因为读者（和解析器）几乎不可能分辨 `^^X <` 后面是模板实参列表还是小于号。与其引入一条复杂的消歧规则，不如直接要求加括号。

`^^int &&&& true` 一行说明最长匹配是**贪心且不回退**的：解析器先尝试取最长的 type-id，`int &&&&` 不是合法类型，就是错误，而不会退回去尝试 `int&&` + `&& true`。

## `^^::`：全局命名空间（¶4）

¶4 `^^::` 表示**全局命名空间**。这是唯一一种不经过名字查找就能得到命名空间反射的写法——全局命名空间没有名字。

```cpp title="reflect-global.cpp"
#include <meta>
static_assert(std::meta::is_namespace(^^::));
static_assert(std::meta::parent_of(^^std) == ^^::);
```

## `^^reflection-name`：按名字查找（¶5）

¶5 若 *reflect-expression* 匹配 `^^reflection-name` 的形式，就按这种形式解释：对 *identifier* 做名字查找，然后按**第一条适用的规则**确定结果：

| 列表项 | 查找找到 | 结果 |
|---|---|---|
| ¶5.1 | 在单次搜索中替换了某个 *using-declarator* 的声明 | **非良构** |
| ¶5.2 | 命名空间别名 | 该命名空间**别名**（所有找到的声明须有相同的目标作用域） |
| ¶5.3 | 命名空间 | 该命名空间 |
| ¶5.4 | 概念 | 该概念 |
| ¶5.5 | 模板 | 见下 |
| ¶5.6 | 类型别名 | 若是模板形参：其底层实体；否则该类型**别名**（须同一目标作用域） |
| ¶5.7 | 类或枚举 | 该类型 |
| ¶5.8 | 匿名联合体的成员 | 该类成员 |
| ¶5.9 | 其他 | 把 *reflection-name* 当作 *id-expression* `I`，结果为 `^^I`（转到 ¶7） |

### 通过 using-declarator 找到的名字（¶5.1）

```cpp title="reflect-using-decl.cpp" error
#include <meta>
struct A { struct S {}; };
struct B : A { using A::S; };
constexpr std::meta::info r1 = ^^B::S;   // error: A::S 是通过 using-declarator 找到的

struct C : virtual B { struct S {}; };
struct D : virtual B, C {};
D::S s;                                  // OK：按类成员查找规则，D::S 是 C::S
constexpr std::meta::info r2 = ^^D::S;   // OK：结果 C::S 不是通过 using-declarator 找到的
```

为什么非良构？*using-declarator* 本身不是实体，[[basic.fundamental#18]] 也建议不把它表示为反射。如果 `^^B::S` 悄悄地返回 `A::S` 的反射，那么 `identifier_of`、`parent_of` 等查询给出的会是 `A` 的信息，与用户写的 `B::S` 不一致；而为 *using-declarator* 发明一种新的反射又超出了 C++26 的范围。于是选择最保守的做法：直接拒绝，将来可以放宽。

### 模板（¶5.5）

- ¶5.5.1 找到**注入类名**（injected-class-name，[[class.pre]]）：
    - 写成 `nested-name-specifier template identifier` 的，结果是注入类名所指的**类模板**；
    - 否则，注入类名作为 *type-name* 必须无歧义，结果是它所指的**类模板特化**（与在类模板内部写 `X` 表示当前特化一致）。
- ¶5.5.2 找到重载集：该重载集必须**只包含唯一一个函数模板** `F` 的声明，结果是 `F`。
- ¶5.5.3 找到类模板、变量模板或别名模板：结果是该模板。

注 2：查找永远不会找到偏特化或显式特化——反射一个模板名得到的总是主模板。

```cpp title="reflect-template.cpp"
#include <meta>
#include <vector>

template<class T> struct Box {
    static constexpr auto self = ^^Box;                   // 注入类名 → 特化 Box<T>
    static constexpr auto tmpl = ^^Box::template Box;     // 注入类名 + template → 类模板 Box
};
static_assert(Box<int>::self == ^^Box<int>);
static_assert(Box<int>::tmpl == ^^Box);

constexpr auto v = ^^std::vector;                         // 类模板
static_assert(std::meta::is_template(v));

template<class T> void f(T);
constexpr auto rf = ^^f;                                  // 唯一的函数模板 → OK
```

如果再加一个非模板重载 `void f(int);`，`^^f` 找到的重载集里就不止一个函数模板，¶5.5.2 不满足；它也不再是"找到模板"的情形……按 ¶5.9 转为 `^^f` 作为 *id-expression*，然后 ¶7.2 要求 `&f` 能唯一确定一个函数——没有目标类型时做不到，非良构。

### 类型别名与模板形参（¶5.6）

¶5.6 区分两种"类型别名"：

- ¶5.6.1 找到的声明是**模板形参** `T`：结果是 `T` 的**底层实体**——即实例化时被替换进去的那个类型。所以在 `S<int>` 里 `^^T == ^^int`。
- ¶5.6.2 否则结果是**类型别名本身**（而不是它所指的类型），并且所有找到的声明须有**相同的目标作用域**。

```cpp title="reflect-alias.cpp"
#include <meta>

template<typename T>
struct S {
    static constexpr std::meta::info r = ^^T;   // 模板形参 → 底层实体
    using type = T;
};
static_assert(S<int>::r == ^^int);
static_assert(^^S<int>::type != ^^int);                         // 成员类型别名 ≠ int
static_assert(std::meta::dealias(^^S<int>::type) == ^^int);    // dealias 剥掉别名

typedef struct X {} Y;
typedef struct Z {} Z;
constexpr std::meta::info e = ^^Y;   // OK：类型别名 Y
constexpr std::meta::info f = ^^Z;   // OK：类型别名 Z（查找找到 typedef，而非类）
```

为什么类型别名要被区别对待？因为反射的一大用途是生成诊断和序列化代码，`identifier_of(^^Y)` 应该是 `"Y"` 而不是 `"X"`。需要底层类型时显式调用 `std::meta::dealias`。而模板形参则相反：模板形参不是用户想看到的"名字"，`^^T` 理应代表实例化时的实际实体。

例 3 展示"相同目标作用域"的要求：

```cpp title="reflect-alias-ambig.cpp" error
#include <meta>
namespace A { using T = int; }
namespace B { using T = int; }
using namespace A;
using namespace B;
auto r = ^^T;   // error: 查找找到两个目标作用域不同的类型别名
```

即便两个别名都指向 `int`，它们是**不同的**别名实体，`^^T` 不知道该代表哪一个。（普通代码中 `T x;` 却是合法的——[[basic.lookup]] 允许找到的多个声明指代同一类型。这是反射对查找结果要求更严格的地方。）

## `^^type-id`（¶6）

¶6 形如 `^^type-id` 时：

- ¶6.1 若 *type-id* 是**占位符类型**（`auto`、`decltype(auto)`、类模板名作为 CTAD 占位符），**非良构**——占位符不是类型，没有可推导的初始化器；
- ¶6.2 若 *type-id* 形如 `nested-name-specifier-opt template-opt simple-template-id`，且终结名是一个**别名模板**，结果是这个别名模板特化所命名的**类型别名**；
- ¶6.3 否则结果是 *type-id* 所表示的**类型**。

```cpp title="reflect-type-id.cpp"
#include <meta>
#include <vector>

template<class T> using Vec = std::vector<T>;
constexpr auto a = ^^Vec<int>;                      // ¶6.2：类型别名 Vec<int>
static_assert(std::meta::is_type_alias(a));
static_assert(std::meta::dealias(a) == ^^std::vector<int>);

constexpr auto b = ^^const int*;                     // ¶6.3：类型 const int*
constexpr auto c = ^^int[3];                         // 数组类型
// constexpr auto d = ^^auto;                        // error: 占位符类型（¶6.1）
```

¶5 与 ¶6 的分工：`^^int` 中 `int` 是关键字而不是 *identifier*，不可能匹配 `^^reflection-name`，只能是 `^^type-id`；而 `^^Y`（`Y` 是 typedef 名）能匹配 `^^reflection-name`，按 ¶5 的规定"若匹配该形式，就按该形式解释"，所以走 ¶5.6 得到类型别名，而不会走 ¶6.3 得到类型。

## `^^id-expression`（¶7）

¶7 形如 `^^id-expression` 时：

**¶7.1 非良构的情形。** 若 *id-expression* 指代：

- ¶7.1.1 由 *init-capture* 声明的变量（`[x = 1] { ^^x; }`）；
- ¶7.1.2 函数局部的预定义变量（`__func__`，[[dcl.fct.def.general]]）；
- ¶7.1.3 *requires-expression* 引入的局部形参；
- ¶7.1.4 一个**局部实体** `E`（[[basic.pre#9]]：自动存储期变量、对应的结构化绑定、结果绑定、`*this`），而在 `E` 被引入之处与该 *reflect-expression* 之间**隔着一个 lambda 作用域**。

这些都是"名字指代的东西不清楚是哪一个实体"的情形。以 ¶7.1.4 为例：在 lambda 里写 `^^x`（`x` 是外层的局部变量），它应该代表外层的变量 `x`，还是闭包中捕获产生的那个成员？若代表外层变量，那么它在 lambda 中是不可 odr-use 的（未捕获时），反射之后再拼接回来就会绕过捕获规则；若代表捕获成员，那么在没有捕获的情况下根本不存在这个实体。规则选择直接禁止。*init-capture* 和 *requires-expression* 形参也类似：它们不是普通意义上的变量声明，难以给出一致的反射语义。

```cpp title="reflect-local-error.cpp" error
#include <meta>
void f() {
    int x = 0;
    constexpr auto ok = ^^x;          // OK：同一作用域中的局部变量
    [] {
        constexpr auto r = ^^x;       // error: 隔着 lambda 作用域的局部实体（¶7.1.4）
    };
    [y = 1] {
        constexpr auto r = ^^y;       // error: init-capture（¶7.1.1）
    };
    constexpr auto g = ^^__func__;    // error: 函数局部预定义变量（¶7.1.2）
}
```

**¶7.2 重载集。** 若 *id-expression* 指代一个重载集 `S`，那么把 `&id-expression` 作为**未求值操作数**时必须良构（[[over.over]] 能唯一选出一个函数），只是允许被选中的函数 `F` 是**被删除的**；结果代表 `F`。

实际含义：没有目标类型时，`&f` 只有在重载集中只有一个函数，或者 *id-expression* 是一个能唯一确定特化的 *template-id* 时才良构。例 4：

```cpp title="reflect-overload.cpp" error
#include <meta>
template<typename T> void fn() requires (^^T != ^^int);
template<typename T> void fn() requires (^^T == ^^int);
template<typename T> void fn() requires (sizeof(T) == sizeof(int));

constexpr std::meta::info a = ^^fn<char>;   // OK：只有第一个模板的约束满足
constexpr std::meta::info b = ^^fn<int>;    // error: 第二、三个模板的约束都满足，歧义
```

允许被删除的函数，是因为反射常用于"检查一个函数是否被删除"（`std::meta::is_deleted`）——如果连反射都拿不到，这个查询就无从谈起。

**¶7.3** 若指代**变量、结构化绑定、枚举项或非静态数据成员**，结果代表该实体。

**¶7.4** 否则**非良构**。注 3：这包括命名**常量模板形参**的 *unqualified-id*（`^^N`，`N` 是 `template<int N>` 的形参）和**包索引表达式**（`^^ts...[0]`）。

为什么 `^^N` 非良构？常量模板形参在实例化中只是一个**值**，不是变量（不是对象，没有地址）——它不在 ¶7.3 的清单中。要得到一个值的反射，使用 `std::meta::reflect_constant(N)`（[[basic.fundamental#17]] 注 13）。

最后一句：`^^id-expression` 中的 *id-expression* 是**未求值操作数**（[[expr.context]]）。所以 `^^x` 不构成对 `x` 的 odr-use，`x` 不需要被捕获，也不需要有定义。

```cpp title="reflect-id-expression.cpp"
#include <meta>

struct P { int x; int y; static int count; };
enum class Color { red, green };
int global = 0;

constexpr auto r1 = ^^global;          // 变量
constexpr auto r2 = ^^P::x;            // 非静态数据成员（不需要对象）
constexpr auto r3 = ^^P::count;        // 静态数据成员也是变量；未求值，无需定义
constexpr auto r4 = ^^Color::red;      // 枚举项
static_assert(std::meta::identifier_of(r2) == "x");
static_assert(std::meta::type_of(r2) == ^^int);

template<int N>
consteval std::meta::info bad() { return ^^N; }   // error（实例化时）：常量模板形参
template<int N>
consteval std::meta::info good() { return std::meta::reflect_constant(N); }   // OK
```

（上例中 `bad` 一旦被实例化即非良构；不实例化时，是否诊断取决于模板定义的检查规则。）

## 一个完整的用法示例

把 `^^`、查询函数和拼接组合起来，就可以写出过去只能用宏或外部代码生成器完成的东西。下面是常见的"枚举转字符串"：

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

这里：

- `^^E`：模板形参 → 底层实体（¶5.6.1），即枚举类型 `Color` 的反射；
- `std::meta::enumerators_of` 返回 `std::vector<std::meta::info>`，它只能在常量求值中存在，所以要用 `std::define_static_array` 转成一个静态存储期数组的 `span`，才能作为展开语句的范围；
- `template for`（[[stmt.expand]]）对每个枚举项展开一份循环体；
- `[:e:]`（[[expr.prim.splice]]）把枚举项的反射拼回成表达式 `Color::red` 等；
- `identifier_of(e)` 是一次**立即调用**，`e` 是 `constexpr` 变量，其结果 `string_view` 指向静态存储期的字符串，整个调用是常量表达式，不是"立即常量表达式"（结果不是 consteval-only 值），因此**不会**触发立即函数升级（[[expr.const.imm#2]]）。`to_string` 仍然是普通的 `constexpr` 函数模板，可以在运行期调用。

## 实现视角

!!! impl "反射值在编译器中的表示"
    - `std::meta::info` 在实现中通常是一个指向编译器内部 AST 节点（声明、类型等）的**不透明句柄**，外加一个"种类"标签。它的 `sizeof` 由实现决定（[[basic.fundamental]] 只说它是标量类型、可以作为模板实参）。
    - 由于反射值永远不会进入运行期，编译器不需要为它定义运行期的对象表示。但它可以作为**模板实参**出现在特化里（`C<^^int>`），因此需要定义**名字修饰**（mangling）规则来区分 `C<^^int>` 与 `C<^^char>`。Itanium ABI 为此需要新的修饰形式，这部分属于 ABI 规范的工作。
    - `^^` 的求值本身几乎没有代价：编译器在解析时就已经完成了名字查找，`^^x` 只是把查找结果包装成一个值。代价在于后续的查询（如 `members_of` 需要完成类的实例化）和拼接。

## 历史与演进

!!! history "从 Reflection TS 到 C++26"
    - **Reflection TS**（基于 `reflexpr` 运算符）走的是"反射产生**类型**"的路线：`reflexpr(T)` 是一个元对象类型，查询通过类型特征完成。由于基于模板的元编程编译代价高、写法繁琐，这条路线没有进入标准。
    - **基于值的反射**：P2996 改为"反射产生**值**"（`std::meta::info`），查询是普通的 `consteval` 函数，可以用循环、`std::vector`、算法——这依赖 C++20 起不断增强的常量求值能力（`constexpr` 动态分配、`consteval`、立即函数升级）。
    - 记号：P2996 早期版本使用前缀 `^`，[[P3381R0]] 改为 `^^`。
    - C++26 通过 [[P2996R13]] 加入静态反射；同期还有注解（annotations）、`define_aggregate`、展开语句等配套提案。
    - 当前草案中，"consteval-only **类型**"的说法已被重新表述为"consteval-only **值**"与"立即对象"（[[expr.const.const]]），这使得空反射可以出现在运行期变量中。

## 陷阱

!!! pitfall "`^^int && x` 的解析"
    最长匹配会把 `&&` 当成类型的一部分。比较反射时养成加括号的习惯：`(^^int) == r && cond`。

!!! pitfall "别名不等于类型"
    `^^std::string != ^^std::basic_string<char>`：前者是类型别名 `std::string` 的反射。比较"是不是同一类型"时，先 `std::meta::dealias`，或者比较 `^^std::basic_string<char>` 与 `dealias(r)`。

!!! pitfall "在 lambda 里反射外层局部变量"
    ¶7.1.4 禁止。需要时在 lambda 外面先 `constexpr auto r = ^^x;`，再把 `r` 带进去（`r` 是 `constexpr` 变量，可以在 lambda 中使用而无需捕获）。

!!! pitfall "反射常量模板形参"
    `^^N` 非良构。用 `std::meta::reflect_constant(N)` 得到值的反射。

## 思考题

!!! question "思考题 1"
    设 `using I = int;`。`^^I == ^^int` 吗？`std::meta::dealias(^^I) == ^^int` 呢？在 `template<class T> struct W { static constexpr auto r = ^^T; };` 中，`W<I>::r == ^^int` 吗？

<details markdown="1">
<summary>答案</summary>

`^^I` 代表类型**别名** `I`（¶5.6.2），与类型 `int` 的反射不相等。`dealias(^^I)` 剥掉别名，等于 `^^int`。`W<I>::r`：`^^T` 找到的是模板形参，按 ¶5.6.1 代表其**底层实体**。模板实参 `I` 在实例化时已经被解析为类型 `int`（模板实参是类型，不是别名），所以 `W<I>` 就是 `W<int>`，`W<I>::r == ^^int` 成立。
</details>

!!! question "思考题 2"
    为什么 `^^x` 中的 *id-expression* 被规定为未求值操作数？如果它是潜在求值的，会出现什么问题？

<details markdown="1">
<summary>答案</summary>

潜在求值的 id-expression 会构成 odr-use（[[basic.def.odr]]）：反射一个只声明未定义的变量或函数会要求其定义，在 lambda 中反射会触发隐式捕获，在 `constexpr` 语境中还可能要求读取变量的值。而反射关心的是**实体本身**（名字、类型、声明位置），不是它的值。规定为未求值操作数让 `^^f` 对任何函数（包括只有声明的、被删除的）都可用，也让反射不会意外改变 lambda 的捕获集或模板的实例化需求。
</details>

!!! question "思考题 3"
    `constexpr auto a = ^^int(); constexpr auto b = ^^int{};` 分别是什么？

<details markdown="1">
<summary>答案</summary>

`^^int()`：按 ¶3 最长匹配，`int()` 可以构成 *type-id*（返回 `int`、无形参的函数类型），所以 `a` 是函数类型 `int()` 的反射——标准例 1 正是 `static_assert(std::meta::is_type(^^int()))`。`^^int{}`：`int{}` 不是 *type-id*，最长的能构成 *reflect-expression* 的序列是 `^^int`，剩下的 `{}` 无法衔接，非良构。`^^` 不能作用于任意表达式；要反射值 0，写 `std::meta::reflect_constant(0)`。
</details>

## 小结

| 操作数形式 | 段落 | 结果 / 限制 |
|---|---|---|
| `^^::` | ¶4 | 全局命名空间 |
| 命名空间、命名空间别名、概念 | ¶5.2–¶5.4 | 对应实体；别名就是别名 |
| 模板名 | ¶5.5 | 类/变量/别名模板，或唯一的函数模板；注入类名默认是特化，加 `template` 是模板 |
| 类型别名 | ¶5.6 | 别名本身（模板形参则是底层实体） |
| 类、枚举 | ¶5.7 | 该类型 |
| *type-id* | ¶6 | 类型；别名模板特化 → 类型别名；占位符非良构 |
| 变量、结构化绑定、枚举项、非静态数据成员 | ¶7.3 | 该实体（未求值，不 odr-use） |
| 重载集 | ¶7.2 | `&f` 须能唯一选出函数（可以是被删除的） |
| 非良构 | ¶5.1、¶7.1、¶7.4 | using-declarator 找到的名字；init-capture、`__func__`、requires 形参、隔着 lambda 的局部实体；常量模板形参、包索引 |
| 解析 | ¶3 | 最长匹配、不回退；表示模板时不得后跟 `<` |
| 结果 | ¶1 | `std::meta::info` prvalue；非空反射是 consteval-only 值，不进入运行期 |
