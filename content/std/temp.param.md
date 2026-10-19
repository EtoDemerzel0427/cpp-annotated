---
title: 模板形参
summary: 模板能声明哪几种形参，常量模板形参可以是什么类型，默认模板实参写在哪里、怎样合并，形参包有什么限制。
status: done
papers: P0127R2, P0732R2, P1907R1, P2841
related: temp.pre, temp.arg, temp.arg.nontype, temp.arg.template, temp.type, temp.variadic, temp.constr.decl, dcl.spec.auto, dcl.fct.default
tags: 模板, 常量模板形参, NTTP, 结构化类型, 默认模板实参, 概念模板形参
updated: 2026-10-19
---

!!! tldr
    - 模板形参有五种：类型、常量（旧称非类型）、类型模板模板、变量模板模板、概念模板形参，后两种是 C++26 新增的。
    - `template<C T>` 中的约束会把 `T` 插到概念的第一个实参位置：`C<A> T` 表示 `C<T, A>`，`C... Ts` 表示 `(C<Ts> && ...)`。
    - 常量模板形参的类型必须是结构化类型：标量、左值引用，或成员全部 public、非 mutable、类型也都结构化的字面类。`std::string`、`std::string_view` 都不行。
    - 类类型的常量模板形参在模板里是一个 `const` 左值，每个值在全程序中恰好对应一个模板形参对象。
    - 类模板的默认实参之后的形参都必须有默认实参；函数模板没有这条限制，因为它的实参主要靠推导。

**模板形参**（template parameter）是模板声明里 `template<...>` 中列出的名字。它们是模板的输入：使用模板时给出的模板实参（[[temp.arg]]）一一对应到这些形参上，替换后得到一个具体的类、函数或变量。

## 五种模板形参（¶1–¶3）

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

¶2 按声明的写法，模板形参分为五种，每种接受一种实参：

| 种类 | 写法 | 接受的实参 |
|---|---|---|
| 类型模板形参 | `class T`、`typename T`、`std::integral T` | 类型 |
| 常量模板形参 | `int N`、`auto V`、`Point p` | 值 |
| 类型模板模板形参 | `template<class> class TT` | 类模板、别名模板 |
| 变量模板模板形参 {{c++26}} | `template<class> auto VT` | 变量模板 |
| 概念模板形参 {{c++26}} | `template<class> concept CT` | 概念 |

¶3 后三种统称**模板模板形参**（template template parameter），它们的实参是一个模板，而不是类型或值。

常量模板形参在 C++23 及以前叫**非类型模板形参**（non-type template parameter，NTTP）。C++26 加入变量模板模板形参和概念模板形参之后，"非类型"已经不能把值形参和其他形参区分开，草案于是改称 constant template parameter。规则本身没有变，读旧资料时把 NTTP 对应过来即可。

### 为什么需要传概念和变量模板

C++23 之前，想把一个谓词传给模板，只能把它包成类模板，写成 `template<class> class Pred` 再用 `Pred<T>::value`。`std::is_integral_v` 这样的变量模板、`std::integral` 这样的概念都不能直接传。C++26 的 [[P2841]] 补上了这两种形参：

```cpp run title="concept-param.cpp" ok
#include <concepts>

// 所有 Ts 都满足 C
template<template<class> concept C, class... Ts>
concept all_satisfy = (C<Ts> && ...);

static_assert(all_satisfy<std::integral, int, long, char>);
static_assert(!all_satisfy<std::integral, int, double>);

// 用概念模板形参约束函数形参
template<template<class> concept C>
void take(C auto) {}

int main() { take<std::integral>(42); }
```

本机 Clang 23 能编译上面两个例子，较旧的编译器会报语法错误。

### 形参的名字（¶8）

¶8 模板形参里声明的类型名或模板名不经过名字查找，因为这里是在引入一个新名字。在模板声明的作用域内，类型模板形参的名字是一个 *typedef-name*，模板模板形参的名字是 *template-name*，概念模板形参的名字是 *concept-name*。

所以 `T` 可以像 typedef 一样使用，但不能写成 `struct T` 这样的详述类型说明符。

## 类型模板形参

### `class` 与 `typename`（¶7）

