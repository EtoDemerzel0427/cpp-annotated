---
title: 从类型推导模板实参
summary: 所有推导场合共用的算法：把用模板形参写成的类型 P 与实际类型 A 按结构对齐，拆开指针、引用、数组、函数、成员指针和模板特化来求模板实参；哪些位置是非推导语境；包怎样推导；常量模板形参的类型怎样推导。
status: done
covers: temp.deduct.type
papers: P0887R1
related: temp.deduct, temp.deduct.call, temp.deduct.partial, temp.deduct.decl, temp.variadic, temp.arg.nontype, temp.spec.partial.match, topics/type-deduction
tags: 模板, 模板实参推导, 非推导语境, 包
updated: 2026-10-19
---

!!! tldr
    - 推导就是结构匹配：把用模板形参写成的类型 `P` 和实际类型 `A` 对齐，只能拆开指针、引用、数组、函数、成员指针、模板特化这些类型构造器。
    - 每一对 `P`/`A` 独立推导再合并；结果冲突、有多个解、或者有模板形参没有确定，推导就失败。推导不考虑隐式转换。
    - 限定名的前缀（`typename A<T>::type`）、`decltype`、含模板形参的表达式（`N+1`）等位置是非推导语境：不从这里求值，只用别处求得的值代入。`std::type_identity_t<T>` 就是有意制造的非推导语境。
    - 包可以推导出零个或多个实参，但不在末尾的包不推导。
    - 推导常量模板形参时，它的类型必须与实际模板形参的类型相同：`template<int N> void f(std::array<int, N>)` 推不出来，要写 `std::size_t N` 或 `auto N`。

## P 与 A（¶1–¶2）

```cpp run ok title="forms.cpp"
#include <cstddef>
#include <type_traits>

template<class R, class... As> constexpr auto arity(R(*)(As...)) { return sizeof...(As); }
template<class C, class M> constexpr bool is_mem_obj(M C::*) { return !std::is_function_v<M>; }
template<template<class...> class TT, class... Ts> constexpr auto count(const TT<Ts...>&) { return sizeof...(Ts); }
template<class T, std::size_t N> constexpr auto len(T(&)[N]) { return N; }

struct S { int x; void f(); };
template<class...> struct List { };
int fn(int, char, double);
int arr[7];

static_assert(arity(&fn) == 3);                // 函数类型：R = int，As = int, char, double
static_assert(is_mem_obj(&S::x));              // 成员指针：C = S，M = int
static_assert(!is_mem_obj(&S::f));             // M = void()
static_assert(count(List<int, char>{}) == 2);  // 模板特化：TT = List
static_assert(len(arr) == 7);                  // 数组：T = int，N = 7
int main() { }
```

每个调用里，编译器都把形参类型（如 `R(*)(As...)`）和实参类型（`int(*)(int, char, double)`）一层层对齐，从对应位置读出 `R`、`As` 的值。

¶1 推导发生在很多场合：函数调用（[[temp.deduct.call]]）、取函数模板的地址（[[temp.deduct.funcaddr]]）、转换函数模板（[[temp.deduct.conv]]）、偏序（[[temp.deduct.partial]]）、从函数声明推导（[[temp.deduct.decl]]）、部分特化的匹配（[[temp.spec.partial.match]]）。每种场合最后都归结为本节的问题：给定一个用模板形参写成的类型 `P` 和一个实际类型 `A`，求模板实参（类型形参求一个类型，常量形参求一个值，模板模板形参求一个模板），使 `P` 代入后的类型（称为推导出的 `A`）与 `A` 兼容。

¶2 有时只有一对 `P`/`A`，有时有一组，例如函数的每个形参各一对。每一对独立推导，然后合并。下面任一情形推导失败：某一对无法推导；某一对有不止一组解；不同的对推出不同的值；某个模板实参既没有推导出来，也没有显式指定。

```cpp error
template<class T> void f(T x, T y) { }
struct A { };
struct B : A { };
void g(A a, B b) {
    f(a, b);    // error: T 推导为 A 和 B
    f(b, a);    // error: 同上
    f(a, a);    // OK：T = A
    f(b, b);    // OK：T = B
}
```

