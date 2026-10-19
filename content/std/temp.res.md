---
title: 名字决议
summary: 模板定义里的名字何时、在哪里查找：非依赖名在定义处一次绑定，依赖名推迟到每个特化；typename 何时必需、何时可省（仅类型语境）；以及“不可能有合法特化”等一组 IFNDR 规则，编译器据此可以在实例化之前检查模板。
status: done
covers: temp.res.general
papers: P0634R3, P1787R6, P2593R1
related: temp.local, temp.dep, temp.dep.res, temp.point, temp.names, basic.lookup, stmt.if, dcl.pre, topics/two-phase-lookup
tags: 模板, 名字查找, typename, 两阶段查找, IFNDR
updated: 2026-10-17
---

```cpp
template<class T> void f(T t) {
    T::x * p;          // 乘法？还是声明一个指针 p？
    t.get<0>();        // 调用成员模板？还是 (t.get < 0) > ()？
    g(t);              // 哪个 g？现在看得见的，还是将来才声明的？
}
```

写模板的人知道 `T` 将是什么，编译器在看到这段定义时却不知道。可 C++ 的语法是上下文相关的：`a * b` 是表达式还是声明、`<` 是小于号还是模板实参列表的开头，都取决于名字指什么。如果所有判断都推迟到实例化，模板定义就只能当作一串记号保存起来，等到实参确定后再重新解析。MSVC 很多年就是这么做的，代价是模板里的错误要等到模板被使用时才暴露，而且同一个模板在不同地方实例化可能得到不同的意思。

第 13.8 节 [[temp.res]]（name resolution）采用的是另一种模型：编译器看到模板定义时就完整地解析它，其中的名字分成两类：

- **非依赖名**（non-dependent name）：含义不随模板实参变化，在定义处查找一次，结果固定下来；
- **依赖名**（dependent name，精确定义见 [[temp.dep]]）：查找结果取决于模板形参，推迟到每个特化（替换之后）再查。

这就是通常所说的两阶段名字查找（two-phase name lookup，见 [[topics/two-phase-lookup]]）。为了让第一阶段的解析能进行，语言要求程序员在依赖名指类型或模板时用 `typename` / `template` 标明，除非语境本身已经说明它只能是类型（¶4 的仅类型语境）。为了让第一阶段的检查有意义，标准又给出一组 IFNDR 规则（¶6）：如果一个模板不可能有任何合法特化，或者其中非依赖的部分本身就是错的，编译器可以在不实例化的情况下拒绝它，但不是必须。

本节在第 13 章中的位置：

| 子条款 | 内容 |
|---|---|
| [[temp.res.general]]（本页） | 查找从哪里出发、`typename`、仅类型语境、定义时检查 |
| [[temp.local]] | 模板里的注入类名、模板形参的隐藏规则 |
| [[temp.dep]] | 什么是依赖的：依赖类型、类型依赖/值依赖表达式、当前实例化 |
| [[temp.dep.res]] | 依赖名在哪里查：实例化点、实例化语境中的 ADL |

读本页前最好熟悉名字查找的一般规则（[[basic.lookup]]、[[basic.lookup.qual]]）和 ADL（[[basic.lookup.argdep]]）。

## 名字从哪里查找（¶1）

¶1 出现在模板 `T` 的某个声明 `D` 里的名字，从它出现的位置开始查找。不过这个位置指的是 `T` 的某个未指明的声明：它要么就是 `D` 本身，要么是从 `D` 可达、且从它出发再也到达不了另一个也含有这次使用的 `T` 的声明。

这段拗口的话处理的是：同一个模板可以有多个声明（例如在不同 TU、或者通过模块导入看到的同一定义的多个副本），名字的出现位置应当选哪一份。直观地说，就是最新的那份含有这个名字的声明。对普通代码，你可以把它简单理解为：名字在模板定义里它出现的地方查找，和非模板代码一样。

接下来是关键的一句：如果名字是依赖的（[[temp.dep]]），那么它要针对每个特化（在替换之后）查找，因为查找结果取决于模板形参。

!!! std
    If the name is dependent (as specified in [temp.dep]), it is looked up for each specialization (after substitution) because the lookup depends on a template parameter.

    依赖名在每个特化里（替换后）各查一次。