¶7 `template<class T>` 和 `template<typename T>` 完全等价。区别只在 `typename` 后面跟的是什么：跟一个简单名字时声明类型形参，跟一个限定名（如 `T::type`）时，整个形参是一个类型为 `T::type` 的常量形参。

```cpp run title="class-vs-typename.cpp" ok
struct S { using type = int; };

template<class T, typename T::type N>   // T 是类型形参，N 是常量形参
struct Q { static constexpr auto value = N; };

static_assert(Q<S, 3>::value == 3);
int main() {}
```

`class T` 永远声明类型形参，即使外层作用域里恰好有一个名叫 `T` 的类：

```cpp run title="class-T.cpp" ok
class T {};
int i;

template<class T, T i> void f(T t) {
    T t1 = i;         // 模板形参 T 和 i
    ::T t2 = ::T();   // 全局的类 T
    (void)t; (void)t1; (void)t2;
}

int main() { f<int, 3>(0); }
```

这里的 `f` 有一个名叫 `T` 的类型形参，而不是一个类型为 `class T`、没有名字的常量形参。

¶7 末尾还有两条限制：常量模板形参不能带存储类说明符（`template<static int N>` 非法），模板形参声明中不能定义新类型（`template<struct Q {} q>` 非法）。

### 用概念约束类型形参（¶9–¶10）

C++20 起，类型形参可以用一个**类型约束**（*type-constraint*）代替 `class`，写成 `template<std::integral T>`。类型约束就是一个概念名，可以带一部分模板实参。

```cpp run title="immediately-declared.cpp" ok
#include <concepts>
template<typename T> concept C1 = true;
template<typename... Ts> concept C2 = true;
template<typename T, typename U> concept C3 = true;

template<C1 T> struct s1;          // 约束 C1<T>
template<C1... T> struct s2;       // (C1<T> && ...)
template<C2... T> struct s3;       // (C2<T> && ...)，不是 C2<T...>
template<C3<int> T> struct s4;     // C3<T, int>
template<C3<int>... T> struct s5;  // (C3<T, int> && ...)

template<std::convertible_to<long> T>
struct s6;                         // std::convertible_to<T, long>
int main() {}
```

¶9 规则是：被约束的类型 `T` 总是插到概念的第一个实参位置。类型约束写成 `C<A1, ..., An>` 时得到 `C<T, A1, ..., An>`，写成 `C` 时得到 `C<T>`。如果 `T` 是一个包，结果再包成折叠表达式 `(C<T> && ...)`，对每个元素分别检查。这样得到的约束表达式叫做**立即声明约束**（[[g:immediately-declared-constraint]]）。

¶10 以类型约束开头的类型形参，就把这个立即声明约束加进模板的关联约束（[[temp.constr.decl]]）。

把 `T` 放在第一位，是为了让 `template<std::convertible_to<long> T>` 读起来像 "T convertible to long"。标准库的二元概念（`same_as`、`derived_from`、`convertible_to` 等）都遵循被约束的类型在前的约定。

`s3` 容易看错：`C2` 本身是变参概念，但 `C2... T` 仍然展开为对每个元素检查 `C2<T>`，而不是一次检查 `C2<T...>`。