虽然 `B` 能转换成 `A`，但推导不考虑转换（[[temp.deduct.call#4]] 只允许少数几种调整），所以 `f(a, b)` 失败。

一对 `P`/`A` 也可能同时推导几个形参，并且自相矛盾（¶7 例 3）：

```cpp error
template <class T, class U> void f(T (*)(T, U, U));
int  g1(int, float, float);
char g2(int, float, float);
int  g3(int, char, float);
void r() {
    f(g1);    // OK：T = int，U = float
    f(g2);    // error: T 从返回类型推导为 char，从形参推导为 int
    f(g3);    // error: U 推导为 char 和 float
}
```

## 能拆开的形式（¶3、¶8–¶12）

¶3 类型 `P` 可以由别的类型、模板和常量值组成：函数类型包括各形参类型、返回类型和异常说明；成员指针类型包括类类型和成员类型；类模板特化 `A<int>` 包括它的模板实参；数组类型包括元素类型和界。

¶8 只有当 `P` 和 `A` 是下列形式之一时，才能推导类型形参 `T`、常量形参 `i`、表示类模板或别名模板的模板模板形参 `TT`、表示变量模板或概念的模板模板形参 `VV`：

```text
cv(opt) T
T*
T&
T&&
T(opt)[i(opt)]
T(opt)(T(opt)) noexcept(i(opt))
T(opt) T(opt)::*
TT(opt)<T>
TT(opt)<i>
TT(opt)<TT>
TT(opt)<VV>
TT(opt)<>
```

带 `(opt)` 的位置可以继续套用这些形式，也可以是非推导语境，或者是 `P` 和 `A` 里相同的非依赖类型或相同的常量值（¶8.1–¶8.4）。`<T>` 表示至少有一个实参含 `T` 的模板实参列表，`<>` 表示一个都不含。

¶11 这些形式可以像 `T` 一样层层组合，例如 `X<int> (*)(char[6])` 是 `type (*)(T)` 的形式，其中 `type` 是 `X<int>`，`T` 是 `char[6]`。¶12 除此之外，不能从其他构造推导模板实参。

换句话说，推导只会拆开类型构造器。别名不在其中，它在推导之前就已经展开成目标类型。

¶7 例 3 还演示了从异常说明推导。C++17 起异常说明是函数类型的一部分，所以 `noexcept(E)` 里的 `E` 可以推导：

```cpp error
template<bool E> void f1(void (*)() noexcept(E));
template<bool> struct A { };
template<bool B> void f2(void (*)(A<B>) noexcept(B));

void g1();
void g2() noexcept;
void g3(A<true>);

void h() {
    f1(g1);   // OK：E = false
    f1(g2);   // OK：E = true
    f2(g3);   // error: B 从 A<true> 推导为 true，从 noexcept 推导为 false
}
```

## 非推导语境（¶4–¶6）

```cpp run ok title="type_identity.cpp"
#include <type_traits>
template<class T> T vmax(T a, std::type_identity_t<T> b) { return a < b ? b : a; }

auto r = vmax(1.5, 2);    // T 只从第一个实参推导为 double；2 转换为 double
static_assert(std::is_same_v<decltype(r), double>);

int main() { }
```

`std::type_identity_t<T>` 就是 `typename std::type_identity<T>::type`（C++20，[[P0887R1]]）。`T` 出现在 `::` 前面，这个位置不参与推导。`T` 由第一个实参定下来后代入，第二个形参就成了普通的 `double` 形参，可以接受任何能隐式转换的实参。没有它，`vmax(1.5, 2)` 会因 `T` 推出 `double` 和 `int` 两个值而失败。

¶4 组成 `P` 的部分大多参与推导：可以用来确定模板实参，确定的值必须和别处一致。但在某些位置，值不参与推导，而是使用别处推导出或显式指定的值，这些位置叫**非推导语境**（[[g:non-deduced-context|non-deduced context]]）。一个模板形参如果只出现在非推导语境里，又没有显式指定，推导失败。

¶5 非推导语境有：

| ¶ | 语境 | 例子（`T`、`N` 在这里不推导） |
|---|---|---|
| 5.1 | 限定名中 `::` 前面的部分（*nested-name-specifier*） | `typename A<T>::type`、`std::type_identity_t<T>` |
| 5.2 | 包索引 {{c++26}} | `Ts...[0]` |
| 5.3 | 类型约束 | `C<T> auto` 中的 `C<T>` |
| 5.4 | `decltype` 的操作数 | `decltype(T{} + 1)` |
| 5.5 | 拼接说明符里的常量表达式 {{c++26}} | `[: refl :]` 中的 `refl` |
| 5.6 | 子表达式引用了模板形参的常量模板实参或数组界 | `A<N+1>`、`int[N*2]` |
| 5.7 | 这次调用用了默认实参的形参 | `f(T = 5)` 以 `f()` 调用 |
| 5.8 | 实参是重载集，并且有多个类型不同的函数匹配、没有函数匹配，或集合里有函数模板 | `f(g)`，`g` 有重载 |
| 5.9 | 实参是花括号初始化列表，形参又不是能从列表推导的类型 | `template<class T> void g(T); g({1,2,3});` |
| 5.10 | 不在形参列表末尾的函数形参包 | `template<class... Ts> void f(Ts..., int)` |

这些位置不推导，是因为一般无法反推。从 `typename A<T>::type` 等于 `int` 反推 `T`，相当于给任意类型函数求逆，`A` 还可能被特化成任何东西。`N+1 == 5` 能解出 `N`，但 `N*N`、`f(N)` 就不行，标准干脆规定只要模板形参出现在子表达式里就不推导。不在末尾的包则不知道该吃掉几个实参。

非推导语境里的形参并不是被忽略了：推导完成后它照样要代入，代入后的类型必须有效，实参也必须能转换过去。

```cpp error
template <int i> class A { };
template <int i> void g(A<i+1>);
template <int i> void f(A<i>, A<i+1>);

void k() {
    A<1> a1;
    A<2> a2;
    g(a1);          // error: i+1 不推导，i 无从确定
    g<0>(a1);       // OK
    f(a1, a2);      // OK：i 从 A<i> 推导为 1，A<i+1> 代入后是 A<2>，一致
}
```

¶6 一个类型名只要以含非推导语境的方式写出，组成它的所有类型都不推导：`A<T>::B<T2>` 中 `T` 和 `T2` 都不推导，`A<I+J>::X<T>` 中 `I`、`J`、`T` 都不推导。但一个复合类型可以部分推导、部分不推导：`void f(typename A<T>::B, A<T>)` 中第一个形参里的 `T` 不推导，第二个里的推导。

¶4 的注 1 补充：如果 `P` 的推导语境里根本不含模板形参，就不对这一对做推导，`P` 和 `A` 也不必形式相同，只要实参能转换过去即可。

### 数组界

```cpp error
template<int i> void f1(int a[10][i]);
template<int i> void f2(int a[i][20]);
template<int i> void f3(int (&a)[i][20]);

void g() {
    int v[10][20];
    f1(v);          // OK：i 推导为 20
    f1<20>(v);      // OK
    f2(v);          // error: 无法推导 i
    f2<10>(v);      // OK
    f3(v);          // OK：i 推导为 10
}
```

¶17 的注 5 解释了这个例子：除了引用和指针，最外层的数组界不属于函数形参的类型。`int a[i][20]` 被调整成 `int (*a)[20]`，`i` 消失了，自然推不出来；`f3` 用引用保住了它。

## 模板实参列表和函数形参列表中的包（¶9–¶10、¶24）

```cpp ok
template<class> struct X { };
template<class R, class... ArgTypes> struct X<R(int, ArgTypes...)> { };
template<class... Types> struct Y { };
template<class T, class... Types> struct Y<T, Types&...> { };

template<class... Types> int f(void (*)(Types...));
void g(int, float);

X<int> x1;                      // 主模板
X<int(int, float, double)> x2;  // 部分特化；ArgTypes = float, double
X<int(float, int)> x3;          // 主模板（第一个形参不是 int）
Y<> y1;                         // 主模板；Types 为空
Y<int&, float&, double&> y2;    // 部分特化；T = int&，Types = float, double
Y<int, float, double> y3;       // 主模板；float、double 不是引用
int fv = f(g);                  // OK；Types = int, float
```

¶24 的注 8 指出，包可以推导出零个或多个实参。

¶9 `P` 含模板实参列表时，把它的每个实参 `Pi` 和 `A` 的对应实参 `Ai` 比较。`Pi` 是包展开时，用它的模式依次和 `A` 剩下的每个实参比较，每次比较确定包的下一个元素。如果包展开不是列表的最后一个实参，整个模板实参列表都是非推导语境。

¶10 `P` 含函数形参类型列表时，规则相同：形参包的类型依次和 `A` 剩下的每个形参类型比较。

¶9 和 ¶10 各有两条只在偏序（[[temp.deduct.partial]]）中用到的规则。偏序时如果 `Ai` 原本是包：`P` 中没有和它对应的东西，就忽略它（¶9.1、¶10.1）；否则如果 `Pi` 不是包，推导失败（¶9.2、¶10.2）。它们让带包的特化能和不带包的特化比较：

```cpp ok
template<class T1, class... Z> class S;                                 // #1
template<class T1, class... Z> class S<T1, const Z&...> { };            // #2
template<class T1, class T2>   class S<T1, const T2&> { };              // #3
S<int, const int&> s;           // #2 和 #3 都匹配；#3 更特殊

template<class T, class... U> void f(T*, U...) { }   // #4
template<class T>             void f(T) { }          // #5
template void f(int*);                               // 选 #4：T* 比 T 更特殊
```

### 函数类型里的转发引用（¶10）

```cpp run ok title="spec_fwd.cpp"
#include <cstdio>
template <class T> void f(T&&)  { std::puts("primary"); }
template <> void f(int&)  { std::puts("#1 f<int&>"); }    // T&& 对 int&：调整为 T，T = int&
template <> void f(int&&) { std::puts("#2 f<int>"); }     // T&& 对 int&&：T = int

int main() {
    int i = 0;
    f(i);    // 调用 #1
    f(0);    // 调用 #2
}
```

¶10 在两种场合对函数类型做一个调整：取函数模板地址时（[[temp.deduct.funcaddr]]），以及从函数声明推导时（[[temp.deduct.decl]]，例如显式特化）。如果顶层形参 `Pi` 是**转发引用**（无 cv 的 `T&&`，`T` 是函数模板的类型形参），而 `Ai` 是左值引用，就把 `Pi` 改成 `T`，于是 `T` 推导为 `X&`。没有这个调整，`T&&` 和 `int&` 按结构对不上，就无法为左值那个特化写显式特化。

## 常量模板形参的类型（¶13–¶16、¶20）

常量模板形参的类型如果依赖于别的模板形参，推出它的值时也会推出它的类型。

¶13 值从一个表达式推出时，类型从值的类型推出：

```cpp ok
template<long n> struct A { };

template<typename T> struct C;
template<typename T, T n> struct C<A<n>> { using Q = T; };

using R = long;
using R = C<A<2>>::Q;     // OK：T 推导为 long
```

`T` 是 `long` 而不是 `int`：`A<2>` 里的 `2` 已经转换成 `A` 的形参类型 `long`。

¶14 数组类型 `T[N]` 中 `N` 的类型是 `std::size_t`；¶15 函数类型的 `noexcept(B)` 中 `B` 的类型是 `bool`：

```cpp ok
#include <cstddef>
template<typename T> struct S;
template<typename T, T n> struct S<int[n]> { using Q = T; };
using V = S<int[42]>::Q;  // T 推导为 std::size_t
static_assert(sizeof(V) == sizeof(std::size_t));

template<bool> struct A { };
template<auto> struct B;
template<auto X, void (*F)() noexcept(X)> struct B<F> { A<X> ax; };
void f_nothrow() noexcept;
B<f_nothrow> bn;          // X 的类型推导为 bool
```

¶16 的例子用函数调用演示同一件事：`template<class T, T i> void f(int (&a)[i]);` 以 `int v[10]` 调用时，`T` 是 `std::size_t`。¶2 末句规定，类型形参只有在别处推不出时，才从数组界推导。

¶20 `P` 含 `<i>` 时，`i` 的类型必须与 `A` 所属模板中对应形参的类型完全相同（顶层 cv 除外），否则推导失败：

```cpp error
template<int i> class A { };
template<short s> void f(A<s>);
void k1() {
    A<1> a;
    f(a);           // error: int 与 short 不同
    f<1>(a);        // OK：显式指定，不推导
}

template<const short cs> class B { };
template<short s> void g(B<s>);
void k2() {
    B<1> b;
    g(b);           // OK：模板形参类型上的 cv 被忽略
}
```

如果 `i` 的类型含占位符（`auto`、`decltype(auto)`），就把对应的形参当作初始化表达式来推导这个占位符：

```cpp error
template<int> struct D;
template<auto x> void f(D<x> *);
void g(D<0LL> *ap) {
    f(ap);          // OK：D 的形参是 int，x 推导为 int 值
}

template<int &> struct E;
template<auto x> void f(E<x> *);
int v;
void g(E<v> *bp) {
    f(bp);          // error: auto 推导出 int，与形参类型 int& 不同
}

template<const int &> struct F;
template<decltype(auto) x> void f(F<x> *);
int i;
void g(F<i> *ap) {
    f(ap);          // OK：decltype(auto) 推导出 const int&
}
```

¶20 还规定：`P` 含 `[i]` 而 `i` 不是整型，或含 `noexcept(i)` 而 `i` 不是 `bool`，推导失败。

!!! impl "Clang 的偏差"
    标准例 13 的最后一段是：

    ```cpp
    template <decltype(auto) q> struct G;
    template <auto x> long *f(G<x> *);              // #1
    template <decltype(auto) x> short *f(G<x> *);   // #2

    const int j = 0;
    short *g(G<(j)> *ap) { return f(ap); }   // q 的类型是 const int&，只有 #2 匹配
    long *g(G<j> *ap) { return f(ap); }      // q 的类型是 int，#1 更特殊
    ```

    本机 Clang 23 对最后一个调用报告二义。按标准应选 #1。

## 函数实参、默认实参、模板模板形参（¶21–¶23）

¶21 模板实参可以从函数类型、函数指针类型、成员函数指针类型推导。实参是重载集时，按 ¶5.8 处理：

```cpp error
template<class T> void f(void(*)(T, int));
template<class T> void foo(T, int);
void g(int, int);
void g(char, int);
void h(int, int, int);
void h(char, int);

int m() {
    f(&g);      // error: 两个 g 都匹配，T 不同
    f(&h);      // OK：只有 void h(char, int) 匹配，T = char
    f(&foo);    // error: 重载集里有模板
    return 0;
}
```

前后两个错误中，这个形参都成了非推导语境，`T` 又没有别处可推，所以报的是没有匹配的函数。

¶22 类型形参不能从默认实参的类型推导：

```cpp error
template <class T> void f(T = 5, T = 7);
void g() {
    f(1);           // OK：f<int>(1, 7)，第二个形参用了默认实参，不参与推导
    f();            // error: 无法推导 T
    f<int>();       // OK：f<int>(5, 7)
}
```

¶23 模板模板形参从实参类型中的类模板特化推导：

```cpp ok
template <template <class T> class X> struct A { };
template <template <class T> class X> void f(A<X>) { }
template<class T> struct B { };
A<B> ab;
void use() { f(ab); }      // X 推导为 B
```

## 常见误解

!!! pitfall "以为别名模板总能推导"
    `template<class T> using Vec = std::vector<T>;` 之后，`f(Vec<T>)` 等价于 `f(std::vector<T>)`，能推导。但 `template<class T> using Id = typename std::type_identity<T>::type;` 展开后 `T` 落在限定名里，`f(Id<T>)` 就推不出来。推导看的是展开后的类型。

!!! pitfall "想从迭代器推出容器"
    `template<class C> void f(typename C::iterator)` 无法从迭代器推出 `C`（¶5.1）。所以标准算法直接以迭代器类型为模板形参：`template<class It> void sort(It, It)`。

## 思考题

!!! question "思考题 1"
    ```cpp
    template<class T> struct Box { };
    template<class T> void f(Box<T>, typename Box<T>::value_type);
    f(Box<int>{}, 3);
    ```
    能编译吗？

<details markdown="1">
<summary>答案</summary>

不能（假设没有别的候选）。`T` 从第一个形参推导为 `int`，第二个形参里的 `T` 是非推导语境。推导完成后代入，`Box<int>::value_type` 不存在，函数类型无效，推导失败，模板退出候选集，报告没有匹配的函数。
</details>

!!! question "思考题 2"
    为什么 `template<int N> void f(std::array<int, N>)` 对 `std::array<int, 3>` 推导失败？

<details markdown="1">
<summary>答案</summary>

按 ¶20，`N` 的类型必须和 `std::array` 第二个模板形参的类型相同。那个形参的类型是 `std::size_t`，`N` 是 `int`，推导失败。写 `std::size_t N` 或 `auto N` 都可以，后者推导出 `std::size_t`。
</details>

<details class="fine" markdown="1"><summary>其余条文</summary>

¶8 注 3：某个类型符合上述形式，但不含任何 `T`、`i`、`TT`，就无法推导。

¶19 注 7 再次强调：只出现在非推导语境中的模板形参不参与推导，例如 `deduce<77>(a.xm, 62, b.ym)` 中 `T` 从第二个实参推出，`i` 由显式实参给出。

¶20 的脚注：`bool` 类型的形参虽然可以从数组界推导，但结果总是 `true`，因为数组界不为零。

</details>
