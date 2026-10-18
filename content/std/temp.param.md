---
title: 模板形参
summary: 五种模板形参（类型、常量、类型模板模板、变量模板模板、概念模板形参）；type-constraint 与立即声明约束；常量模板形参允许的类型与结构化类型的完整规则；模板形参对象；默认模板实参的合并与顺序规则；模板形参包。
status: done
papers: P0127R2, P0732R2, P1907R1, P2841
related: temp.pre, temp.arg, temp.arg.nontype, temp.arg.template, temp.type, temp.variadic, temp.constr.decl, dcl.spec.auto, dcl.fct.default
tags: 模板, 常量模板形参, NTTP, 结构化类型, 默认模板实参, 概念模板形参
updated: 2026-10-17
---

模板形参（template parameter）是模板的"输入端口"。[temp.param] 规定：端口有哪几种、各自能声明成什么类型、可以带什么约束、可以有什么默认值、什么时候是一个"包"。与之配对的是 [[temp.arg]]：端口能接受什么样的实参。

这一节在 C++ 历史上变化极大：C++98 只有类型形参、整型/指针/引用等"非类型"形参、类模板模板形参；C++11 加了形参包；C++17 加了 `auto` 形参；C++20 加了类类型与浮点类型的常量形参、*type-constraint*；C++26 又加了**变量模板模板形参**与**概念模板形参**，并把"非类型模板形参"更名为**常量模板形参**。

## 文法（¶1）

¶1 给出五种 *template-parameter* 的文法：

```text
template-parameter:
    type-parameter              // class T, typename T, C T, C<A> T
    parameter-declaration       // int N, auto V, S s, auto& r
    type-tt-parameter           // template<class> class TT
    variable-tt-parameter       // template<class> auto VT          (C++26)
    concept-tt-parameter        // template<class> concept CT       (C++26)
```

几个细节：

- *type-parameter* 可以以 `class`/`typename` 开头，也可以以一个 **type-constraint**（`C` 或 `C<A1, ...>`，可带 *nested-name-specifier*）开头；后者就是 `template<std::integral T>` 的写法。
- *type-tt-parameter* 的默认实参可以写成 `= N::template X` 的形式。
- *variable-tt-parameter* 用 `auto` 作为"种类关键字"：`template<class> auto V`。
- *concept-tt-parameter* 用 `concept`：`template<class> concept C`。它的 *template-head* **不能**带 *requires-clause*（文法里直接写的是 `template < template-parameter-list >`，而不是 *template-head*）。

*type-constraint* 的**组成名字**（component names）是它的 *concept-name* 和 *nested-name-specifier* 中的名字。注 1：模板模板形参的 *template-parameter-list* 之后的 `>` 也可以由 `>>` 拆分得来。

## 五种形参（¶2–¶3）

¶2 定义五种模板形参：

| 种类 | 引入方式 | 例子 | 对应实参 | 引入 |
|---|---|---|---|---|
| **类型模板形参** | *type-parameter* | `class T`、`std::integral T` | 类型 | C++98（约束 C++20） |
| **常量模板形参** | *parameter-declaration* | `int N`、`auto V`、`Point p` | 值 | C++98（旧称非类型模板形参） |
| **类型模板模板形参** | *type-tt-parameter* | `template<class> class TT` | 类模板 / 别名模板 | C++98（别名模板 C++11） |
| **变量模板模板形参** | *variable-tt-parameter* | `template<class> auto VT` | 变量模板 | {{c++26}} |
| **概念模板形参** | *concept-tt-parameter* | `template<class> concept CT` | 概念 | {{c++26}} |

¶3 后三种统称**模板模板形参**（template template parameters）。

!!! note "术语变更：常量模板形参"
    {{c++26}} 草案把 C++23 及之前的 *non-type template parameter*（NTTP，"非类型模板形参"）改称 **constant template parameter**（常量模板形参）。原因很直接：引入变量模板模板形参和概念模板形参之后，"非类型"已经不能刻画"值形参"——模板模板形参也不是类型。本站使用新术语；读旧资料时把 NTTP 对应到"常量模板形参"即可，规则本身没有因改名而变化。