¶9 还要求类型约束指名的概念是**类型概念**（type concept，[[temp.concept#7]]），即第一个形参是类型形参的概念：

```cpp title="value-concept.cpp" error
template<int N> concept Positive = N > 0;
template<Positive T> struct X {};   // error: Positive 不是类型概念
```

¶16 同样的机制也用于常量形参。常量形参的类型里如果有带约束的占位符，比如 `std::integral auto`，就对占位符推导出的类型施加立即声明约束：

```cpp title="constrained-auto.cpp" error
#include <concepts>
template<std::integral auto N> struct I {};
I<3>   a;     // OK
I<3.0> b;     // error: double 不满足 std::integral
```

### 类型约束的两条限制（¶4–¶5）

¶4 类型约束里的限定部分（*nested-name-specifier*）不能依赖外层模板形参。约束要在模板定义处参与规范化和包含关系比较（[[temp.constr.normal]]），必须在那时就能确定指的是哪个概念。

这条规则还消除了一处歧义。在 `template<T::C U>` 中，如果 `T` 是外层模板形参，`T::C` 不可能是类型约束，于是只能是常量形参的类型。[[temp.res.general#4]] 又把这个位置列为只能出现类型的语境，所以不用写 `typename`：

```cpp run title="dependent-nns.cpp" ok
namespace N { template<class T> concept C = true; }
template<N::C T> struct X {};      // OK：N 不依赖模板形参

template<class T>
struct W {
    template<T::C U>               // 类型为 typename T::C 的常量形参
    static constexpr auto g() { return U; }
};
struct S { using C = int; };
static_assert(W<S>::g<3>() == 3);
X<int> x;
int main() {}
```

¶5 概念模板形参不能带约束。概念本身不能受约束（[[temp.concept#4]]），作为形参的概念也一样：

```cpp title="constrained-concept-param.cpp" error
#include <concepts>
template<template<std::integral T> concept C>   // error: 违反 ¶5
struct X {};
```

截至写作时，Clang 23 接受这段代码，没有给出诊断。按标准它是非良构的。

## 常量模板形参的类型（¶11–¶15）

### 为什么要限制类型

常量模板形参的值是类型身份的一部分。`X<a>` 和 `X<b>` 是不是同一个类型，取决于 `a` 和 `b` 是否**模板实参等价**（template-argument-equivalent，[[temp.type#2]]）。这个比较必须满足几个条件：

1. 能在编译期完成，所以值必须能在常量求值中算出来；
2. 在每个翻译单元里结果都一样。链接器靠修饰后的符号名合并同一个特化，所以值必须能逐个成员编码进符号名；
3. 不依赖用户写的 `operator==`。否则不同翻译单元可能看到不同的 `==`，或者 `==` 根本不是等价关系，类型系统就无法自洽。

标准的做法是只允许能逐个成员比较的类型，比较时也只按成员逐个比较。

### 结构化类型（¶11–¶12）

¶11 常量模板形参的类型必须是下面之一（可以带 cv 限定）：

- ¶11.1 结构化类型；
- ¶11.2 含有占位符的类型，如 `auto`、`auto*`、`decltype(auto)`、`std::integral auto`（[[dcl.spec.auto]]）{{c++17}}；
- ¶11.3 推导类类型的占位符，即只写类模板名、由类模板实参推导决定具体类型，如 `template<fixed_string s>`（[[dcl.type.class.deduct]]）{{c++20}}。

形参的顶层 cv 限定会被忽略，`template<const int N>` 与 `template<int N>` 声明的是同一种形参。

¶12 **结构化类型**（[[g:structural-type]]）是以下之一：

- ¶12.1 标量类型：算术类型、枚举、指针、成员指针、`std::nullptr_t`，以及 C++26 的反射类型 `std::meta::info`；
- ¶12.2 左值引用类型；
- ¶12.3 满足下面两个条件的字面类类型（[[basic.types.general]]）：
    - ¶12.3.1 所有基类和非静态数据成员都是 public、非 mutable；
    - ¶12.3.2 所有基类和非静态数据成员的类型都是结构化类型，或者结构化类型的（可能多维的）数组。

要求成员 public，是因为逐成员比较的结果用户能直接观察到，不会暴露私有的实现细节。要求非 mutable，是因为模板形参对象是 `const` 的，值不能变。结构化类型不要求类型平凡，可以有用户写的构造函数；它与 `operator==` 也毫无关系。

```cpp title="structural.cpp" error
#include <array>
#include <string_view>
#include <utility>

struct P1 { int x, y; };                    // 结构化
struct P2 { int x; private: int y = 0; };   // 有 private 成员
struct P3 { mutable int x; };               // 有 mutable 成员
struct P4 { double d; int* p; int& r; };    // 结构化
struct P5 : P1 { float f[3]; };             // 结构化

template<P1 p> struct A1 {};
template<P2 p> struct A2 {};                // error: P2 不是结构化类型
template<P3 p> struct A3 {};                // error: P3 不是结构化类型
template<P4 p> struct A4 {};
template<P5 p> struct A5 {};

template<std::array<int, 3> a> struct B1 {};    // OK
template<std::pair<int, int> p> struct B2 {};   // libc++ 中 OK
template<std::string_view s> struct B3 {};      // error: 有 private 成员
```

Clang 在声明形参的地方就检查类型是否结构化，所以错误报在 `template<P2 p>` 这一行，而不是等到使用时。

!!! warning "标准库类型大多不保证是结构化类型"
    标准库只规定了类的公开接口，数据成员通常是私有的或者只用于说明。`std::array` 是聚合，实际实现中可以用作常量形参类型；本机 libc++ 的 `std::pair` 也可以。`std::tuple`、`std::optional`、`std::string_view`、`std::string` 在本机都被拒绝。写可移植的代码，最好自己定义一个成员全部 public 的聚合。

右值引用、`void` 不能作常量形参的类型。¶14 的注专门提醒了 `void`，`void*` 则没有问题，它是指针：

```cpp title="void-param.cpp" error
template<void v> class X;       // error
template<void* pv> class Y;     // OK
template<int&& r> class Z;      // error: 右值引用不是结构化类型
```

### 浮点、lambda 与联合体

C++20 起浮点数是合法的常量形参类型，因为它是标量。但浮点实参的等价要求两个值完全相同（identical），而不只是 `==` 成立。`0.0 == -0.0`，但它们的位模式不同，所以是不同的实参（[[temp.type#2]]）。

```cpp run title="float-nttp.cpp" ok
#include <type_traits>
template<double D> struct F {};
static_assert(!std::is_same_v<F<0.0>, F<-0.0>>);
static_assert(std::is_same_v<F<0.1 + 0.2>,
                             F<0.30000000000000004>>);

template<auto L> struct Lam {};
// 每个 lambda 有自己的闭包类型
static_assert(!std::is_same_v<Lam<[]{}>, Lam<[]{}>>);

union U { int i; float f; };
template<U u> struct UU {};
// 活跃成员不同，就是不同的实参
static_assert(!std::is_same_v<UU<U{.i = 0}>, UU<U{.f = 0}>>);
int main() {}
```

无捕获 lambda 的闭包类型是没有数据成员的字面类，因此是结构化类型。联合体只要所有成员 public、非 mutable、类型结构化，也是结构化类型。

### 数组和函数类型会调整为指针（¶15）

¶15 和函数形参一样，类型为"`T` 的数组"或函数类型 `T` 的常量形参会调整为"指向 `T` 的指针"：

```cpp run title="adjust.cpp" ok
template<int* a>   struct R {};
template<int b[5]> struct S {};   // 调整为 int*
int p;
R<&p> w;        // OK
S<&p> x;        // OK：形参已调整为指针
int v[5];
R<v> y;         // OK：实参做数组到指针转换
S<v> z;         // OK：两者都有
int main() {}
```

想传数组本身，就用数组的引用 `template<int (&arr)[5]>`，引用不会被调整。

## 模板形参对象（¶13）

<div class="compare" markdown="1">

```cpp error
template<int i>
void f() {
  i++;         // error: i 是 prvalue
  (void)&i;    // error: 不能取地址
}
```

```cpp ok
struct A { int v; };
template<A a>
void g() {
  (void)&a;    // OK：a 是左值
  const A& r = a;   // 绑定到对象本身
  (void)r;
}
```

</div>

¶13 类类型的常量形参在模板里指称一个真实存在的对象，叫做**模板形参对象**（[[g:template-parameter-object]]）。它具有静态存储期，类型是 `const T`。没有两个模板形参对象是模板实参等价的，也就是说，每个值在整个程序中恰好对应一个对象。

注 3 说明了不同类型的形参在表达式里是什么值类别：

| 形参的类型 | 在模板中使用它得到 | 能否取地址 |
|---|---|---|
| 非类类型、非引用（`int i`） | prvalue | 不能 |
| 类类型 `T`（`A a`） | 类型为 `const T` 的左值，即模板形参对象 | 能 |
| 引用类型（`const X& x`） | 引用所指对象的左值 | 能 |

所以 `int& ri = i;` 是错误的，`i` 是 prvalue，非 const 左值引用不能绑定；`const int& cri = i;` 可以，它绑定到一个临时对象。

每个值对应一个对象，这一点可以观察到：

```cpp run title="param-object-identity.cpp" ok
struct A { int v; };

template<A a> constexpr const A* addr() { return &a; }

static_assert(addr<A{1}>() == addr<A{1}>());   // 同一个对象
static_assert(addr<A{1}>() != addr<A{2}>());
int main() {}
```

字符串字面量正好相反：两个内容相同的字符串字面量是不是同一个对象，标准不作规定（[[lex.string]]）。这是字符串字面量不能用作指针类型常量实参的原因之一（[[temp.arg.nontype#6]]）。

注 2 补充，C++26 的反射设施（如 `std::define_static_array`，[[meta.define.static]]）可以创建数组类型的模板形参对象。常量模板形参的名字永远不会指称这种对象，而且它的地址可能与别的存活对象重合（[[intro.object]]）。

## 默认模板实参（¶17–¶21）

### 写在哪里（¶17）

¶17 **默认模板实参**（default template argument）是模板形参中 `=` 后面的实参。它可以写在模板声明中，但有几处不能写：

```cpp title="default-where.cpp" error
template<class... Ts = int> struct P;    // error: 形参包不能有默认实参

template<class T> struct A {
    template<class U> void f();
};
template<class T> template<class U = int>
void A<T>::f() {}                        // error: 类外的成员定义

template<class T> struct C {
    template<class U = int>
    friend void h(U);                    // error: 必须是定义
    template<class U = int>
    friend void k(U) {}                  // OK
};
```

完整的规则是：

1. 形参包不能有默认实参；
2. 类模板成员在类外定义时，模板形参列表里不能写默认实参，它只能写在类内的声明上；
3. 友元类模板声明不能写默认实参；
4. 友元函数模板声明写了默认模板实参时，这个声明必须是定义，而且不能有其他声明与它互相可达。

后两条是为了让一个模板在任何地方看到的默认实参都一样。友元声明写在类里，声明的却是外层命名空间的实体。如果允许它添加默认实参，一个模板有没有默认实参就要取决于哪个类被实例化过。

截至写作时，Clang 23 不诊断友元类模板上的默认实参（第 3 条），也不诊断第 4 条的后半部分。

### 跨声明合并（¶18）

¶18 同一个模板的多个声明中的默认实参会合并起来，方式与函数的默认实参相同（[[dcl.fct.default]]）：

```cpp run title="merge.cpp" ok
#include <type_traits>
template<class T1, class T2 = int> class A;
template<class T1 = int, class T2> class A;   // 合并后 <int, int>
template<class T1, class T2> class A {};

static_assert(std::is_same_v<A<>, A<int, int>>);
int main() {}
```

第二个声明中 `T1` 有默认实参而 `T2` 没写，看似违反下面的顺序规则，但合并之后 `T2` 已经有了默认实参，所以合法。同一个形参的默认实参只能给一次，即使两次的值相同。

### 顺序：类模板和函数模板不同（¶19）

<div class="compare" markdown="1">

```cpp error
// 类模板：默认实参之后
// 必须都有默认实参
template<class T = int, class U>
struct S;  // error
```

```cpp ok
// 函数模板：U 可以推导
template<class T = int, class U>
void f(U) {}

int main() { f(1.0); }  // T=int
```

</div>

¶19 类模板的实参只能按位置写出，`S<X>` 中的 `X` 一定对应第一个形参。如果默认实参后面还有没有默认实参的形参，那个形参就永远拿不到实参。函数模板的实参主要靠推导，位置无关紧要，所以没有这条限制。完整的规则：

| 模板种类 | 有默认实参的形参之后 | 形参包的位置 |
|---|---|---|
| 类模板、变量模板、别名模板 | 后面每个形参都要有默认实参，或者是形参包 | 主模板中，形参包必须是最后一个 |
| 函数模板 | 没有限制 | 形参包后面的形参必须能从函数形参推导，或有默认实参 |
| 推导指引模板 | 没有限制 | 没有默认实参的形参必须能从推导指引的形参推导 |

```cpp title="default-order.cpp" error
template<class R = void, class... Args, class F>
R invoke_like(F, Args...);                   // OK：Args、F 都能推导

template<class... T, class... U> void g() {} // error: U 无法推导
template<class... T, class U> void h() {}    // error: 同上
```

截至写作时，Clang 23 不诊断 `g` 和 `h` 的声明，要到调用时才因推导失败报错。标准例 8 明确把它们标为非良构。

形参包必须在最后，只针对主模板。部分特化的形参都是从主模板的实参中推导出来的，形参包可以放在任何位置：

```cpp run title="pack-not-last.cpp" ok
#include <type_traits>
template<class... Ts> struct List {};
template<class L, class T> struct Append;

template<class... Ts, class T>        // 部分特化：包不在最后，OK
struct Append<List<Ts...>, T> { using type = List<Ts..., T>; };

static_assert(std::is_same_v<Append<List<int>, char>::type,
                             List<int, char>>);
int main() {}
```

C++98 的函数模板根本不能有默认模板实参，C++11 起才允许（[[CWG226]]）。`template<class T, class = std::enable_if_t<...>>` 这种借默认模板实参实现 SFINAE 的写法就依赖它。

### 默认实参中的 `>`（¶20）

¶20 常量形参的默认实参里，第一个不在括号内的 `>` 会被当成形参列表的结束：

```cpp title="gt-default.cpp" error
template<int i = 3 > 4 > class X {};      // error: 语法错误
template<int i = (3 > 4) > class Y {};    // OK
```

模板实参列表也有同样的规则（[[temp.names#8]]）。在尖括号里使用 `>` 运算符，一律加括号。

### 模板模板形参的形参的默认实参（¶21）

¶21 模板模板形参自己的形参也可以有默认实参，但它只在这一个声明里生效，不像普通默认实参那样跨声明合并：

```cpp title="tt-default.cpp" error
template<template<class TT = float> class T> struct A {
    void f();
    void g();
};
template<template<class TT> class T> void A<T>::f() {
    T<> t;            // error: 这里的 TT 没有默认实参
}
template<template<class TT = char> class T> void A<T>::g() {
    T<> t;            // OK：T<char>
}
```

¶21 最后一句 {{c++26}}：模板模板形参的约束不能依赖同一列表里的概念模板形参，这种约束叫做**概念依赖约束**（concept-dependent constraint，[[temp.constr.concept]]）：

```cpp title="tt-concept-dependent.cpp" error
template<
    template<typename> concept C,
    template<C> class TT          // error: C 形成概念依赖约束
>
struct A {};
```

模板模板实参的匹配要比较约束的包含关系（[[temp.arg.template#4]]），而在 `C` 确定之前，依赖它的约束无法规范化，也就无法比较。截至写作时，Clang 23 接受上面的代码，没有诊断。

## 形参包（¶6）

¶6 名字前面带省略号的模板形参声明一个**模板形参包**（template parameter pack，[[temp.variadic]]），它可以对应零个或多个实参：`class... Ts`、`int... Ns`、`auto... Vs`、`template<class> class... TTs`、`std::integral... Ts`。

形参包本身可以同时是一个包展开，即它的声明里用到了另一个尚未展开的包：

```cpp title="pack-expansion-param.cpp" error
template<class... T>
struct value_holder {
    template<T... Values> struct apply {};  // OK：Values 展开外层的 T
};
value_holder<int, char>::apply<1, 'a'> ok;  // 形参依次是 int、char

template<class... T, T... Values>           // error: 展开了同一列表中的 T
struct static_array;
```

`apply` 的形参个数和类型由外层的 `T` 决定，而外层的 `T` 在 `value_holder<int, char>` 中已经确定。`static_array` 则不同：`T` 和 `Values` 在同一个列表里，确定 `T` 有几个元素和确定 `Values` 有几个形参互相依赖，所以标准禁止。

同样的规则适用于形参列表里含有未展开包的模板模板形参包，以及类型约束里含有未展开包的类型形参包。

## 实现视角

!!! impl "常量模板实参怎样进入符号名"
    Itanium ABI 把常量模板实参编码进修饰名。本机 Clang 23 的结果：
    
    - `fi<42>()` 修饰为 `_Z2fiILi42EEvv`，整数编码为 `Li42E`；
    - `fd<1.0>()` 中的实参编码为 `Ld3ff0000000000000E`，即 double 的位模式。所以 `0.0` 和 `-0.0` 是不同的实参；
    - `addr<A{1}>()` 修饰为 `_Z4addrIXtl1ALi1EEEEPKS0_v`，类类型的值按成员逐个编码，`tl` 表示花括号初始化。
    
    模板形参对象 `A{1}` 本身被输出为一个名为 `_ZTAXtl1ALi1EEE` 的只读常量，在各目标文件中以可合并的方式出现，链接后只剩一份。¶13 要求的每个值一个对象就是这样实现的。

## 历史与演进

!!! history
    - C++98 已有类型形参、类模板模板形参，以及整数、枚举、指针、引用、成员指针类型的非类型形参，但函数模板不能有默认模板实参。
    - C++11 加入了模板形参包，函数模板可以有默认模板实参。
    - C++17 加入了 `template<auto N>`（[[P0127R2]]）。
    - C++20 允许类类型的常量形参（[[P0732R2]]）。这个提案最初要求类有 `= default` 的 `operator==`，后来 [[P1907R1]] 改成了现在与 `==` 无关、只看成员的结构化类型定义，并允许浮点类型。同一版本加入了类型约束。
    - C++26 加入了变量模板模板形参和概念模板形参（[[P2841]]），非类型模板形参改称常量模板形参。

## 常见误解

!!! pitfall "C++20 可以写 `template<std::string s>`"
    不行。`std::string` 在 C++20 中是字面类型，但它的成员是私有的，所以不是结构化类型。要传字符串，就写一个成员全部 public 的 `fixed_string` 聚合，见 [[temp.arg.nontype]]。

!!! pitfall "`C... Ts` 等于 `C<Ts...>`"
    `C... Ts` 是对每个元素分别检查，等于 `(C<Ts> && ...)`（¶9）。

!!! pitfall "`template<const int N>` 和 `template<int N>` 是不同的模板"
    顶层 cv 限定会被忽略（¶11）。`template<int N> void h();` 与 `template<const int N> void h() {}` 是同一个函数模板的声明和定义。

## 思考题

!!! question "思考题 1"
    下列哪些类型可以作为常量模板形参的类型？

    ```cpp
    struct A { int x; constexpr A(int v) : x(v) {} };              // (a)
    struct B { int x; bool operator==(const B&) const = delete; }; // (b)
    struct C { const int& r; };                                    // (c)
    struct D { int&& r; };                                         // (d)
    struct E { std::array<float, 2> a; };                          // (e)
    ```

<details markdown="1">
<summary>答案</summary>

- (a) 可以。它是字面类，成员是 public 的；用户写的构造函数不影响结构化。
- (b) 可以。结构化类型与 `operator==` 无关，删除 `==` 也没有影响。
- (c) 可以。左值引用是结构化类型，但实参里的引用不能绑定到临时对象（[[temp.arg.nontype#6]]）。
- (d) 不可以。右值引用不是结构化类型。
- (e) 实际可以：`std::array` 的成员在实现中是 public 的，`float` 是标量。标准本身不保证这一点。
</details>

!!! question "思考题 2"
    `template<auto... Vs> struct V {};` 中 `V<1, 'a', nullptr>` 合法吗？各个 `Vs` 的类型是什么？

<details markdown="1">
<summary>答案</summary>

合法。`auto...` 形参包的每个元素各自推导类型（[[temp.arg.nontype#1]] 为每个实参虚构一个声明 `auto x = E;`），分别是 `int`、`char`、`std::nullptr_t`。如果要求所有元素类型相同，就写 `template<class T, T... Vs>`。
</details>

<details class="fine" markdown="1"><summary>其余条文</summary>

¶1 给出五种模板形参的文法，分别是 *type-parameter*、*parameter-declaration*、*type-tt-parameter*、*variable-tt-parameter* 和 *concept-tt-parameter*。几个细节：类型模板模板形参的默认实参可以写成 `= N::template X`；概念模板形参的开头直接写 `template<...>`，不是一般的 *template-head*，所以不能带 *requires-clause*。

类型约束的组成名字（component names）是它的概念名和限定部分中的名字，其他条款用这个说法来规定查找。

注 1：模板模板形参的形参列表后面的 `>` 可以来自 `>>` 的拆分（[[temp.names#8]]），例如 `template<template<class = A<int>> class TT>` 中的 `>>` 不必拆开写。

</details>
