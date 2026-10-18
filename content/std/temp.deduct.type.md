---
title: 从类型推导模板实参
summary: 所有推导语境共用的核心算法：把用模板形参写成的类型 P 与实际类型 A 结构匹配。可推导的形式（T*、T&、T[i]、函数类型、成员指针、TT<T>、TT<i>……）、各 P/A 对独立推导再合并、完整的非推导语境列表（限定名的前缀、decltype、含形参的表达式、包索引……）、包的推导、常量模板形参的类型推导、数组界的类型是 size_t。
status: done
covers: temp.deduct.type
papers: P0887R1
related: temp.deduct, temp.deduct.call, temp.deduct.partial, temp.deduct.decl, temp.variadic, temp.arg.nontype, temp.spec.partial.match, topics/type-deduction
tags: 模板, 模板实参推导, 非推导语境, 包
updated: 2026-10-18
---

[[temp.deduct.type]] 是模板实参推导的**引擎**。无论是从函数调用（[[temp.deduct.call]]）、取地址（[[temp.deduct.funcaddr]]）、转换函数（[[temp.deduct.conv]]）、偏序（[[temp.deduct.partial]]）、函数声明（[[temp.deduct.decl]]），还是**部分特化的匹配**（[[temp.spec.partial.match]]），最终都归结为本节的问题：

> 给定一个用模板形参写成的类型 `P`，和一个实际类型 `A`，求模板实参，使 `P` 代入后与 `A` "兼容"。

它本质上是一个**结构化模式匹配**（类似函数式语言中的 unification，但只单向：只有 `P` 含变量）。理解这一节，就理解了"什么能推导、什么不能"的全部边界。

## 基本概念：P、A、推导出的 A（¶1–¶2）

¶1 在每种推导语境中，都是把一个用模板形参表示的类型 `P`，与一个实际类型 `A` 比较，求出模板实参值（类型形参求类型、常量形参求值、模板模板形参求模板），使 `P` 代入后（称为**推导出的 A**，deduced A）与 `A` 兼容。

¶2 有时只有一对 `P`/`A`，有时有一组。每一对**独立**推导，然后**合并**结果。以下任一情形推导失败：

- 某一对无法推导；
- 某一对推导出不止一组可能的值；
- 不同的对推导出不同的值；
- 某个模板实参既未被推导也未被显式指定。

另外：**类型形参的类型只在别处无法推导时，才从数组界推导**。（这对应下文 ¶13–¶14：`template<class T, T n> void f(int(&)[n])` 中 `T` 从界的类型 `size_t` 得出，但若 `T` 能从别处推导，以别处为准。）

```cpp
template<class T> void f(T x, T y) { /* ... */ }
struct A { };
struct B : A { };
void g(A a, B b) {
    f(a, b);    // error: T 被推导为 A 和 B
    f(b, a);    // error: 同上
    f(a, a);    // OK：T = A
    f(b, b);    // OK：T = B
}
```