所以一个依赖名可能要查找两次。注 1 指出，某些依赖名在解析时也要先查一下，目的是判断它到底是不是依赖的，或者为了决定紧随其后的 `<` 是不是模板实参列表的开头（[[temp.names#7]]）。真正决定它指什么的，是实例化时的那次查找。非依赖名则只在定义处查一次。

注 1 还说：*using-declarator* 在特化中永远不是依赖的，所以在特化的查找中，它被替换为它指名的声明（[[basic.lookup.general]]）。

### 依赖的 conversion-function-id（例 1）

```cpp run ok
struct A { operator int() { return 42; } };

template<class B, class T>
struct D : B {
    T get() { return operator T(); }   // operator T 依赖于 T：推迟到特化时查找
};

int f(D<A, int> d) { return d.get(); } // OK：特化时在 D<A,int> 中找到 A::operator int
int main() { return f({}) == 42 ? 0 : 1; }
```

在模板定义里，`operator T` 根本不知道是哪个转换函数；何况它来自依赖基类 `B`，定义时也无从查找（依赖基类不参与定义时的查找，见 [[temp.dep.type#3]]）。[[temp.dep.general#2]] 规定 conversion-type-id 依赖时这个名字是依赖的，所以推迟到特化。

### 依赖调用 vs 非依赖调用（例 2）

标准的例 2 是理解两阶段查找最好的入门例子。下面是可以运行的改编版：

```cpp run ok title="two_phase.cpp"
#include <cstdio>
void f(char) { std::puts("f(char)"); }

template<class T> void g(T t) {
    f(1);        // 非依赖：定义处查找，只看得到 f(char)，就此绑定
    f(T(1));     // 依赖调用：实参类型依赖于 T
    f(t);        // 依赖调用
}

enum E { e };
void f(E) { std::puts("f(E)"); }   // 在 g 的定义之后才声明

int main() {
    g(e);        // f(char) f(E) f(E)
    g('a');      // f(char) f(char) f(char)
}
```

逐个分析：

- `f(1)`：实参 `1` 不是类型依赖的，所以这不是依赖调用（[[temp.dep.general#2]]），`f` 在定义处查找，只找到 `f(char)`。绑定已经完成，哪怕之后声明了 `f(int)` 这样更好的匹配，结果也不会改变。
- `f(T(1))`、`f(t)`：实参类型依赖于 `T`，是依赖调用。按 [[temp.dep.candidate]]，候选函数 = 定义处的无限定查找结果 ∪ 定义语境与实例化语境中的 ADL 结果。`g(e)` 时 `T = E`，`E` 的关联命名空间是全局命名空间，实例化语境中的 ADL 找到了后声明的 `f(E)`，它是精确匹配，胜出。
- `g('a')` 时 `T = char`，基本类型没有关联命名空间，ADL 什么都不加，只有定义处找到的 `f(char)`。

例 2 原文还有一行 `dd++;`，其中 `dd` 在模板之后才声明为 `double`。`dd` 不是依赖名，定义处查找失败，程序非良构。Clang 和 GCC 会在模板定义处直接报告未声明的标识符，不用等到实例化：

```cpp error
template<class T> void g(T) {
    dd++;        // error: dd 不是依赖名，定义处找不到
}
double dd;
```

!!! pitfall "推迟到实例化时查找只适用于依赖名"
    常见的误解是，模板里的名字都是实例化时才查的。只有依赖名如此，而且即便是依赖调用，普通的无限定查找也只在定义处做，实例化处只追加 ADL（[[temp.dep.candidate]]）。所以 `f(t)` 中 `T = int` 时，定义之后才声明的 `f(int)` 永远找不到：`int` 没有关联命名空间。

### 模板实参的成员不影响绑定（例 3）

```cpp run ok
struct A {
    struct B { };
    int a;
    int Y;
};

int a;

template<class T> struct Y : T {
    struct B { };
    B b;                          // Y 自己的 B，不是 A::B
    void f(int i) { a = i; }      // ::a，不是 A::a
    Y* p;                         // 注入类名：Y<T>，不是 A::Y
};

Y<A> ya;
int main() { ya.f(1); return a == 1 ? 0 : 1; }
```

`Y<A>` 的基类是 `A`，`A` 里恰好有 `B`、`a`、`Y`。但这些名字在模板定义里都不是依赖的：`T` 是依赖基类，定义时不被搜索，`B`、`a`、`Y` 在定义时分别绑定到 `Y::B`、`::a`、注入类名 `Y`。实例化成 `Y<A>` 时不会重新查找，所以 `A` 的成员不会取代它们。

这正是两阶段查找保护模板作者的地方：模板的含义由作者在定义处看到的东西决定，不会因用户传进来的类型而悄悄改变。想要用基类成员，就必须把名字变成依赖的（`this->a`、`T::a`），见 [[temp.dep.res]]。

## 可达但未被找到的默认实参（¶2）

¶2 如果某个声明引入了默认实参或默认模板实参，这个声明从特化的实例化点（[[temp.point]]）可达，但特化中的查找没有找到它，而考虑这个默认实参又会改变程序的合法性或含义，那么程序 {{ifndr}}。

典型场景：依赖调用的无限定查找只在定义处做，之后的重声明可以给函数补上默认实参：

```cpp ifndr
void f(int, int);
template<class T> void g(T t) { f(t); }   // 依赖调用；定义处只找到 f(int, int)
void f(int, int = 0);                     // 重声明，补上默认实参
void use() { g(1); }                      // IFNDR：若考虑新默认实参，调用就合法了
```

特化 `g<int>` 的查找：定义处找到 `void f(int, int)`（那个声明没有默认实参），`int` 无关联命名空间所以 ADL 不补充。补默认实参的重声明从实例化点可达，但查找没有找到它；若考虑它，`f(t)` 就合法了，这正是 ¶2 描述的情形。标准不要求诊断，因为在实现里默认实参通常是函数的属性，随声明累积，编译器很难区分它来自哪一份声明。Clang 在这里报错，并附注提示 `f` 应该在调用点之前声明。

## typename-specifier（¶3）

```text
typename-specifier:
    typename nested-name-specifier identifier
    typename nested-name-specifier template(opt) simple-template-id
```

¶3 *typename-specifier* 的组成名字是它的 *identifier*（若有），以及 *nested-name-specifier* 与 *simple-template-id* 中的组成名字。它所指称的类型（或类模板），与去掉 `typename` 后形成的 *simple-type-specifier*（[[dcl.type.simple]]）所指称的相同。

注 2 强调：有了 `typename`，查找仍然是普通的限定名查找（[[basic.lookup.qual]]）。`typename` 并不把查找限制为只找类型，它只是向解析器承诺这里是一个类型。如果实例化时普通查找找到的不是类型，程序非良构：

```cpp error
struct A {
    struct X { };
    int X;            // 数据成员 X 隐藏了同名的类 X
};
struct B { struct X { }; };

template<class T> void f(T) { typename T::X x; }

void foo() {
    f(B{});           // OK：B::X 是类
    f(A{});           // error: A::X 找到的是数据成员，不是 struct A::X
}
```

对比：`struct T::X x;` 这种详述类型说明符用的是仅类型查找（[[basic.lookup.elab]]），会忽略数据成员；`typename` 则不会。

### typename 写在哪里都行吗？

`typename` 只能用在带 *nested-name-specifier* 的名字前（语法如此），不能写 `typename T`、`typename int`。C++11 起它也可以用在模板之外（只要名字是限定的），这对宏和代码生成很方便：

```cpp ok
struct S { using type = int; };
typename S::type x = 0;   // OK：模板外也允许，只是多余
```

## 仅类型语境：何时可以省略 typename（¶4–¶5）

在 C++17 及以前，规则很简单：依赖的限定名如果指类型，一律要写 `typename`（基类列表和成员初始化列表除外）。C++20 的 [[P0634R3]]（“Down with typename!”）注意到，很多位置在语法上只可能是类型，在这些地方要求 `typename` 只是徒增负担。于是引入了[[g:type-only-context|**仅类型语境**]]（type-only context）。

¶4 一个限定或无限定名字处于仅类型语境，如果它是以下结构的终端名（terminal name）：

| 编号 | 语境 | 例子 |
|---|---|---|
| ¶4.1 | *typename-specifier*、*type-requirement*、*nested-name-specifier*、*elaborated-type-specifier*、*class-or-decltype*（基类、成员初始化器）、*using-enum-declarator* | `typename T::X`、`requires { typename T::X; }`、`struct D : T::Base` |
| ¶4.2 | *friend-type-specifier* 中的 *simple-type-specifier* | `friend T::R;` |
| ¶4.3.1 | *new-type-id* | `new T::R{}` |
| ¶4.3.2 | *defining-type-id* | `using A = T::R;` |
| ¶4.3.3 | *conversion-type-id* | `operator T::R();` |
| ¶4.3.4 | 尾置返回类型 | `auto f() -> T::R;` |
| ¶4.3.5 | 类型模板形参的默认实参 | `template<class T, class U = T::R>` |
| ¶4.3.6 | 四种具名转型的 *type-id* | `static_cast<T::R>(x)` |
| ¶4.4.1 | 命名空间作用域的 *simple-declaration* / 函数定义的 *decl-specifier-seq* | `template<class T> T::R f();` |
| ¶4.4.2 | *member-declaration* | 类模板里的 `T::R m;` |
| ¶4.4.3 | *member-declaration* 中的形参声明（不在默认实参里） | `void f(T::R);` 作为成员 |
| ¶4.4.4 | *declarator-id* 是限定名的函数声明的形参 | `void S<T>::f(T::R) { }` |
| ¶4.4.5 | lambda 声明符、*requirement-parameter-list* 的形参 | `[](T::R r) {}`、`requires(T::R r) {}` |
| ¶4.4.6 | 模板形参的 *parameter-declaration*（必然是常量模板形参） | `template<T::R V>` |

¶4 末尾还为 {{c++26}} 的反射补了一句：*splice-specifier* / *splice-specialization-specifier* 处于仅类型语境，当且仅当同一位置上一个假想的限定名会处于仅类型语境（所以 `using Alias = [:^^int:];` 不需要 `typename`）。

这些位置的共性是：此处若不是类型，语法就无法成立。反过来，块作用域的声明、普通命名空间作用域函数的形参、模板实参、`sizeof(...)` 的操作数等不在表中的位置，都存在表达式的合法解释，所以 `typename` 仍是必需的。

¶5 处于仅类型语境、终端名依赖的 *qualified-id* 被视为指称类型。不在仅类型语境的依赖限定名则被假定不是类型（除非写 `typename`）。另外，指向一个终端名依赖、且带 `typename` 关键字的 *using-declarator* 的名字，被解释为 *typedef-name*。

### 一张对照例子

```cpp run ok title="down_with_typename.cpp"
template<class T, class U = T::R>              // ¶4.3.5 类型模板形参的默认实参
struct S {
    T::R m;                                    // ¶4.4.2 成员声明
    void f(T::R);                              // ¶4.4.3 成员函数形参
    operator T::R();                           // ¶4.3.3 转换类型
    static T::R sm;
    friend T::R;                               // ¶4.2
    using A = T::R;                            // ¶4.3.2
    auto g() -> T::R { return static_cast<T::R>(m); }   // ¶4.3.4、¶4.3.6
};
template<class T, class U> void S<T, U>::f(T::R) { }   // ¶4.4.4：declarator-id 是限定名
template<class T, class U> T::R S<T, U>::sm{};          // ¶4.4.1

template<class T> T::R gv{};                   // ¶4.4.1：命名空间作用域
template<class T> void blk() {
    auto l = [](T::R r) { return r; };         // ¶4.4.5 lambda 形参
    typename T::R local{};                     // 块作用域：仍须 typename
    auto* p = new T::R{};                      // ¶4.3.1 new-type-id
    delete p; (void)l; (void)local;
}

struct X { using R = int; };
template struct S<X>;
template void blk<X>();
int main() { }
```

注意 `blk` 里的 `typename T::R local{};`：块作用域的声明不在 ¶4.4 的列表中（¶4.4 只列了命名空间作用域与类作用域的声明），`typename` 不能省。块作用域是 `typename` 最常"还得写"的地方：

```cpp error
template<class T> void f() {
    T::R local;         // error: 块作用域不是仅类型语境，须写 typename
}
```

### 微妙之处：形参声明到底在哪个作用域

¶4.4.3 与 ¶4.4.4 的区分很精细：

```cpp ifndr
template<class T> T::R f();          // OK：命名空间作用域函数声明的返回类型
template<class T> void f(T::R);      // IFNDR：试图声明一个 void 类型的变量模板
```

第二行里 `f` 不是限定名，它的形参不是仅类型语境，`T::R` 被当作表达式。于是 `void f(T::R)` 被解析成一个类型为 `void`、以 `(T::R)` 直接初始化的变量模板 `f`。`void` 变量不可能有合法特化，所以 IFNDR（¶6.1）。Clang 会在这里报告变量具有不完整类型 void。

为什么命名空间作用域函数的形参不算仅类型语境？因为在命名空间作用域，`void f(T::R);` 在语法上确实可以是变量声明（`int x(expr);` 是合法的直接初始化）。而成员声明与限定声明符（`S<T>::f`）的形参不可能是变量的初始化器：类内不允许 `int x(expr);` 这种圆括号初始化的成员，重声明 `S<T>::f(...)` 也只能是函数。

```cpp error
template<typename T> void f() {
    void (*pf)(T::X);     // OK：变量 pf，类型 void*，用 T::X 初始化（注意：不是函数指针！）
    void g(T::X);         // error: 块作用域，T::X 不指称类型；试图声明 void 变量 g
}
```

第一行是“最令人困惑的解析”的一个经典变体：`void (*pf)(T::X)` 不是指向接受 `T::X` 的函数的指针，而是 `void* pf(T::X)` 形式的变量声明，用 `T::X` 直接初始化。

### 被假定为非类型的依赖名（¶5，例 6）

```cpp error
template <class T> void f(int i) {
    T::x * i;           // 表达式（乘法），不是声明变量 i
}

struct Foo { typedef int x; };
struct Bar { static int const x = 5; };

int main() {
    f<Bar>(1);          // OK
    f<Foo>(1);          // error: Foo::x 是类型
}
```

在实例化 `f<Foo>` 时，`T::x` 被替换成 `Foo::x`，但解析早已完成：它是表达式中的一个 *qualified-id*，查找却找到了类型，非良构。

¶5 后半句对应的场景：

```cpp run ok
template<class T> struct Base { using type = T; };
template<class T> struct D : Base<T> {
    using typename Base<T>::type;   // 依赖的 using 声明符，带 typename
    type x{};                       // type 被解释为 typedef-name
};
D<int> d;
int main() { }
```

## template 消歧义符

与 `typename` 平行的问题是 `<`：`p->alloc<200>()` 中的 `<` 是小于号还是模板实参列表？规则在 [[temp.names#7]]：只有当 `<` 前的名字查找找到了模板、或者前面写了关键字 `template`、或者满足若干语法条件时，`<` 才开始模板实参列表。依赖的成员名在定义时查不到，所以必须写 `template`：

```cpp run ok
#include <cstddef>
struct X {
    template<std::size_t> X* alloc() { return this; }
    template<std::size_t> static X* adjust() { return nullptr; }
};
template<class T> void f(T* p) {
    T* p2 = p->template alloc<200>();   // OK：< 开始模板实参列表
    T::template adjust<100>();          // OK
    (void)p2;
}
template void f(X*);
int main() { }
```

不写 `template` 时，`p->alloc<200>()` 被解析为 `(p->alloc < 200) > ()`，而 `()` 不是表达式。Clang 会提示缺少 `template` 关键字：

```cpp error
template<class T> void f(T* p) {
    T* p1 = p->alloc<200>();   // error: < 被当作小于号
}
```

几条要点（细节在 [[temp.names]]）：

- 不需要 `template` 的情形：名字是无限定的且查找找到函数或什么都没找到（C++20 [[P0846R0]] 让 `get<0>(t)` 在没有可见的 `get` 模板时也能工作）；名字是仅类型语境中的终端名（[[temp.names#7]] ¶7.3.4），如 `typename T::Y<int>`、成员声明 `T::Y<int> m;`。
- 写了也无妨：即使查找本来就会找到模板，`template` 前缀也是良构的（[[temp.names#11]] 注 5）。
- 不能随意添加：带 `template` 前缀的名字后面必须跟模板实参列表，或指一个类模板/别名模板。后一种用法（如作为模板模板实参 `T::template C`）已被弃用（[[depr.template.template]]）。

!!! impl "Clang 尚未实现 ¶7.3.4"
    按当前草案，`typename T::Y<int>`、类内 `T::Y<long> b;`、`using Z = T::Y<char>;` 中的 `<` 都处于仅类型语境中的终端名之后，无需 `template`。截至写作时（Clang 23），Clang 对这三种写法仍报错并建议加上 `template`。保险起见，可移植代码继续写 `typename T::template Y<int>`。

## 在实例化之前检查模板（¶6）

¶6 首句：模板化实体（templated entity）的合法性可以在任何实例化之前检查。注 3 解释了前提：既然通过 `typename`/`template` 知道了哪些名字是类型、哪些是模板，每个模板的语法都可以这样检查。

然后是本节最重要的 IFNDR 清单。程序 {{ifndr}}，如果：

### ¶6.1：不可能有合法特化

> 对某个模板化实体、或模板化实体中某个 constexpr if 语句的子语句，无法生成任何合法特化（忽略失败的 *static_assert-declaration*），且最内层外围模板未被实例化。

“无法生成合法特化”是对所有可能的模板实参的量化：无论 `T` 是什么，这段代码都是错的。比如 `void f(T::R)` 被解析为 `void` 变量模板；比如 `int a[-int(sizeof(T))];`（数组大小必然为负）。这样的模板没有存在的意义，标准允许编译器提前拒绝，但不强制，因为证明不存在任何合法特化在一般情况下是不可判定的。

“且最内层外围模板未被实例化”是说，如果它确实被实例化了，那就按普通规则报错（非良构，须诊断），不需要 IFNDR。

#### static_assert(false) {{c++23}}

括号里的“忽略失败的 *static_assert-declaration*”是 C++23 [[P2593R1]] 加的，它解决了泛型编程中一个存在多年的问题：

```cpp run ok title="static_assert_false.cpp"
#include <type_traits>
template<class T> int classify(T) {
    if constexpr (std::is_integral_v<T>)            return 1;
    else if constexpr (std::is_floating_point_v<T>) return 2;
    else static_assert(false, "unsupported type");  // C++23 起 OK
}
int a = classify(1), b = classify(1.0);

template<class T> void never_used() { static_assert(false); }  // OK：从未实例化
int main() { }
```

在 C++23 之前，`else static_assert(false, ...)` 这条子语句不可能有合法特化（`false` 不依赖任何东西），于是整个程序 IFNDR。实践中 GCC 和 Clang 会在模板定义处直接报告静态断言失败，即使对所有实际用到的 `T` 那个分支都会被丢弃。程序员只好写：

```cpp
template<class> inline constexpr bool dependent_false = false;
// ...
else static_assert(dependent_false<T>, "unsupported type");
```

这个变通利用的是：`dependent_false<T>` 是值依赖的，理论上存在某个 `T` 的显式特化使其为 `true`，因此存在合法特化。

C++23 换了一种更简洁的规定。[[dcl.pre#13]] 规定在模板定义语境中求值的 `static_assert` 没有效果，与此配合，判断能否生成合法特化时，失败的静态断言不计入。于是：

- 定义处：`static_assert(false)` 不触发；
- 丢弃的分支：constexpr if 的被丢弃子语句不会被实例化（[[stmt.if#2]]），断言永远不被求值；
- 真正走到的分支：实例化时断言失败，正常报错。

```cpp error
template<class T> int f(T) {
    if constexpr (sizeof(T) == 4) return 1;
    else static_assert(false, "unsupported type");
}
int c = f('a');   // error: 实例化 f<char> 时走到 else 分支，静态断言失败
```

P2593 被作为缺陷报告处理，实现通常在 C++17/20 模式下也采用新行为。

!!! lawyer "非依赖的 static_assert 也被推迟了"
    [[dcl.pre#13]] 的措辞是"在模板定义的语境中求值时，声明没有效果"，它不区分条件是否依赖。所以 `template<class T> void f(T) { static_assert(sizeof(int) == 0); }` 在定义时不报错，只有当 `f` 被实例化时才失败。Clang 的行为与此一致。

### ¶6.2：expansion statement {{c++26}}

> 对 *expansion-statement* 的复合语句无法生成合法特化，而它又没有被实例化。

C++26 的展开语句（`template for`，[[stmt.expand]]）的循环体会针对每个元素实例化一次，本质上也是模板化的。如果展开结果为空（比如遍历空 tuple），循环体从未被实例化；此时若它根本不可能合法，就是 IFNDR。规则与 ¶6.1 平行，同样忽略失败的静态断言。

### ¶6.3–¶6.6：默认模板实参、别名模板、约束、变参模板

- ¶6.3 默认模板实参无法产生合法特化，且从未在任何实例化中被用到。
- ¶6.4 别名模板（[[temp.alias]]）没有任何合法特化，且程序中从未指名过它的特化。
- ¶6.5 程序中某个约束表达式（包括隐式引入的）的规范形式中有一个原子约束 A，A 的任何满足性检查都不可能良构，而 A 又从未被检查过。
- ¶6.6 变参模板的每个合法特化都要求模板形参包为空。

¶6.6 值得一提：变参模板如果只能以空包实例化，那它写成变参就没有意义，标准把它当作错误。例 7 中的 `void operator++(int, T... t);` 就是一例：后置 `++` 只能有 `int` 一个额外形参，包必须为空。Clang 对它直接报错。

### ¶6.7：紧随定义之后的假想实例化

> 在定义之后立即进行的一次假想实例化，会因为某个不依赖模板形参的结构（失败的静态断言除外）而非良构。

这条规则把“非依赖部分必须现在就是对的”形式化了。想象在模板定义的右花括号之后立刻用任意实参实例化它：非依赖的结构此时就已经有确定的含义，如果它是错的，那它在任何实例化中都是错的。

```cpp error
template<class T> void f() {
    int* p = 1;          // 非依赖：int 不能初始化 int*
}
```

```cpp error
struct Inc;
template<class T> int f(T) { return sizeof(Inc); }   // 非依赖：此处 Inc 不完整
struct Inc { int x; };
```

后一个例子里，即使 `f` 的所有实例化都发生在 `Inc` 完整之后，在紧随定义的假想实例化中 `Inc` 是不完整的，所以 IFNDR。Clang 两个都在定义处报错。

### ¶6.8：假想实例化与实际实例化的解释不同

> 这样的结构在假想实例化中的解释，与任何实际实例化中对应结构的解释不同。

这条与 ¶6.7 对应，关注的是含义：结构在定义处是合法的，但含义和实际实例化时不同。注 4 列出了几种典型情形：

- ¶6.9 非依赖名中用到的类型在定义处不完整，在实例化处已完整；
- ¶6.10 定义中查找找到一个 *using-declaration*，它是包展开，而对应包为空，实例化时就什么都找不到；
- ¶6.11 实例化用到了定义模板时还没定义的默认实参或默认模板实参；
- ¶6.12 模板实例化中的常量求值用到了定义模板时尚未定义的 const 整型对象的值、constexpr 对象的值、引用的值、或 constexpr 函数的定义；
- ¶6.13 非依赖的 *simple-template-id* 所指的类模板/变量模板特化，实例化自一个定义模板时尚未定义的部分特化，或指名了定义模板时尚未声明的显式特化。

¶6.12 的一个例子：

```cpp ifndr
constexpr int k();
template<class T> void f() { int a[k()]; (void)a; }   // 定义处 k 未定义：k() 不是常量表达式
constexpr int k() { return 3; }
template void f<int>();                                  // 实例化处 k() == 3
```

在定义处，`k()` 不是常量表达式（[[expr.const.core]]：调用未定义的 constexpr 函数），`int a[k()]` 是一个变长数组，在标准 C++ 中非良构；在实例化处它是 `int[3]`。两种解释不同，所以 IFNDR。Clang 的实际行为可以印证这一点：它在定义处就把它当作 VLA（Clang 扩展）并给出 `-Wvla-cxx-extension` 警告，说明它确实在定义处就固定了解释。

这些规则的共同精神是：**非依赖结构的含义在定义处就应该确定，且不应因为后来的声明而改变**。编译器可以选择立即解析与绑定（GCC/Clang），也可以推迟到实例化（旧 MSVC），这两种策略完全不同，而这些规则保证程序的含义不依赖于这个选择。凡是两种策略会给出不同结果的程序，都被宣布为 IFNDR。

### 注 5 与例 7：何时诊断

注 5 说，模板被实例化后，错误按本文档的其他规则诊断；确切何时诊断是实现质量（QoI）问题。

例 7 展示了哪些错误可以提前诊断：

```cpp
int j;
template<class T> class X {
    void f(T t, int i, char* p) {
        t = i;          // 依赖：只有实例化 X::f 且赋值非法时才诊断
        p = i;          // 非依赖：即使 X::f 未被实例化，也可以诊断
        p = j;          // 同上
        X<T>::g(t);     // OK：X<T> 是当前实例化，g 是它的成员
        X<T>::h();      // 可以提前诊断：当前实例化中没有 h，且没有依赖基类
    }
    void g(T t) {
        +;              // 语法错误：可以提前诊断
    }
};
```

`X<T>::h()` 那行用到了 [[temp.dep.type#5]]：限定名的查找上下文是当前实例化、且当前实例化没有依赖基类时，查找什么都没找到的名字不是依赖的，所以可以在定义处报错。若 `X` 有依赖基类，`X<T>::h` 就是依赖的（¶5.4），只能等实例化。

## 默认实参与 noexcept 说明符被视为定义（¶7）

¶7（注 6）：就名字查找而言，函数模板和类模板成员函数的默认实参与 *noexcept-specifier* 被视为定义（[[temp.decls]]）。这意味着它们和函数体一样，按需单独实例化（[[temp.inst]]），其中的名字也遵循本节的两阶段规则，而不是在声明时一次性解析。这也是为什么 [[temp.point#2]]、[[temp.point#3]] 要单独为默认实参和 noexcept 说明符规定实例化点。

!!! impl "实现视角：三大编译器的两阶段模型"
    - Clang、GCC 在看到模板定义时构建完整的 AST，把非依赖名绑定好，依赖的部分保留为依赖节点，实例化时做替换（TreeTransform）。¶6 的 IFNDR 条款给了它们在定义处报错的许可，它们大量使用这一许可（`p = i`、未声明标识符、不完整类型……）。
    - MSVC 历史上把模板体保存为记号流，实例化时才解析，这使它在很长时间里接受大量不合规代码（不写 `typename`、依赖基类成员直接用），见 [[temp.dep.res]]。VS 2017 起的 `/permissive-` 模式引入了符合标准的两阶段查找，可用 `/Zc:twoPhase-` 关掉。
    - Clang 的兼容开关 `-fdelayed-template-parsing` 模拟 MSVC 的推迟解析：函数模板体推迟到翻译单元末尾才解析。这能让依赖 MSVC 旧行为的代码编译，但违背标准，Clang 已提示该选项在 C++20 之后弃用。

!!! history "历史与演进"
    | 版本 | 变化 |
    |---|---|
    | C++98 | 两阶段查找、`typename`/`template` 消歧义、不可能有合法特化即 IFNDR，这些规则都已存在；`typename` 只能在模板内使用 |
    | C++11 | `typename`、`template` 前缀可以用在模板之外 |
    | C++17 | constexpr if：被丢弃的子语句不实例化，¶6.1 增加了 constexpr if 子语句这一粒度 |
    | C++20 | [[P0634R3]] 引入仅类型语境，大量位置可省略 `typename`；[[P0846R0]] 让 `name<...>(args)` 在查找无果时也被当作模板 |
    | C++23 | [[P1787R6]] 用组成名字、终端名、查找上下文等术语重写了名字查找与依赖性的规定；[[P2593R1]] 让失败的 `static_assert` 在判断有无合法特化时不计入 |
    | C++26 | 展开语句（¶6.2）、反射的拼接说明符纳入仅类型语境（¶4 末句） |

## 陷阱

!!! pitfall "typename 不会改为只查找类型"
    `typename T::X` 照常做限定名查找，找到数据成员就报错，不会跳过非类型去找类型（¶3 注 2）。需要仅类型查找时用详述类型说明符 `struct T::X`/`class T::X`。

!!! pitfall "块作用域里还是得写 typename"
    C++20 之后很多人以为 `typename` 可以全面省略。块作用域的声明、命名空间作用域非限定函数的形参、模板实参（`std::vector<typename T::R>`）、`sizeof`/`decltype` 的操作数中仍然需要 `typename`，因为这些位置都存在合法的表达式解释。

!!! pitfall "依赖调用的普通查找不会推迟"
    `template<class T> void g(T t) { f(t); }` 之后才声明的 `f(int)`，对 `g(1)` 永远不可见：无限定查找只在定义处做，ADL 对 `int` 不贡献任何东西。修正方法是把 `f` 的声明提到模板前面，或者让实参类型有关联命名空间。

!!! pitfall "IFNDR 意味着编译通过不代表正确"
    ¶6 的大部分情形 Clang/GCC 能诊断一部分、漏掉一部分，而 MSVC 的宽松模式几乎全部漏掉。代码在一个编译器上通过，换一个编译器（或升级版本）就报错，通常就是撞上了 ¶6。

## 思考题

!!! question "思考题 1"
    下面的代码在 C++20 下是否良构？若不是，属于哪一类错误？
    ```cpp
    template<class T> struct S {
        void f(T::type);
    };
    template<class T> void g(T::type);
    ```

<details markdown="1">
<summary>答案</summary>

`S::f` 的形参处于 ¶4.4.3（*member-declaration* 中的形参声明），是仅类型语境，`T::type` 被当作类型，所以良构。

`g` 是命名空间作用域的函数模板，`g` 不是限定名，其形参不属于 ¶4.4 中任何一项，于是 `T::type` 被当作表达式，`void g(T::type);` 被解析为以 `T::type` 初始化的 `void` 类型变量模板。这样的变量模板不可能有合法特化，按 ¶6.1 IFNDR（例 5 的第二行正是此例）。需要写 `template<class T> void g(typename T::type);`。
</details>

!!! question "思考题 2"
    ```cpp
    template<class T> void f() {
        if constexpr (false) {
            int* p = 1;
        }
    }
    ```
    `f` 从未被实例化。这个程序良构吗？把 `int* p = 1;` 换成 `static_assert(false);` 呢？

<details markdown="1">
<summary>答案</summary>

`int* p = 1;` 是不依赖模板形参的结构，在 ¶6.7 所说的紧随定义的假想实例化中就非良构，即使它位于被丢弃的分支里。constexpr if 的丢弃只是不实例化，并不会让非依赖的错误变得合法。所以程序 IFNDR，Clang/GCC 实际上在定义处报错。

换成 `static_assert(false);` 则良构（C++23 起，[[P2593R1]]）：¶6.1 与 ¶6.7 都明确排除了失败的静态断言，而丢弃的分支永不被实例化。注意这与是否在模板里有关：在非模板函数中，`if constexpr (false) { static_assert(false); }` 仍然会触发，因为在模板外，被丢弃的语句照样要完整检查。
</details>

!!! question "思考题 3"
    为什么标准不干脆规定模板中非依赖的错误必须在定义处诊断，而是用 IFNDR？

<details markdown="1">
<summary>答案</summary>

至少有三个原因。第一，无法生成任何合法特化一般而言是不可判定的（它是对所有可能的模板实参的全称命题），无法要求诊断。第二，标准希望容许推迟解析的实现（历史上的 MSVC，以及 Clang 的 `-fdelayed-template-parsing`）仍然是符合标准的实现。第三，¶6.8 一类问题（定义处与实例化处解释不同）需要同时对比两个语境，要求诊断会迫使编译器在每次实例化时重新检查所有非依赖结构，代价很高。IFNDR 把责任交给程序员，同时允许好的实现尽早报错。
</details>

## 小结

| 规则 | 段落 | 后果 |
|---|---|---|
| 非依赖名在定义处查找、绑定一次 | ¶1 | 后续声明不影响它 |
| 依赖名对每个特化在替换后查找 | ¶1 | 见 [[temp.dep.res]] |
| 可达但未被找到的默认实参改变了含义 | ¶2 | {{ifndr}} |
| `typename` 照常做限定查找 | ¶3 | 找到非类型 → 非良构 |
| 仅类型语境中依赖限定名视为类型 | ¶4–¶5 | 可省略 `typename`（C++20） |
| 其他位置的依赖限定名假定为非类型 | ¶5 | `T::x * i` 是乘法 |
| 无合法特化（忽略失败的 static_assert） | ¶6.1–¶6.6 | {{ifndr}} |
| 非依赖结构在假想实例化中非良构或含义不同 | ¶6.7–¶6.8 | {{ifndr}} |
| 默认实参与 noexcept 说明符视为定义 | ¶7 | 按需实例化 |