```cpp run title="five-kinds.cpp" ok
#include <concepts>
#include <vector>

template<class T> constexpr bool always = true;
template<class T> concept Small = sizeof(T) <= 4;

template<
    class T,                              // 类型模板形参
    int N,                                // 常量模板形参
    template<class...> class Container,   // 类型模板模板形参
    template<class> auto Trait,           // 变量模板模板形参（C++26）
    template<class> concept Concept       // 概念模板形参（C++26）
>
struct All {
    Container<T> c;
    static constexpr bool ok = Trait<T> && Concept<T> && N > 0;
};

static_assert(All<int, 1, std::vector, always, Small>::ok);
int main() {}
```

!!! impl "实现状态"
    概念模板形参与变量模板模板形参（[[P2841]]）是 C++26 新特性。截至写作时，本机 Clang 23 已经支持上面的例子；旧版本编译器会直接报语法错误。

### 模板模板形参的用途

为什么需要变量模板模板形参和概念模板形参？C++23 之前，"把一个谓词传给模板"只能把它包成类模板（`template<class> class Pred` + `Pred<T>::value`）。变量模板（`std::is_integral_v`）和概念（`std::integral`）都无法直接传递。C++26 之后：

```cpp run title="concept-param.cpp" ok
#include <concepts>

// 一个"高阶概念"：所有 Ts 都满足 C
template<template<class> concept C, class... Ts>
concept all_satisfy = (C<Ts> && ...);

static_assert(all_satisfy<std::integral, int, long, char>);
static_assert(!all_satisfy<std::integral, int, double>);

// 用概念模板形参约束函数形参
template<template<class> concept C>
void take(C auto) {}

int main() { take<std::integral>(42); }
```

## type-constraint 的限制（¶4–¶5）

¶4 *type-constraint* 的 *nested-name-specifier*（若有）**不能是待决的**。原因是 *type-constraint* 必须在模板定义处就能确定它指名哪个概念——约束要参与规范化和包含关系比较（[[temp.constr.normal]]），不能等到实例化才知道是哪个概念。