"不同的对推导出不同的值"即使存在隐式转换（`B` → `A`）也是失败——推导不考虑转换（[[temp.deduct.call#4]]）。

## P 的组成（¶3–¶4）

¶3 类型 `P` 可以由其他类型、模板、常量模板实参值组合而成：

- ¶3.1 函数类型包括每个函数形参的类型、返回类型、**异常说明**；
- ¶3.2 成员指针类型包括所指对象的类类型和成员的类型；
- ¶3.3 类模板特化（如 `A<int>`）包括其模板实参列表引用的类型、模板、常量值；
- ¶3.4 数组类型包括元素类型和**界的值**。

¶4 大多数情况下，组成 `P` 的这些部分都**参与**推导：可以用来确定模板实参，且确定的值必须与别处一致。但在某些语境中，值**不参与**推导，而是使用别处推导出或显式指定的值。若一个模板形参**只**用在非推导语境中且未显式指定，推导失败。

注 1：按 [[temp.deduct.call]]，若 `P` 在推导语境中不含任何模板形参，就不做推导，所以 `P` 和 `A` 不必形式相同（只需能转换）。

## 非推导语境（¶5–¶6）

¶5 [[g:non-deduced-context|**非推导语境**]]（non-deduced context）有：

| ¶ | 语境 | 例子（`T`/`N` 在此处不被推导） |
|---|---|---|
| 5.1 | 用 *qualified-id* 指定的类型或模板的 *nested-name-specifier* | `typename A<T>::type`、`std::type_identity_t<T>` |
| 5.2 | *pack-index-specifier* 或 *pack-index-expression* {{c++26}} | `Ts...[0]` |
| 5.3 | *type-constraint* | `C<T> auto` 中 `C<T>` 的部分 |
| 5.4 | *decltype-specifier* 的表达式 | `decltype(T{} + 1)` |
| 5.5 | *splice-specifier* 的常量表达式 {{c++26}} | `[: refl :]` 中的 `refl` |
| 5.6 | 子表达式引用了模板形参的常量模板实参或数组界 | `A<N+1>`、`int[N*2]` |
| 5.7 | 带默认实参的函数形参中使用的模板形参，且该默认实参在本次调用中被使用 | `f(T = 5)` 调用 `f()` |
| 5.8 | 实参是重载集，且：有多个约束满足但类型不同的函数匹配（二义）、无函数匹配、或集合含函数模板 | `f(g)` 而 `g` 重载 |
| 5.9 | 实参是初始化列表，但形参不是可从初始化列表推导的类型 | `template<class T> void g(T); g({1,2,3});` |
| 5.10 | 不在形参列表末尾的函数形参包 | `template<class... Ts> void f(Ts..., int)` |

### 为什么这些不能推导？

- **5.1 限定名前缀**：从 `typename A<T>::type` = `int` 反推 `T` 需要"求逆"任意的类型函数——`A<T>::type` 对很多 `T` 都可能是 `int`，甚至可能被特化成任何东西。推导本质上不可能。
- **5.4 decltype**、**5.6 表达式**：同理，`N+1 == 5` 能解出 `N = 4`，但一般表达式（`N*N`、`f(N)`）无法求逆。标准选择一刀切：只要涉及形参的**子表达式**（不是形参本身），就不推导。
- **5.10 非尾随包**：不知道包要"吃掉"几个实参。

```cpp
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

（¶17 注 5：除引用和指针类型外，主数组界**不是**函数形参类型的一部分——`int a[i][20]` 被调整为 `int (*a)[20]`，`i` 消失了，自然推不出来；`f3` 用引用保住了它。）

```cpp
template <int i> class A { };
template <int i> void g(A<i+1>);
template <int i> void f(A<i>, A<i+1>);

void k() {
    A<1> a1;
    A<2> a2;
    g(a1);          // error: 表达式 i+1 不推导
    g<0>(a1);       // OK
    f(a1, a2);      // OK：i 从 A<i> 推导为 1，A<i+1> 只用来检查（A<2>，一致）
}
```

### std::type_identity：故意制造非推导语境

5.1 被广泛利用来**关闭**某个形参的推导。C++20 起标准库提供 `std::type_identity`（[[P0887R1]]）：

```cpp run ok title="type_identity.cpp"
#include <type_traits>
template<class T> T vmax(T a, std::type_identity_t<T> b) { return a < b ? b : a; }

auto r = vmax(1.5, 2);    // T 只从第一个实参推导为 double；2 隐式转换为 double
static_assert(std::is_same_v<decltype(r), double>);

int main() { }
```

`std::type_identity_t<T>` 是 `typename std::type_identity<T>::type`，`T` 处在 *nested-name-specifier* 中——非推导语境。于是第二个形参不参与推导，等到 `T` 由第一个实参确定后，它就是普通的 `double` 形参，允许任何隐式转换。没有它，`vmax(1.5, 2)` 会因 `T` 推导冲突（`double` vs `int`）而失败。

`std::forward` 的形参 `std::remove_reference_t<T>&` 也是故意的非推导语境——强制调用者写 `std::forward<T>(x)`。

### 复合类型：部分推导、部分不推导（¶6）

¶6 当一个类型名以包含非推导语境的方式指定时，**组成该类型名的所有类型**都是非推导的。但一个复合类型可以同时包含推导和非推导的部分。

- `A<T>::B<T2>`：`T` 和 `T2` 都不推导（整个名字是限定名）。
- `A<I+J>::X<T>`：`I`、`J`、`T` 都不推导。
- `void f(typename A<T>::B, A<T>)`：第一个形参中的 `T` 不推导，第二个形参中的 `T` 推导。

```cpp
template<int i, typename T>
T deduce(typename A<T>::X x,    // 这里 T 不推导
         T t,                   // 这里推导 T
         typename B<i>::Y y);   // 这里 i 不推导
A<int> a;
B<77>  b;
int x = deduce<77>(a.xm, 62, b.ym);
// T 推导为 int；a.xm 需能转换为 A<int>::X
// i 显式指定为 77；b.ym 需能转换为 B<77>::Y
```

（¶19 注 7。）

## 推导与"一致性"：例 3（¶7）

¶7 标准例 3 汇集了几种典型情形：

```cpp
// 一对 P/A 推导两个实参，可能自相矛盾
template <class T, class U> void f(T (*)(T, U, U));
int  g1(int, float, float);
char g2(int, float, float);
int  g3(int, char, float);
void r() {
    f(g1);    // OK：T = int，U = float
    f(g2);    // error: T 被推导为 char（返回）和 int（形参）
    f(g3);    // error: U 被推导为 char 和 float
}
```

```cpp
// 从函数类型的异常说明推导
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

（C++17 起异常说明是函数类型的一部分，所以 `noexcept(E)` 可以被推导。）

例 3 的后两段对应 [[temp.deduct.call#4]] 的限定转换与派生到基类：`f(const T*)` 接受 `int*`；`f(B<T>&)` 接受 `D<int>` 和 `struct D2 : B<int>`。

## 可推导的形式（¶8–¶12）

¶8 类型模板实参 `T`、常量模板实参 `i`、表示类模板或别名模板的模板模板实参 `TT`、表示变量模板或概念的模板模板实参 `VV`，在 `P` 和 `A` 具有以下形式之一时可以推导：

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

其中：

- ¶8.1 `T(opt)` 表示一个类型或形参类型列表，它要么**递归地**满足这些规则，要么是 `P` 或 `A` 中的非推导语境，要么在 `P` 和 `A` 中是**相同的非依赖类型**；
- ¶8.2 `i(opt)` 表示一个表达式，它要么**是**一个 `i`，要么在 `P` 或 `A` 中是值依赖的，要么在 `P` 和 `A` 中有相同的常量值；
- ¶8.3 `TT(opt)` 表示类模板或模板模板形参；
- ¶8.4 `noexcept(i(opt))` 表示异常说明，其 *noexcept-specifier* 的操作数（可以是隐式的）满足 `i(opt)` 的规则。

注 3：若某个类型符合这些形式但不含任何 `T`、`i`、`TT`，就无法推导。`<X>` 表示至少一个实参含 `X` 的模板实参列表；`<>` 表示没有任何实参含 `T`、`i`、`TT`、`VV` 的列表。

¶11 这些形式可以像 `T` 一样**进一步组合**：

```text
X<int> (*)(char[6])
```

是 `template-name<T> (*)(type[i])` 的形式，这又是 `type (*)(T)` 的变体，其中 `type` 是 `X<int>`、`T` 是 `char[6]`。

¶12 除以上形式外，不能从涉及其他构造的函数实参推导模板实参。

形式列表的意思是：推导**只能"看穿"类型构造器**——指针、引用、数组、函数、成员指针、模板特化——而不能看穿别名（别名在推导前就已展开为其目标类型）、限定名（非推导语境）、表达式。

```cpp run ok title="forms.cpp"
#include <type_traits>
template<class T, class U> constexpr bool same = std::is_same_v<T, U>;

template<class R, class... As> constexpr auto arity(R(*)(As...)) { return sizeof...(As); }
template<class C, class M> constexpr bool is_mem_obj(M C::*) { return !std::is_function_v<M>; }
template<template<class...> class TT, class... Ts> constexpr auto count(const TT<Ts...>&) { return sizeof...(Ts); }
template<class T, std::size_t N> constexpr auto len(T(&)[N]) { return N; }

struct S { int x; void f(); };
template<class...> struct List { };
int fn(int, char, double);
int arr[7];

static_assert(arity(&fn) == 3);                // T(T) 形式
static_assert(is_mem_obj(&S::x));              // T T::* 形式：C = S，M = int
static_assert(!is_mem_obj(&S::f));             // M = void()
static_assert(count(List<int, char>{}) == 2);  // TT<T> 形式
static_assert(len(arr) == 7);                  // T[i] 形式
int main() { }
```

## 模板实参列表中的包（¶9）

¶9 若 `P` 含有 `<T>`、`<i>`、`<TT>` 或 `<VV>` 形式，则把 `P` 的模板实参列表中的每个实参 `Pi` 与 `A` 的对应实参 `Ai` 比较。

- 若 `P` 的模板实参列表含有一个**不是最后一个**实参的包展开，**整个**模板实参列表都是非推导语境。
- 若 `Pi` 是包展开，把它的模式与 `A` 的模板实参列表中**剩余的每个**实参比较，每次比较推导包的下一个位置。
- 在偏序中，若 `Ai` 原本是包展开：¶9.1 `P` 中没有与 `Ai` 对应的实参，则忽略 `Ai`；¶9.2 否则若 `Pi` 不是包展开，推导失败。

```cpp ok
template<class T1, class... Z> class S;                                 // #1
template<class T1, class... Z> class S<T1, const Z&...> { };            // #2
template<class T1, class T2>   class S<T1, const T2&> { };              // #3
S<int, const int&> s;           // #2 和 #3 都匹配；#3 更特殊

template<class T, class... U>            struct A { };                  // #1
template<class T1, class T2, class... U> struct A<T1, T2*, U...> { };   // #2
template<class T1, class T2>             struct A<T1, T2> { };          // #3
template struct A<int, int*>;   // 选 #2
```

第二组：`A<int, int*>` 同时匹配 #2（`U` 为空）和 #3。偏序时，#3 的 `T2` 只能推出"任意类型"，#2 的 `T2*` 要求指针——#2 更特殊。¶9.1 保证 #3 中没有与 #2 的 `U...` 对应的东西时，不会因此失败。

## 函数形参列表中的包；函数类型推导中的转发引用（¶10）

¶10 若 `P` 含 `(T)` 形式，把 `P` 的形参类型列表的每个 `Pi` 与 `A` 的对应 `Ai` 比较。

**特殊调整**：若 `P` 和 `A` 是**取函数模板地址**（[[temp.deduct.funcaddr]]）或**从函数声明推导**（[[temp.deduct.decl]]）时产生的函数类型，且 `Pi` 和 `Ai` 是顶层形参类型列表中的形参，若 `Pi` 是转发引用而 `Ai` 是左值引用，就把 `Pi` 改为模板形参类型（`T&&` 改为 `T`）。注 4：于是 `Pi` 为 `T&&`、`Ai` 为 `X&` 时，`T` 推导为 `X&`。

```cpp run ok title="spec_fwd.cpp"
#include <cstdio>
template <class T> void f(T&&)  { std::puts("primary"); }
template <> void f(int&)  { std::puts("#1 f<int&>"); }    // T&& 对 int&：调整为 T，T = int&
template <> void f(int&&) { std::puts("#2 f<int>"); }     // T&& 对 int&&：T = int

int main() {
    int i = 0;
    f(i);    // 调用 f<int&>(int&)，即 #1
    f(0);    // 调用 f<int>(int&&)，即 #2
}
```

没有这条调整，`template<> void f(int&)` 中 `T&&` 对 `int&` 做结构匹配会失败（`&&` 对 `&`），程序员就无法为"左值实参"那个特化写显式特化。

若与 `Pi` 对应的形参声明是函数形参包，就把包的 *declarator-id* 的类型与 `A` 剩余的每个形参类型比较。偏序时若 `Ai` 原本是函数形参包：¶10.1 `P` 没有对应形参类型则忽略；¶10.2 否则若 `Pi` 不是函数形参包，推导失败。

```cpp ok
template<class T, class... U> void f(T*, U...) { }   // #1
template<class T>             void f(T) { }          // #2
template void f(int*);                               // 选 #1
```

`f(int*)` 同时匹配 #1（`U` 为空）和 #2（`T = int*`）。偏序：#1 的 `T*` 比 #2 的 `T` 更特殊；¶10.1 让 #1 的 `U...` 在与 #2 比较时被忽略。

## 常量模板形参的类型（¶13–¶16，¶20）

¶13 若常量模板形参 `P` 的类型是**依赖的**，而它的值从一个表达式推导出来，那么 `P` 类型中的模板形参从**值的类型**推导：

```cpp ok
template<long n> struct A { };

template<typename T> struct C;
template<typename T, T n> struct C<A<n>> { using Q = T; };

using R = long;
using R = C<A<2>>::Q;     // OK：T 从 A<2> 中模板实参值的类型推导为 long
```

注意 `T` 推导为 `long`（`A` 的形参类型），而不是 `int`（字面量 `2` 的类型）——因为 `A<2>` 中的 `2` 已经被转换为 `long`。

¶14 `T[N]` 中 `N` 的类型是 `std::size_t`：

```cpp ok
template<typename T> struct S;
template<typename T, T n> struct S<int[n]> { using Q = T; };

using V = decltype(sizeof 0);
using V = S<int[42]>::Q;  // OK：T 从 int[42] 推导为 std::size_t
```

¶15 函数类型的 `noexcept(B)` 中 `B` 的类型是 `bool`：

```cpp ok
template<bool> struct A { };
template<auto> struct B;
template<auto X, void (*F)() noexcept(X)> struct B<F> { A<X> ax; };
void f_nothrow() noexcept;
B<f_nothrow> bn;          // OK：X 的类型推导为 bool
```

¶16：

```cpp ok
template<class T, T i> void f(int (&a)[i]);
int v[10];
void g() { f(v); }        // OK：T 是 std::size_t
```

¶20 若 `P` 含 `<i>` 形式，除非 `i` 的类型与 `A` 中所指模板的**对应模板形参 `p` 的类型相同**，否则推导失败；若 `i` 的声明类型含占位类型，则以 `p` 的 *id-expression* 作为占位类型推导的对应实参。若 `P` 含 `[i]` 形式而 `i` 的类型不是整型，推导失败（脚注：`bool` 形参虽然可以从数组界推导，但结果总是 `true`，因为界非零）。若 `P` 含 `noexcept(i)` 而 `i` 的类型不是 `bool`，推导失败。

```cpp
template<int i> class A { };
template<short s> void f(A<s>);
void k1() {
    A<1> a;
    f(a);           // error: 推导失败——int 到 short 的类型不同
    f<1>(a);        // OK：显式指定，不推导
}

template<const short cs> class B { };
template<short s> void g(B<s>);
void k2() {
    B<1> b;
    g(b);           // OK：模板形参类型的 cv 被忽略
}

template<auto> struct C;
template<long long x> void f(C<x> *);
void g(C<0LL> *ap) {
    f(ap);          // OK：从 0LL 推导出 long long 值
}

template<int> struct D;
template<auto x> void f(D<x> *);
void g(D<0LL> *ap) {
    f(ap);          // OK：x 推导为 int 值（D 的形参是 int，0LL 已转为 int）
}

template<int &> struct E;
template<auto x> void f(E<x> *);
int v;
void g(E<v> *bp) {
    f(bp);          // error: x 的类型 int 与 E<v> 中模板形参的类型 int& 不匹配
}

template<const int &> struct F;
template<decltype(auto) x> void f(F<x> *);
int i;
void g(F<i> *ap) {
    f(ap);          // OK：x 推导为类型为 const int& 的常量模板形参
}
```

`E` 与 `F` 的对比显示了 ¶20 中"占位类型"那句的作用：`auto x` 对 `p`（类型 `int&`）做 `auto` 推导，得 `int`，与 `int&` 不同 → 失败；`decltype(auto) x` 则得 `const int&`，相同 → 成功。

标准例 13 的最后一段：

```cpp
template <decltype(auto) q> struct G;
template <auto x> long *f(G<x> *);              // #1
template <decltype(auto) x> short *f(G<x> *);   // #2

const int j = 0;
short *g(G<(j)> *ap) {    // OK：q 的类型是 const int&
    return f(ap);         // OK：只有 #2 匹配
}
long *g(G<j> *ap) {       // OK：q 的类型是 int
    return f(ap);         // OK：#1 更特殊
}
```

!!! impl "Clang 的偏差"
    截至写作时，Clang 23 对最后一个调用 `f(ap)`（`G<j>`）报"二义"，标准说 #1 更特殊。其余例子 Clang 的行为与标准一致。

## 函数、函数指针、默认实参、模板模板形参（¶21–¶23）

¶21 模板实参可以从函数类型、函数指针类型、成员函数指针类型推导：

```cpp
template<class T> void f(void(*)(T, int));
template<class T> void foo(T, int);
void g(int, int);
void g(char, int);
void h(int, int, int);
void h(char, int);

int m() {
    f(&g);      // error: 二义（两个 g 都匹配，T 不同）
    f(&h);      // OK：void h(char, int) 是唯一匹配
    f(&foo);    // error: 推导失败，因为 foo 是模板
    return 0;
}
```

这三行分别对应 ¶5.8 的三种情形。注意 `f(&g)` 的结果是"无法推导 T"（形参变成非推导语境，`T` 又没有别处可推），所以报的是"没有匹配的函数"。

¶22 模板类型形参**不能**从函数默认实参的类型推导：

```cpp
template <class T> void f(T = 5, T = 7);
void g() {
    f(1);           // OK：调用 f<int>(1, 7)
    f();            // error: 无法推导 T
    f<int>();       // OK：调用 f<int>(5, 7)
}
```

`f(1)` 中第二个形参用了默认实参，按 ¶5.7 它是非推导语境，`T` 只从第一个实参推导。

¶23 模板模板形参对应的模板实参，从函数调用实参列表中所用的类模板特化的**模板实参**的类型推导：

```cpp ok
template <template <class T> class X> struct A { };
template <template <class T> class X> void f(A<X>) { }
template<class T> struct B { };
A<B> ab;
void use() { f(ab); }      // 调用 f(A<B>)：X 推导为 B
```

## 包推导出零个或多个实参（¶24）

¶24（注 8）涉及形参包的推导可以为每个包推导出**零个或多个**实参。

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
Y<int, float, double> y3;       // 主模板；Types = int, float, double
int fv = f(g);                  // OK；Types = int, float
```

`Y<int, float, double>` 不匹配部分特化：`Types&...` 要求 `float`、`double` 都是左值引用类型。

## 陷阱

!!! pitfall "别名模板是“透明”的"
    `template<class T> using Vec = std::vector<T>;` 后，`template<class T> void f(Vec<T>)` 等价于 `f(std::vector<T>)`，可以推导。但如果别名模板展开后 `T` 落在非推导语境里，例如 `template<class T> using Id = typename std::type_identity<T>::type;`，`f(Id<T>)` 中的 `T` 就不可推导——推导看的是**展开后**的类型。

!!! pitfall "依赖的成员类型永远推不出来"
    `template<class C> void f(typename C::iterator)` 无法从迭代器推导出容器 `C`（¶5.1）。标准算法因此以迭代器类型本身为模板形参：`template<class It> void sort(It, It)`。

!!! pitfall "数组界：引用保留，值丢失"
    `void f(T a[N])` 等价于 `void f(T* a)`，`N` 推不出（¶17）；必须写 `T (&a)[N]`。

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

`T` 从第一个形参推导为 `int`（第二个形参中的 `T` 是非推导语境）。推导完成后代入：`Box<int>::value_type` 不存在——这是函数类型中的无效类型，推导失败（SFINAE）。如果没有其他候选，报"no matching function"。这说明非推导语境中的形参虽然不参与推导，但仍要在推导后代入并检查。
</details>

!!! question "思考题 2"
    为什么 `template<int N> void f(std::array<int, N>)` 对 `std::array<int, 3>` 推导失败，而 `template<std::size_t N> void f(std::array<int, N>)` 成功？

<details markdown="1">
<summary>答案</summary>

¶20：`P` 含 `<i>` 形式时，`i` 的类型必须与 `A` 所指模板中对应模板形参的类型**相同**。`std::array` 的第二个形参类型是 `std::size_t`，而 `N` 的类型是 `int`，不同，推导失败。写 `std::size_t N` 或 `auto N` 都行（后者按占位类型推导得 `std::size_t`）。
</details>

## 小结

| 规则 | 段落 | 要点 |
|---|---|---|
| 各 P/A 对独立推导再合并；冲突、多解、未定则失败 | ¶2 | 不考虑转换 |
| 类型形参只在别处无法推导时才从数组界推导 | ¶2 | — |
| 非推导语境：限定名前缀、包索引、类型约束、decltype、拼接、含形参的子表达式、使用默认实参的形参、重载集、初始化列表、非尾随包 | ¶5 | `type_identity_t` |
| 非推导语境"传染"整个类型名 | ¶6 | 复合类型可部分推导 |
| 可推导形式：`T*`、`T&`、`T[i]`、`T(T)noexcept(i)`、`T T::*`、`TT<...>` 等，可递归组合 | ¶8, ¶11 | 其他构造不能推导 |
| 模板实参列表中非末尾的包 → 整个列表非推导 | ¶9 | — |
| 函数类型推导中转发引用对左值引用：`T&&` 调整为 `T` | ¶10 | 用于显式特化/取地址 |
| 常量形参的类型从值的类型推导；`T[N]` 的 N 是 `size_t`；`noexcept(B)` 的 B 是 `bool` | ¶13–¶15 | — |
| `<i>` 的类型必须与对应形参的类型相同 | ¶20 | `int N` 对 `array<int, 3>` 失败 |
| 函数默认实参不能推导类型形参 | ¶22 | — |
| 包可推导出零个或多个实参 | ¶24 | — |