它与 [[temp.res.general#4]] 配合，消除了一处歧义：在模板形参声明中，`T::X U`（`T` 是外层模板形参）既可能被读作"带限定名的 *type-constraint*"，也可能被读作"类型为 `T::X` 的常量模板形参"。¶4 排除了前者；而 [[temp.res.general#4]] 规定常量模板形参的 *parameter-declaration* 是**仅类型语境**（type-only context），所以 `T::X` 被当作类型，不需要写 `typename`：

```cpp run title="dependent-nns.cpp" ok
namespace N { template<class T> concept C = true; }
template<N::C T> struct X {};          // OK: 非待决的 nested-name-specifier

template<class T>
struct W {
    template<T::C U>                   // 不是 type-constraint，而是类型为 typename T::C 的常量模板形参
    static constexpr auto g() { return U; }
};
struct S { using C = int; };
static_assert(W<S>::g<3>() == 3);
X<int> x;
int main() {}
```

¶5 **概念模板形参不能有关联约束**（[[temp.constr.decl]]）。例如 `template<template<std::integral T> concept C>` 是非良构的：概念本身不能被约束（[[temp.concept#4]]），作为形参的概念也一样。

```cpp title="constrained-concept-param.cpp" error
#include <concepts>
template<template<std::integral T> concept C>   // error: 概念模板形参不能有关联约束（¶5）
struct X {};
```

!!! impl "编译器现状"
    截至写作时，Clang 23 **接受**上面的代码（没有诊断 ¶5）。这是编译器尚未实现的检查，标准规定它是非良构的。

## 形参包（¶6）

¶6 以下 *template-parameter* 声明一个**模板形参包**（template parameter pack，[[temp.variadic]]）：

- 声明了包的 *parameter-declaration*（`int... Ns`、`auto... Vs`）；
- 其他形式中，可选的 *identifier* 之前有省略号（`class... Ts`、`template<class> class... TTs`、`C... Ts`）。

形参包可以**同时是一个包展开**：

- 常量模板形参包的**类型**中含有未展开的包：`template<T... Values>`，其中 `T` 是外层的类型形参包；
- 模板模板形参包的 *template-parameter-list* 中含有未展开的包；
- 带 *type-constraint* 的类型形参包，其 *type-constraint* 含有未展开的包。

限制：作为包展开的形参包，**不能展开同一个** *template-parameter-list* 中声明的包。

```cpp title="pack-expansion-param.cpp" error
template<class... T>
struct value_holder {
    template<T... Values> struct apply {};   // OK: Values 是常量形参包，同时是 T 的包展开
};
value_holder<int, char>::apply<1, 'a'> ok;  // apply 的形参是 int, char

template<class... T, T... Values>            // error: Values 展开了同一列表中的 T
struct static_array;
```

为什么最后一个非法？因为在同一个列表里，`T` 的长度在推导/指定实参时还没确定，而 `Values` 的形参个数又依赖 `T` 的长度——这形成了循环依赖。外层模板的包在内层模板声明时已经确定，所以 `value_holder<int, char>::apply` 没有这个问题。

## class 与 typename；形参名（¶7–¶8）

¶7 *type-parameter-key* 中的 `class` 和 `typename` **没有语义区别**。但 `typename` 之后跟的是什么决定了形参种类：

- `typename` + *unqualified-id* → 类型模板形参；
- `typename` + *qualified-id* → *parameter-declaration* 中的类型（常量模板形参）。

```cpp run title="class-vs-typename.cpp" ok
struct S { using type = int; };

template<class T, typename T::type N>   // T：类型形参；N：类型为 T::type 的常量形参
struct Q { static constexpr auto value = N; };

static_assert(Q<S, 3>::value == 3);
int main() {}
```

`class T` 形式总是 *type-parameter*，即使作用域里有一个叫 `T` 的类。标准例 2：

```cpp run title="class-T.cpp" ok
class T {};
int i;

template<class T, T i> void f(T t) {
    T t1 = i;         // 模板形参 T 和 i
    ::T t2 = ::T();   // 全局的 T
    (void)t; (void)t1; (void)t2;
}

int main() { f<int, 3>(0); }
```

这里 `f` 有一个名叫 `T` 的**类型模板形参**，而不是一个类型为 `class T` 的匿名常量形参。

¶7 末尾两条规范要求：常量模板形参的 *parameter-declaration* **不能有存储类说明符**（`static int N` 非法），模板形参声明中**不能定义类型**（`template<struct X {} x>` 非法）。

¶8 *template-parameter* 中表示类型或模板的 *identifier* **不被查找**——它是在声明一个新名字，而不是使用一个旧名字。没有跟在省略号之后的标识符，在模板声明的作用域中被定义为：

- ¶8.1 *type-parameter* 的 *typedef-name*（所以 `T` 可以像 typedef 一样用，但不能写 `class T` 的详述类型说明符 `struct T`）；
- ¶8.2–¶8.3 模板模板形参的 *template-name*；
- ¶8.4 概念模板形参的 *concept-name*。

## 立即声明约束（¶9–¶10）

¶9 是 *type-constraint* 的语义核心。一个指名概念 `C` 的 *type-constraint* `Q`，可以对一个"由语境决定的类型或类型形参包" `T` 施加如下约束表达式 `E`：

1. 若 `Q` 形如 `C<A1, ..., An>`，令 `E′` 为 `C<T, A1, ..., An>`；否则 `E′` 为 `C<T>`。也就是说，**被约束的类型总是作为概念的第一个实参插进去**。
2. 若 `T` 不是包，`E` 就是 `E′`；若是包，`E` 是折叠表达式 `(E′ && ...)`。

这个 `E` 叫做 `Q` 对 `T` 的**立即声明约束**（[[g:immediately-declared-constraint]]）。*type-constraint* 指名的概念必须是**类型概念**（type concept，[[temp.concept#7]]）——第一个形参是类型形参的概念。

¶10 以 *type-constraint* 开头的 *type-parameter* 为该形参引入立即声明约束：

```cpp run title="immediately-declared.cpp" ok
#include <concepts>
template<typename T> concept C1 = true;
template<typename... Ts> concept C2 = true;
template<typename T, typename U> concept C3 = true;

template<C1 T> struct s1;            // 关联约束 C1<T>
template<C1... T> struct s2;         // (C1<T> && ...)
template<C2... T> struct s3;         // (C2<T> && ...)   注意：不是 C2<T...>
template<C3<int> T> struct s4;       // C3<T, int>       T 插在最前面
template<C3<int>... T> struct s5;    // (C3<T, int> && ...)

template<std::convertible_to<long> T> struct s6;   // std::convertible_to<T, long>
int main() {}
```

`s3` 值得注意：即使 `C2` 本身是变参概念，`C2... T` 也展开为对**每个**元素分别检查 `C2<T>` 的折叠，而不是一次性检查 `C2<T...>`。

为什么是"插在第一个"？因为这让 `template<std::convertible_to<long> T>` 读起来像英语："T convertible to long"。标准库的所有二元概念（`same_as`、`derived_from`、`convertible_to`……）都按照"被约束的类型在前"的约定设计。

```cpp title="value-concept.cpp" error
template<int N> concept Positive = N > 0;
template<Positive T> struct X {};   // error: Positive 不是类型概念（第一个形参不是类型形参）
```

## 常量模板形参的类型（¶11–¶12）

¶11 常量模板形参必须具有以下（可能 cv 限定的）类型之一：

- ¶11.1 **结构化类型**（structural type，见 ¶12）；
- ¶11.2 含有占位符类型的类型（`auto`、`auto&`、`auto*`、`decltype(auto)`、`std::integral auto`，[[dcl.spec.auto]]） {{c++17}}；
- ¶11.3 推导类类型的占位符（如 `template<FixedString s>`，由类模板实参推导决定，[[dcl.type.class.deduct]]） {{c++20}}。

确定形参的类型时，**顶层 cv 限定被忽略**：`template<const int N>` 与 `template<int N>` 声明的是同一种形参。

¶12 **结构化类型**（[[g:structural-type]]）是以下之一：

- ¶12.1 **标量类型**（算术、枚举、指针、成员指针、`std::nullptr_t`，以及 C++26 的 `std::meta::info`）；
- ¶12.2 **左值引用类型**；
- ¶12.3 具有以下性质的**字面类类型**（[[basic.types.general]]）：
    - ¶12.3.1 所有基类和非静态数据成员都是 **public** 且**非 mutable**；
    - ¶12.3.2 所有基类和非静态数据成员的类型都是结构化类型或其（可能多维的）数组。

注意结构化类型的定义是**递归的**，且只关心"成员能否从外部看到并逐一比较"，而不要求类型平凡。右值引用类型**不是**结构化类型。

### 为什么是这些条件？

常量模板形参的值是类型身份的一部分：`X<a>` 和 `X<b>` 是否是同一个类型，取决于 `a` 和 `b` 是否**模板实参等价**（[[temp.type#2]]）。这个等价关系必须：

1. **在编译期可判定**——所以要求字面类型；
2. **在不同 TU 中一致**——名字修饰（mangling）必须能把值编码进符号名，链接器靠符号名合并特化。所以值必须能被**逐成员地**编码；
3. **与用户自定义的 `operator==` 无关**——如果 `X<a>` 与 `X<b>` 的同一性由用户的 `==` 决定，不同 TU 可能看到不同的 `==`，或者 `==` 不满足等价关系，类型系统就会崩溃。

"所有成员 public"保证了"逐成员比较"在语义上是用户可观察的、不会暴露封装细节；"非 mutable"保证模板形参对象（const）的值不会变。

```cpp title="structural.cpp" error
#include <array>
#include <string_view>
#include <utility>

struct P1 { int x, y; };                      // 结构化
struct P2 { int x; private: int y = 0; };     // 非结构化：有 private 成员
struct P3 { mutable int x; };                 // 非结构化：有 mutable 成员
struct P4 { double d; int* p; int& r; };      // 结构化：double、指针、左值引用都可以
struct P5 : P1 { float f[3]; };               // 结构化：public 基类 + 结构化类型的数组

template<P1 p> struct A1 {};
template<P2 p> struct A2 {};                  // error: P2 不是结构化类型
template<P3 p> struct A3 {};                  // error: P3 不是结构化类型
template<P4 p> struct A4 {};
template<P5 p> struct A5 {};

template<std::array<int, 3> a> struct B1 {};  // OK: std::array 只有一个 public 数组成员
template<std::pair<int, int> p> struct B2 {}; // OK（实践中）：pair 的成员 first/second 是 public
template<std::string_view s> struct B3 {};    // error: string_view 有 private 成员
```

!!! warning "标准库类型是否结构化，标准大多不保证"
    `std::array<int, N>` 是聚合，成员是 public，因此是结构化类型——但标准库规范中它的数组成员是"仅供说明"的，严格说这依赖实现。`std::pair` 在 libc++ 与 libstdc++ 中都可用作常量模板形参类型；`std::tuple`、`std::optional`、`std::string_view` 则都不行（有 private 成员）。写可移植代码时，最好自己定义一个全 public 的聚合。

### 浮点、lambda、联合体

C++20 起浮点类型也是结构化类型（标量），但其模板实参等价是"值**相同**（identical）"而不是"相等"：`0.0` 与 `-0.0` 相等但不 identical，所以是**不同**的实参（[[temp.type#2]]）：

```cpp run title="float-nttp.cpp" ok
#include <type_traits>
template<double D> struct F {};
static_assert(!std::is_same_v<F<0.0>, F<-0.0>>);   // 0.0 == -0.0，但不是同一个模板实参
static_assert(std::is_same_v<F<0.1 + 0.2>, F<0.30000000000000004>>);  // 同一个 double 值

template<auto L> struct Lam {};
static_assert(!std::is_same_v<Lam<[]{}>, Lam<[]{}>>);  // 每个 lambda 有不同的闭包类型

union U { int i; float f; };
template<U u> struct UU {};
static_assert(!std::is_same_v<UU<U{.i = 0}>, UU<U{.f = 0}>>);  // 活跃成员不同 ⇒ 不同
int main() {}
```

无捕获的闭包类型是没有成员的字面类类型，因而是结构化的；联合体只要所有成员 public、非 mutable、结构化即可。

### 不允许的类型（¶14 注 4）

¶14 注：常量模板形参不能是 *cv* `void`；但 `void*` 可以。此外右值引用、类类型中有 private 成员的类型、`std::string` 这类非字面类型都不行。

```cpp title="void-param.cpp" error
template<void v> class X;       // error
template<void* pv> class Y;     // OK
template<int&& r> class Z;      // error: 右值引用不是结构化类型
```

## 模板形参对象（¶13）

¶13 某些构造指涉**模板形参对象**（template parameter object）：具有**静态存储期**、**非 volatile 的 const 类型**的独立对象。**没有两个模板形参对象是模板实参等价的**——换句话说，每个"值"恰好有一个对象。

指名类类型 `T` 的常量模板形参的 *id-expression*，表示类型为 `const T` 的模板形参对象，它与（转换到形参类型后的）对应模板实参模板实参等价（[[g:template-parameter-object]]）。

注 3 把值类别讲清楚了：

| 常量模板形参的类型 | *id-expression* 的值类别 | 能否取地址 |
|---|---|---|
| 非类类型、非引用（`int N`） | prvalue | 不能（`&N` 非法） |
| 类类型 `T`（`A a`） | lvalue，类型 `const T` | 能，得到模板形参对象的地址 |
| 引用类型（`const X& x`） | lvalue（引用所指的对象） | 能 |

```cpp title="param-object.cpp" error
struct A { int v; };

template<const int& x, int i, A a>
void f() {
    i++;                    // error: 不能修改模板形参的值（i 是 prvalue）
    (void)&x;               // OK
    (void)&i;               // error: 不能对非引用的非类类型形参取地址
    (void)&a;               // OK: 模板形参对象
    int& ri = i;            // error: 非 const 左值引用不能绑定到 prvalue
    const int& cri = i;     // OK: 绑定到临时对象
    const A& ra = a;        // OK: 绑定到模板形参对象本身
    (void)cri; (void)ra;
}
```

"每个值恰好一个对象"有可观察的后果：相同值的两个特化中，`&a` 指向**同一个**对象。

```cpp run title="param-object-identity.cpp" ok
struct A { int v; };

template<A a> constexpr const A* addr() { return &a; }

static_assert(addr<A{1}>() == addr<A{1}>());   // 同一个模板形参对象
static_assert(addr<A{1}>() != addr<A{2}>());
int main() {}
```

这与字符串字面量形成对比：两个相同的字符串字面量是否是同一个对象是**未指明**的（[[lex.string]]），这正是字符串字面量不能直接作为指针型常量模板实参的原因之一（[[temp.arg.nontype#6]]）。

注 2：{{c++26}} 也可以存在**数组类型**的模板形参对象（由 `std::define_static_array` 等反射设施创建，[[meta.define.static]]），但它们永远不会被一个指名常量模板形参的 *id-expression* 表示；这种对象的地址可能与其他存活对象的地址不唯一（[[intro.object]]）——类似字符串字面量。

## 数组与函数类型的调整（¶15）

¶15 类型为"`T` 的数组"或函数类型 `T` 的常量模板形参被**调整**为"指向 `T` 的指针"——与函数形参的调整一样。

```cpp run title="adjust.cpp" ok
template<int* a>   struct R {};
template<int b[5]> struct S {};     // 被调整为 int*
int p;
R<&p> w;        // OK
S<&p> x;        // OK: 形参调整
int v[5];
R<v> y;         // OK: 数组到指针的隐式转换
S<v> z;         // OK: 调整 + 转换
int main() {}
```

注意：要传"数组本身"，应使用数组引用 `template<int (&arr)[5]>`，它不会被调整。

## 带约束的占位符（¶16）

¶16 用含有带 *type-constraint* 的占位符声明的常量模板形参，为与该占位符对应的**虚构类型**引入立即声明约束：

```cpp title="constrained-auto.cpp" error
#include <concepts>
template<std::integral auto N> struct I {};   // 关联约束 std::integral<decltype(N) 的虚构类型>
I<3>   a;     // OK
I<3.0> b;     // error: 约束不满足
```

## 默认模板实参（¶17–¶21）

### 在哪里可以写（¶17）

¶17 **默认模板实参**（default template argument）是在 *template-parameter* 中 `=` 之后指定的模板实参。规则：

1. **形参包不能有默认实参**（包的"默认"就是空包）。
2. 默认实参可以写在模板声明中。
3. 在类外定义类模板成员时，其 *template-parameter-list* 中**不能**写默认实参——默认实参属于成员声明，只能在类内写。
4. **友元类模板声明**中不能写默认实参。
5. 如果**友元函数模板**声明 `D` 指定了默认模板实参，那么 `D` 必须是**定义**，且不能有其他声明从 `D` 可达或 `D` 从它可达。

```cpp title="default-where.cpp" error
template<class... Ts = int> struct P;                    // error: 形参包不能有默认实参

template<class T> struct A { template<class U> void f(); };
template<class T> template<class U = int>
void A<T>::f() {}                                        // error: 类外成员定义不能加默认实参

template<class T> struct C {
    template<class U = int> friend void h(U);            // error: 有默认实参的友元函数模板声明必须是定义
    template<class U = int> friend void k(U) {}          // OK
};
```

规则 4、5 的动机都是**避免同一个模板在不同地方被看到不同的默认实参**。友元声明是"埋在类里的命名空间作用域声明"，如果允许它添加默认实参，那么一个模板的默认实参会取决于哪个类模板被实例化过——这是不可接受的不确定性。

!!! impl "编译器现状"
    截至写作时，Clang 23 不诊断**友元类模板**上的默认实参（规则 4），也不诊断"有默认实参的友元函数模板定义之前已有其他声明"（规则 5 后半）。

### 合并（¶18）

¶18 可用的默认模板实参集合是把所有**先前声明**中的默认实参**合并**得来的，方式与默认函数实参相同（[[dcl.fct.default]]）：

```cpp run title="merge.cpp" ok
#include <type_traits>
template<class T1, class T2 = int> class A;
template<class T1 = int, class T2> class A;      // 合并后等价于 <class T1 = int, class T2 = int>
template<class T1, class T2> class A {};

static_assert(std::is_same_v<A<>, A<int, int>>);
int main() {}
```

同一个形参的默认实参只能指定一次（在同一作用域中不能重复给出，哪怕值相同）。

### 顺序规则：类模板与函数模板不同（¶19）

¶19 是"默认实参必须靠后"规则的精确版本：

| 模板种类 | 有默认实参的形参之后 | 形参包的位置 |
|---|---|---|
| 类模板、变量模板、别名模板 | 后续每个形参都必须有默认实参或是形参包 | **主**模板中，形参包必须是最后一个 |
| 函数模板 | 无限制 | 形参包之后的形参必须能从函数形参类型列表推导，或有默认实参 |
| 推导指引模板 | — | 没有默认实参的形参必须能从推导指引的形参类型列表推导 |

为什么函数模板不同？因为类模板的实参只能**按位置显式给出**——`B<int>` 中的 `int` 只能对应第一个形参，所以默认实参之后必须全有默认值，否则后面的形参无从得到实参。而函数模板的实参主要来自**推导**，位置无所谓：

```cpp title="default-order.cpp" error
template<class T1 = int, class T2> class B;     // error: T2 没有默认实参

template<class T = int, class U> void f(U) {}   // OK: U 从函数实参推导
template<class R = void, class... Args, class F>
R invoke_like(F, Args...);                      // OK: Args 和 F 都可推导

template<class... T, class... U> void g() {}    // error: U 既不可推导也没有默认实参
template<class... T, class U> void h() {}       // error: 同上
```

!!! impl "编译器现状"
    截至写作时，Clang 23 只诊断上例中的 `B`；对 `g`、`h` 两个函数模板的声明不报错（直到试图调用时才因无法推导而失败）。标准例 8 明确把它们标为非良构。

"**主**"模板这个限定很关键：部分特化中，形参包可以不在最后（部分特化的形参都是从主模板的实参推导出来的）：

```cpp run title="pack-not-last.cpp" ok
template<class... Ts> struct List {};
template<class L, class T> struct Append;
template<class... Ts, class T>                  // 部分特化：包不是最后一个，OK
struct Append<List<Ts...>, T> { using type = List<Ts..., T>; };

static_assert(__is_same(Append<List<int>, char>::type, List<int, char>));
int main() {}
```

C++98 中函数模板根本**不允许**有默认模板实参；C++11 起才允许（[[CWG226]]）。这为 `std::enable_if` 的"默认模板实参 SFINAE"写法铺平了道路：`template<class T, class = std::enable_if_t<...>>`。

### `>` 的解析（¶20）

¶20 解析常量模板形参的默认实参时，**第一个非嵌套的 `>`** 被当作 *template-parameter-list* 的结束：

```cpp title="gt-default.cpp" error
template<int i = 3 > 4 > class X {};      // error: 语法错误
template<int i = (3 > 4) > class Y {};    // OK
```

这与 [[temp.names#8]] 中 *template-argument-list* 的规则一致：在尖括号里使用 `>` 运算符必须加括号。

### 模板模板形参的形参的默认实参（¶21）

¶21 模板模板形参自己的形参也可以有默认实参；指定时，它们只在该模板模板形参的作用域内生效：

```cpp title="tt-default.cpp" error
template<template<class TT = float> class T> struct A {
    void f();
    void g();
};
template<template<class TT> class T> void A<T>::f() {
    T<> t;            // error: 这里的 TT 没有默认实参
}
template<template<class TT = char> class T> void A<T>::g() {
    T<> t;            // OK: T<char>
}
```

也就是说，模板模板形参的默认实参属于**那一个声明**，而不像普通默认实参那样跨声明合并。

¶21 最后一条：**模板模板形参的关联约束不能包含概念依赖约束**（[[temp.constr.concept]]）{{c++26}}：

```cpp title="tt-concept-dependent.cpp" error
template<
    template<typename> concept C,
    template<C> class TT          // error: C 形成概念依赖约束
>
struct A {};
```

原因：模板模板实参的匹配要比较约束的包含关系（[[temp.arg.template#4]]），而概念依赖约束在 `C` 确定之前无法规范化，也就无法比较。

!!! impl "编译器现状"
    截至写作时，Clang 23 接受上面的代码，没有诊断。

## 实现视角

!!! impl "实现视角"
    - **名字修饰**：常量模板实参被编码进修饰名。Itanium ABI 中整数编码为 `Li42E`（Clang 把 `fi<42>()` 修饰为 `_Z2fiILi42EEvv`），类类型的值按成员逐个编码（`addr<A{1}>` 修饰为 `_Z4addrIXtl1ALi1EEEEPKS0_v`，`tl` 表示花括号初始化），浮点按位模式编码（`fd<1.0>` 中的实参为 `Ld3ff0000000000000E`）——这也是为什么浮点实参比较的是"identical"而不是 `==`：位模式不同就是不同的符号。
    - **模板形参对象**在目标文件中是一个 COMDAT 的只读常量（Itanium 修饰名以 `_ZTA` 开头，例如 `_ZTAXtl1ALi1EEE`），保证跨 TU 唯一，从而实现 ¶13 的"每个值恰好一个对象"。
    - **结构化检查时机**：Clang 在**声明模板形参时**就检查类型是否结构化（`template<P2 p>` 处报错），而不是等到使用时。

## 历史与演进

!!! history "历史与演进"
    - **C++98**：类型形参；整型/枚举、对象或函数的指针/引用、成员指针形式的"非类型"形参；类模板模板形参。函数模板不能有默认模板实参。
    - **C++11**：模板形参包；函数模板可以有默认模板实参（CWG 226）；`std::nullptr_t` 形参；别名模板可作模板模板实参。
    - **C++17**：`template<auto N>`（[[P0127R2]]），¶11.2。
    - **C++20**：类类型的常量模板形参（[[P0732R2]]），后由 [[P1907R1]] 改为现在的"结构化类型"定义并允许浮点类型；*type-constraint*；推导类类型的占位符作形参类型（¶11.3）。
    - **C++26**：变量模板模板形参与概念模板形参（[[P2841]]）；"非类型模板形参"更名为"常量模板形参"；`std::meta::info` 成为标量类型，可作常量模板形参。

    P0732R2 最初的方案要求类类型具有"强结构化相等"（*strong structural equality*：即 `operator==` 被默认为 `= default`）。P1907R1 放弃了与 `operator==` 的关联，改为现在纯粹基于"成员可见且递归结构化"的定义——正是上文"与用户的 `operator==` 无关"那一条的由来。

## 陷阱

!!! pitfall "常见误解"
    - **"`template<std::string s>` 在 C++20 可以用"**——不行，`std::string` 不是字面类型（它的值不能在编译期之外留存）且有 private 成员。要传字符串，自己写一个全 public 的 `fixed_string` 聚合（见 [[temp.arg.nontype]]）。
    - **"`C... Ts` 等价于 `C<Ts...>`"**——不是，等价于 `(C<Ts> && ...)`（¶9）。
    - **"类模板的默认实参也可以不靠后，像函数模板一样"**——不行（¶19）。
    - **"相同值的常量形参，`&p` 在不同特化中不同"**——对类类型形参而言是同一个模板形参对象（¶13）。
    - **"`const int N` 与 `int N` 是不同的模板"**——顶层 cv 被忽略（¶11），`template<int N> void h();` 与 `template<const int N> void h() {}` 是同一个函数模板的声明与定义。

## 思考题

!!! question "思考题 1"
    下列哪些类型可以作为常量模板形参的类型？

    ```cpp
    struct A { int x; constexpr A(int v) : x(v) {} };              // (a)
    struct B { int x; bool operator==(const B&) const = delete; }; // (b)
    struct C { const int& r; };                                    // (c)
    struct D { int&& r; };                                          // (d)
    struct E { std::array<float, 2> a; };                          // (e)
    ```

<details markdown="1">
<summary>答案</summary>

- (a) 可以：有 `constexpr` 构造函数的字面类，成员 public。用户定义构造函数不影响结构化。
- (b) 可以：结构化类型与 `operator==` 无关（P1907R1 之后），删除 `==` 也不影响。
- (c) 可以：左值引用是结构化类型。但实参中的引用不能绑定到临时对象（[[temp.arg.nontype#6]]）。
- (d) 不可以：右值引用不是结构化类型。
- (e) 实践中可以（`std::array` 成员 public、`float` 是标量）。
</details>

!!! question "思考题 2"
    为什么下面第一个声明非法而第二个合法？

    ```cpp
    template<class T = int, class U> struct S;
    template<class T = int, class U> void f(U);
    ```

<details markdown="1">
<summary>答案</summary>

类模板的实参只能显式按位置给出，`S<X>` 中的 `X` 永远对应 `T`，`U` 无法得到实参，所以 ¶19 要求默认实参之后的形参都有默认实参。函数模板的 `U` 可以从调用实参推导，`f(1.0)` 得到 `T = int, U = double`，所以没有顺序限制。
</details>

!!! question "思考题 3"
    `template<auto... Vs> struct V {};` 中 `V<1, 'a', nullptr>` 合法吗？各个 `Vs` 的类型是什么？

<details markdown="1">
<summary>答案</summary>

合法。`auto...` 形参包的每个元素**各自**推导类型（[[temp.arg.nontype#1]] 对每个实参虚构一个声明 `auto x = E;`），分别是 `int`、`char`、`std::nullptr_t`。若想让所有元素同类型，用 `template<class T, T... Vs>`。
</details>

## 小结

!!! summary "小结"
    | 主题 | 要点 |
    |---|---|
    | 形参种类 | 类型、常量、类型模板模板、变量模板模板 {{c++26}}、概念 {{c++26}} |
    | *type-constraint* | `C<A...> T` ⇒ 立即声明约束 `C<T, A...>`；包 ⇒ `(C<T> && ...)`；须是类型概念 |
    | 常量形参类型 | 结构化类型、含占位符的类型、推导类类型占位符；顶层 cv 忽略；数组/函数调整为指针 |
    | 结构化类型 | 标量、左值引用、成员全 public 非 mutable 且递归结构化的字面类 |
    | 模板形参对象 | 类类型形参 ⇒ `const T` 左值，静态存储期，同值唯一 |
    | 默认实参 | 包不能有；类外成员定义、友元类模板不能写；可跨声明合并；类模板须靠后，函数模板不须 |
