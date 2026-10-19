---
title: 模板实参推导
summary: 推导的总流程与 SFINAE：显式实参先代入、再推导、再补默认值、再检查约束与非依赖形参、最后整体代入；代入按词法顺序进行，只有直接语境中的无效类型或表达式才导致推导失败（静默剔除候选），其余是硬错误。另含取函数模板地址、转换函数模板、偏序、从声明推导四种推导语境。
status: done
covers: temp.deduct.general, temp.deduct.funcaddr, temp.deduct.conv, temp.deduct.partial, temp.deduct.decl
papers: N2634, P0315R4
related: temp.deduct.call, temp.deduct.type, temp.fct.spec, temp.over, temp.func.order, temp.inst, temp.constr.constr, over.match.best, topics/type-deduction
tags: 模板, 模板实参推导, SFINAE, 偏序
updated: 2026-10-18
---

调用 `std::max(a, b)` 时你没有写 `<int>`，编译器却知道是 `max<int>`，靠的就是**模板实参推导**（template argument deduction）。它是 C++ 泛型编程中最重要的便利，也是最复杂的子系统之一：第 13.10.3 节 [[temp.deduct]] 有七个子条款，本站分三页：

| 子条款 | 内容 | 页面 |
|---|---|---|
| [[temp.deduct.general]] | 总流程、代入、SFINAE、直接语境 | 本页 |
| [[temp.deduct.call]] | 从函数调用推导：P/A 调整、转发引用、初始化列表 | [[temp.deduct.call]] |
| [[temp.deduct.funcaddr]] | 取函数模板地址时推导 | 本页 |
| [[temp.deduct.conv]] | 推导转换函数模板的实参 | 本页 |
| [[temp.deduct.partial]] | 偏序中的推导 | 本页 |
| [[temp.deduct.type]] | 从类型推导：可推导的形式、非推导语境 | [[temp.deduct.type]] |
| [[temp.deduct.decl]] | 从函数声明推导（显式特化/实例化/友元） | 本页 |

所有推导语境的核心都在 [[temp.deduct.type]]：拿一个用模板形参写成的类型 `P` 去和一个实际类型 `A` 比较，求出让两者一致的模板实参。各语境的区别只在于 `P` 和 `A` 从哪里来、比较前做哪些调整。

本页先讲总流程，也就是推导之外的那些步骤：显式实参的代入、默认实参、约束检查、最终的代入，以及其中最著名的副产品 [[g:sfinae|**SFINAE**]]。

## 总流程（¶1–¶6）

¶1 引用函数模板特化时，所有模板实参都必须有值：显式指定、从使用中推导，或从默认模板实参取得。

```cpp
void g(double d) {
    int i = convert<int>(d);      // 调用 convert<int, double>(double)
    int c = convert<char>(d);     // 调用 convert<char, double>(double)
}
```

把 ¶2–¶6 拼起来，函数调用语境中的推导流程是：

```text
① 显式模板实参 ─→ 检查 template-id 合法性 ─→ 代入函数类型   （¶2）
                                              │ 失败 → 推导失败
② 对函数类型做 [dcl.fct] 调整（数组→指针、去顶层 cv）            （¶3）
③ 推导：以②得到的函数类型为 P，与调用实参 A 逐对比较        （¶5, [temp.deduct.call]）
④ 未推导的形参：用默认模板实参（代入之前已确定的实参）        （¶5）
⑤ 把全部实参代入模板形参列表（形参的类型、默认值……）          （¶5）
⑥ 检查关联约束是否满足                                       （¶5）
⑦ 非依赖形参：检查实参能否隐式转换                            （¶5）
⑧ 把全部实参代入函数类型                                       （¶5）
                                     任一步失败 → 推导失败（候选被剔除）
```

### 显式实参的代入（¶2–¶4）

¶2 给出了显式模板实参列表时，若 *template-id*（或拼接特化说明符 {{c++26}}）不合法（[[temp.names]]），推导失败；否则把这些实参代入对应的模板形参。

¶3 代入之后，对函数形参类型做 [[dcl.fct]] 中的调整：数组 → 指针、函数 → 函数指针、删除顶层 cv。例 2：形参列表 `(const int, int[5])` 调整为 `(int, int*)`。注 1：顶层 cv 不影响函数类型，但仍影响函数体内形参变量的类型。

```cpp run ok title="explicit_subst.cpp"
#include <type_traits>
template <class T> void f(T t) { static_assert(std::is_const_v<decltype(t)> == std::is_const_v<T>); }
template <class X> void g(const X x) { static_assert(std::is_const_v<decltype(x)>); }
template <class Z> void h(Z, Z*) { }

int main() {
    f<int>(1);          // 函数类型 f(int)，t 非 const
    f<const int>(1);    // 函数类型 f(int)，t 是 const
    g<int>(1);          // 函数类型 g(int)，x 是 const
    g<const int>(1);    // 函数类型 g(int)，x 是 const
    h<const int>(1, 0); // 函数类型 h(int, const int*)

    static_assert(std::is_same_v<decltype(&f<const int>), void(*)(int)>);
    static_assert(std::is_same_v<decltype(&h<const int>), void(*)(int, const int*)>);
}
```

`h<const int>` 的第一个形参 `Z` = `const int`，顶层 const 被调整掉成为 `int`；第二个形参 `Z*` = `const int*`，这里 `const` 不是顶层的，保留。

¶4（注 2）`f<int>(1)` 和 `f<const int>(1)` 调用的是不同的函数，尽管函数类型相同。它们是两个特化，有各自的地址和各自的静态变量。

### 默认实参、约束、非依赖形参（¶5）

¶5 是整个推导过程的主干，按顺序说了五件事：

1. 代入并调整后的函数类型被用作推导时的函数模板类型。
2. 如果某个模板实参未被推导，而对应形参有默认实参，就把前面已确定的模板实参代入默认实参来得到它。代入结果无效则推导失败。

    ```cpp
    template <class T, class U = double>
    void f(T t = 0, U u = 0);

    void g() {
        f(1, 'c');        // f<int, char>(1, 'c')
        f(1);             // f<int, double>(1, 0)：U 用默认模板实参
        f();              // error: T 无法推导（函数默认实参不参与推导）
        f<int>();         // f<int, double>(0, 0)
        f<int, char>();   // f<int, char>(0, 0)
    }
    ```

    注意 `f()` 失败了：函数默认实参 `T t = 0` 不能用来推导 `T`（[[temp.deduct.type#22]]），因为默认实参的类型本身依赖于 `T`。

3. 所有模板实参都确定后，把它们代入模板形参列表中的所有使用（例如常量模板形参的类型、后续形参的默认值）。无效则推导失败。
4. 若函数模板有关联约束，检查其是否满足；不满足则推导失败。
5. 在函数调用语境中，对每个在代入任何显式实参之前就已是非依赖的函数形参，检查对应实参能否隐式转换为形参类型；不能则推导失败。按注 3，其余形参（含不参与推导的依赖形参、因显式实参而变得非依赖的形参）由重载决议检查。
6. 若到此仍未失败，把模板实参代入函数类型中的所有使用。无效则推导失败。

第 4、5 步的位置很关键：**约束检查和非依赖形参的转换检查都在代入函数类型之前**。原因是代入函数类型可能触发实例化（例如返回类型 `typename Z<T>::xx` 会实例化 `Z<T>`），而实例化中的错误是硬错误。先检查代价低、不会引发实例化的条件，就能在不必实例化的情况下尽早淘汰候选：

```cpp ok title="early_fail.cpp"
template <class T> struct Z {
    typedef typename T::x xx;          // 对 T = int 或 A 实例化都会出错
};
template <class T> concept C = requires { typename T::A; };

template <C T> typename Z<T>::xx f(void *, T);   // #1
template <class T> void f(int, T);               // #2

struct A {} a;
struct ZZ {
    template <class T, class = typename Z<T>::xx> operator T *();
    operator int();
};

int main() {
    ZZ zz;
    f(1, a);    // OK：#1 推导失败，因为 int 不能转为 void*（第 5 步）——Z<A> 从未实例化
    f(zz, 42);  // OK：#1 推导失败，因为 C<int> 不满足（第 4 步）——Z<int> 从未实例化
}
```

- `f(1, a)`：#1 的第一个形参 `void*` 是非依赖的。`1` 不能转为 `void*`，第 5 步就失败，不会去代入返回类型 `Z<A>::xx`。否则实例化 `Z<A>` 会因 `A::x` 不存在而产生硬错误。
- `f(zz, 42)`：`T = int`，约束 `C<int>` 不满足，第 4 步失败。如果先做第 5 步，`zz` 到 `void*` 的转换会考虑 `operator T*()` 模板，那需要代入 `Z<void>::xx`，又会导致硬错误。

!!! history "检查顺序的演变"
    早期的规则是先代入整个函数类型，再在重载决议中检查转换。这导致很多本应被淘汰的候选在代入返回类型时触发硬错误。C++20 引入约束时，[[CWG2369]] 把约束检查提前到代入函数类型之前；非依赖形参的转换检查也在同一时期被加入，使 ¶5 呈现出今天的顺序。

### 代入发生在两个时刻（¶6）

¶6 推导过程中有两个时刻需要把模板实参代入函数类型：开头代入显式指定的实参，结尾代入推导出的和默认的实参。

## 代入的范围与顺序（¶7）

¶7 定义了[[g:deduction-substitution-loci|**推导代入位置**]]（deduction substitution loci）：

- ¶7.1 函数类型，不含 *noexcept-specifier*；
- ¶7.2 *explicit-specifier*（`explicit(bool)`）；
- ¶7.3 模板形参声明；
- ¶7.4 部分特化的模板实参列表（[[temp.spec.partial.general]]）。

代入发生在这些位置中用到的所有类型和表达式中，不仅包括数组界、常量模板实参这样的常量表达式，还包括 `sizeof`、`decltype` 等允许非常量表达式的语境里的一般表达式。（后者就是 C++11 引入的表达式 SFINAE。）

!!! std
    The substitution proceeds in lexical order and stops when a condition that causes deduction to fail is encountered.

    代入按词法顺序进行，遇到导致推导失败的条件即停止。

之所以要规定顺序，是因为代入可能触发实例化，而实例化有副作用，还可能产生硬错误。先遇到的失败可以让后面的部分免于代入：

```cpp title="lexical_order.cpp"
template <class T> struct A { using X = typename T::X; };

template <class T> typename T::X f(typename A<T>::X);
template <class T> void f(...) { }

template <class T> auto g(typename A<T>::X) -> typename T::X;
template <class T> void g(...) { }

void x() {
    f<int>(0);    // OK：先代入返回类型 int::X，失败，停止——A<int> 从未实例化
    g<int>(0);    // error：先代入形参类型 A<int>::X，实例化 A<int>，其中 int::X 是硬错误
}
```

`f` 与 `g` 的唯一区别是返回类型写在前面还是后面（尾置返回类型在词法上位于形参之后）。

¶7 末尾还规定：如果对同一个函数模板的不同声明做代入会导致模板实例化以不同顺序发生或根本不发生，程序 {{ifndr}}：

```cpp ifndr
template <class T> struct A { using X = typename T::X; };
template <class T> typename T::X h(typename A<T>::X);
template <class T> auto h(typename A<T>::X) -> typename T::X;   // 同一模板的重声明
template <class T> void h(...) { }
void x() { h<int>(0); }   // IFNDR：两个声明的代入顺序不同
```

注 4 指出，对异常说明（[[except.spec]]）和函数契约断言（[[dcl.contract.func]]）的等价代入，只在 *noexcept-specifier* 或 *function-contract-specifier* 被实例化时才做；那时若代入得到无效类型或表达式，程序非良构，不属于 SFINAE。

```cpp error
template<class T> void f(T) noexcept(T::value);   // noexcept 不在代入位置中
void f(...);
void t() { f(0); }   // error: 选中模板后实例化 noexcept 说明符，int::value 非良构
```

!!! history "词法顺序"
    C++11 只说代入发生在函数类型中用到的所有类型和表达式中，没有规定顺序，各编译器行为不一。[[CWG1227]] 明确了按词法顺序代入、遇到失败即停止，作为 C++14 的缺陷报告。

## SFINAE：无效类型与直接语境（¶8–¶9）

¶8 是 SFINAE 的定义：

- 代入产生无效类型或表达式时，推导失败。所谓无效，是指在同一语境中用代入后的实参写出来会非良构且要求诊断。注 5 补充，若不要求诊断，程序仍是非良构的。**访问检查是代入过程的一部分。**
- 无效类型和表达式只有在推导代入位置的[[g:immediate-context|**直接语境**]]（immediate context）中，才会导致推导失败。
- 推导代入位置的直接语境就是该位置本身，不包括 lambda 表达式的函数体和单独实例化的构造。

推导失败的后果见 [[temp.over]]：这个函数模板不会为此次调用贡献候选函数，它被静默剔除，不报错。这就是 Substitution Failure Is Not An Error（代入失败不是错误）。这个缩写来自 Vandevoorde 与 Josuttis 的 *C++ Templates*，标准本身不使用它。

```cpp ok
template<typename T>
T* fun(T&& v);   // #1：代入位置是函数类型"(T&&) → T*"

void fun(...);   // #2

void test() {
    int i = 0;
    fun(i);      // 选 #2：T 推导为 int&，形成"指向引用的指针" int&* 失败
}
```

注 6 指出，单独实例化的构造即使与推导同时被实例化，也不在直接语境中。注 7 指出，代入可能带来模板特化的实例化、隐式定义函数的生成等副作用；这些副作用不在直接语境中，其中的错误会使程序非良构。

直接语境是 SFINAE 最微妙的地方。粗略地说，**错误必须直接出现在函数模板的声明（签名、模板形参列表）里，而不是藏在为了处理声明而实例化的别的东西里**。

```cpp error
template<class T> struct Wrap { using type = typename T::value_type; };

template<class T> typename Wrap<T>::type first(T);   // #1
template<class T> void first(...);                   // #2

void t() { first<int>(0); }   // error：错误在 Wrap<int> 的类体里，不在直接语境
```

代入 `Wrap<int>::type` 需要实例化 `Wrap<int>`，`int::value_type` 的错误发生在类模板的实例化中，属于 ¶8 注 7 所说的副作用，因此是硬错误。如果让错误直接出现在签名里，或者让 `Wrap` 本身能妥善处理没有 `value_type` 的情形（例如用部分特化或约束，只在合法时提供 `type`），就变成 SFINAE：

```cpp ok
template<class T> struct Safe { };                                    // 没有 type
template<class T> requires requires { typename T::value_type; }
struct Safe<T> { using type = typename T::value_type; };

template<class T> typename Safe<T>::type first(T);   // #1
template<class T> void first(...);                   // #2

void t() { first<int>(0); }   // OK：Safe<int> 合法地没有 type，#1 推导失败，选 #2
```

标准库 trait 正是这样做到 SFINAE 友好的：`std::common_type<A, B>`、`std::invoke_result<F, Args...>` 在无解时没有 `type` 成员，而不是在类体内报错。

### 访问检查是代入的一部分

```cpp ok
class P { using secret = int; };                             // 私有

template<class T> auto probe(T*) -> typename T::secret;      // 访问失败 → 推导失败
template<class T> char probe(...);

static_assert(sizeof(probe<P>(nullptr)) == 1);               // 选了 probe(...)
```

C++11 之前，访问错误在 SFINAE 中的地位不明；现在它明确是代入的一部分，访问失败就是推导失败。

### 语句永不在直接语境中（¶9）

¶9（注 8）任何语句都不在推导代入位置的直接语境中。C++20 起 lambda 可以出现在不求值操作数里（[[P0315R4]]），于是签名里可以出现 lambda，而它的函数体是语句，不在直接语境中：

```cpp
template <class T>
    auto f(T) -> decltype([]() { T::invalid; } ());
void f(...);
f(0);              // error：lambda 体中的无效表达式不在直接语境

template <class T, std::size_t = sizeof([]() { T::invalid; })>
    void g(T);
void g(...);
g(0);              // error：同上

template <class T>
    auto h(T) -> decltype([x = T::invalid]() { });
void h(...);
h(0);              // OK：init-capture 的初始化器在直接语境中，推导失败，调用 h(...)

template <class T>
    auto i(T) -> decltype([]() -> typename T::invalid { });
void i(...);
i(0);              // OK：lambda 的返回类型在直接语境中，调用 i(...)

template <class T>
    auto j(T t) -> decltype([](auto x) -> decltype(x.invalid) { } (t));
void j(...);
j(0);              // OK：调用泛型 lambda 时，对其返回类型的推导失败使调用表达式无效
```

由此可见，lambda 的声明部分（捕获初始化器、形参、返回类型）在直接语境中，函数体则不在。

### 一个经典的表达式 SFINAE（¶10）

```cpp run ok title="expr_sfinae.cpp"
struct X { };
struct Y { Y(X) { } };

template <class T> auto f(T t1, T t2) -> decltype(t1 + t2);   // #1
X f(Y, Y);                                                    // #2

X x1, x2;
X x3 = f(x1, x2);   // #1 推导失败（X + X 无效），调用 #2

int main() { }
```

`decltype(t1 + t2)` 让 `T` 支持 `+` 这一要求成为签名的一部分。这就是 C++11 的**表达式 SFINAE**（[[N2634]]）。在此之前，只有类型（如 `typename T::type`）的失败才能可靠地算作 SFINAE。

## 推导失败的原因一览（¶11–¶12）

¶11（注 9）列出推导失败的常见原因。这只是注，并非穷举，规范性规则只有 ¶8 关于无效类型或表达式的那一条。

| ¶ | 原因 | 最小例子 |
|---|---|---|
| 11.1 | 展开含多个长度不同的包 | `template<class... A, class... B> void f(pair<A,B>...)` 配上不等长 |
| 11.2 | 创建元素为 `void`/函数/引用的数组，或大小为零或负数的数组 | `template<class T> int f(T[5]); f<void>(0);` |
| 11.3 | 在限定名中使用非类、非枚举类型 | `template<class T> int f(typename T::B*); f<int>(0);` |
| 11.4 | *nested-name-specifier* 中的类型没有该成员，或成员种类不对（需要类型却是非类型、需要模板却不是模板……） | 见下 |
| 11.5 | 创建指向引用的指针 | `T*`，`T = int&` |
| 11.6 | 创建对 `void` 的引用 | `T&`，`T = void` |
| 11.7 | `T` 不是类类型时创建指向 `T` 成员的指针 | `template<class T> int f(int T::*); f<int>(0);` |
| 11.8 | 给常量模板形参无效的类型 | 非结构化类型作为常量模板实参 |
| 11.9 | 模板实参表达式或函数声明中的表达式进行了无效转换 | `template<class T, T*> int f(int); f<int, 1>(0);` |
| 11.10 | 创建形参为 `void`、或返回函数/数组类型的函数类型 | `T(int)`，`T = int[3]` |
| 11.11 | 给 lambda 调用运算符的显式对象形参不允许的类型 | — |

```cpp ok title="nns_failures.cpp"
template <int I> struct X { };
template <template <class T> class> struct Z { };
template <class T> void f(typename T::Y*) { }
template <class T> void g(X<T::N>*) { }
template <class T> void h(Z<T::template TT>*) { }   // 标准原文写 Z<T::TT>，Clang 要求 template 消歧义
template <class T> void f(...) { }
template <class T> void g(...) { }
template <class T> void h(...) { }

struct A { };
struct B { int Y; };
struct C { typedef int N; };
struct D { typedef int TT; };

int main() {        // 下面每一行，第一个模板都推导失败，调用 (...) 版本
    f<A>(0);        // A 没有成员 Y
    f<B>(0);        // B::Y 不是类型
    g<C>(0);        // C::N 不是非类型非模板名
    h<D>(0);        // D::TT 不是模板
}
```

¶12 窄化让常量模板实参的代入失败：

```cpp
template <int> int f(int);
template <signed char> int f(int);
int i1 = f<1000>(0);    // OK：1000 转 signed char 是窄化，第二个模板推导失败
int i2 = f<1>(0);       // error: 二义——1 不窄化，两个模板都可行
```

（这里假定 `signed char` 无法表示 1000。）

## 取函数模板地址时推导（[temp.deduct.funcaddr]）

¶1 取重载集（含函数模板）的地址时，可以从目标类型推导模板实参。如果有目标（被初始化的指针或引用类型、被赋值的左操作数类型、函数形参类型、转型目标等，见 [[over.over]]），函数模板的函数类型作为 `P`、目标类型作为 `A`，按 [[temp.deduct.type]] 推导。否则用空的 `P`、`A` 集合推导（这时只有显式实参和默认实参能提供值）。

```cpp ok
template<class T> T twice(T x) { return x + x; }
int    (*pf)(int)    = twice;       // T = int：从目标类型推导
double (*pd)(double) = &twice;      // T = double
auto pa = &twice<long>;             // 无目标：必须显式指定
void take(int (*)(int));
void use() { take(twice); }         // 目标是形参类型
```

```cpp error
template<class T> T twice(T x) { return x + x; }
auto pa = &twice;                   // error: 没有目标，T 无法推导
```

¶2 函数模板返回类型中的占位类型（`auto`）是非推导语境。推导成功后，返回类型由实例化函数体确定。

```cpp ok
template<class T> auto ret(T x) { return x; }
int (*pr)(int) = ret;   // T 从形参推导为 int；返回类型 auto 不参与推导，实例化后为 int
```

## 转换函数模板的推导（[temp.deduct.conv]）

¶1 对转换函数模板 `template<class T> operator T()`，推导时比较其返回类型（`P`）与要转换到的类型（*conversion-type-id*，`A`），按 [[temp.deduct.type]] 进行。若 *conversion-function-id* 是在重载决议中构造的（[[over.match.funcs]]），适用下面的额外规则。它们与 [[temp.deduct.call]] 中的 P/A 调整互为镜像：调用推导中 `P` 是形参、`A` 是实参；转换推导中 `P` 是产出的类型、`A` 是需要的类型，方向相反。

| ¶ | 规则 |
|---|---|
| ¶2 | `P` 是引用类型：用被引用的类型代替 `P` |
| ¶3 | `A` 不是引用类型时：`P` 是数组 → 用数组到指针转换后的类型；`P` 是函数 → 函数指针；否则去掉 `P` 的顶层 cv |
| ¶4 | `A` 有顶层 cv：去掉；`A` 是引用：用被引用的类型 |
| ¶5 | 一般要求推导后的 `A` 与 `A` 相同；但在推导本会失败时可以忽略：原 `A` 是引用时 `A` 的 cv（5.1）、原 `A` 是可能抛出的函数指针时的异常说明（5.2）、可以由限定转换恢复的 cv（5.3）。忽略后若有多种可能，推导失败 |

```cpp run ok title="conv_template.cpp"
#include <cstdio>
struct Any {
    template<class T> operator T() const { std::puts("operator T"); return T(); }
};
struct Ref {
    template<class T> operator T&() { static T t{}; std::puts("operator T&"); return t; }
};

int main() {
    Any a;
    int x = a;            // T = int
    double d = a;         // T = double
    Ref r;
    int y = r;            // P = T&，¶2：用 T 比较，T = int
    const int& cy = r;    // A = const int&，¶4：用被引用的 const int 比较，T = const int
    (void)x; (void)d; (void)y; (void)cy;
}
```

像 `Any` 这样能转换为任何类型的类型在实践中是危险的，会让大量重载决议变得二义。标准库中 `std::nullopt_t`、`std::ignore` 等刻意避免这种设计。

## 偏序中的推导（[temp.deduct.partial]）

偏序（partial ordering，[[temp.func.order]]）决定两个都可行的函数模板中哪个更特殊，用于重载决议的决胜（[[over.match.best]] ¶2.5）、显式特化/实例化/友元声明的模板选择（[[temp.deduct.decl]]）、取地址。[[temp.func.order]] 规定了变换的方法（把每个模板形参替换成一个独一无二的合成类型、值或模板）；本节规定变换后如何做推导。

### 基本方法（¶1–¶4）

¶1–¶2 每个模板都有原始函数类型和变换后的函数类型。用变换后的类型作实参模板、对方的原始类型作形参模板做推导，两个方向各做一次。

直观地说，要问的是：模板 1 能接受的每一种实参，模板 2 是否也能接受？如果模板 2 能从模板 1 的任意实例推导成功，说明模板 2 至少一样通用，即模板 1 至少一样特殊。

¶3 用于比较的类型取决于语境：

- ¶3.1 函数调用：有对应实参的函数形参类型（脚注：默认实参不算实参）；
- ¶3.2 调用转换函数：转换函数模板的返回类型；
- ¶3.3 其他语境：函数类型。

¶4 形参模板中的每个类型与实参模板中对应的类型，分别作为 `P` 和 `A`。

### 比较前的变换（¶5–¶7）

- ¶5 `P` 是引用类型时，用被引用类型代替；`A` 也是如此。
- ¶6 若 `P` 和 `A` 原本都是引用，记下哪个更 cv 限定（用于 ¶9）；否则视为同等。
- ¶7 去掉 `P`、`A` 的顶层 cv。

### 推导与至少一样特殊（¶8–¶11）

¶8 若 `A` 来自函数形参包而 `P` 不是包，推导失败。否则按 [[temp.deduct.type]] 推导；`P` 是函数形参包时，与实参模板剩余的每个形参类型逐一比较。**对某个类型推导成功，则实参模板中的该类型被认为至少与形参模板中的该类型一样特殊。**

```cpp run ok title="variadic_order.cpp"
#include <cstdio>
template<class... Args>           void f(Args...)     { std::puts("#1"); }
template<class T1, class... Args> void f(T1, Args...) { std::puts("#2"); }
template<class T1, class T2>      void f(T1, T2)      { std::puts("#3"); }

int main() {
    f();          // #1：只有 #1 可行
    f(1, 2, 3);   // #2：#2 比 #1 更特殊
    f(1, 2);      // #3：非变参的 #3 比变参的 #1、#2 更特殊
}
```

¶9 若某个类型在变换后完全相同，且 `P`、`A` 原本都是引用，还要再看两点：

- ¶9.1 实参模板中的是左值引用而形参模板中的不是，则形参类型不被认为至少一样特殊；
- ¶9.2 否则，若实参模板中的类型比形参模板中的更 cv 限定，形参类型不被认为至少一样特殊。

```cpp run ok title="ref_order.cpp"
#include <cstdio>
template<class T> void q(T&&) { std::puts("q(T&&)"); }
template<class T> void q(T&)  { std::puts("q(T&)"); }

int main() {
    int i = 0;
    q(i);    // q(T&)：两者都推导出 q(int&)，转换序列相同；偏序 ¶9.1 认为 T& 更特殊
    q(0);    // q(T&&)：q(T&) 不可行
}
```

¶10 [[g:at-least-as-specialized|**至少一样特殊**]]：如果对用于定序的每一对类型，`F` 中的都至少与 `G` 中的一样特殊，就说 `F` 至少与 `G` 一样特殊。如果 `F` 至少与 `G` 一样特殊，而 `G` 不是至少与 `F` 一样特殊，就说 `F` 比 `G` **更特殊**（more specialized）。

¶11 是决胜规则：若按上述方法 `F` 与 `G` 互相至少一样特殊，而 `G` 有一个尾随函数形参包（`F` 中没有与之对应的形参），且 `F` 没有尾随函数形参包，则 `F` 更特殊。（这处理的是只有一个实参时 `f(T)` 与 `f(T, Args...)` 的比较，那个包没有对应实参，不参与 ¶3.1 的比较。）

### 未使用的模板形参可以没有值（¶12–¶13）

¶12 一般而言，推导要求所有模板形参都有值；但在偏序中，一个模板形参只要不出现在用于定序的类型中，就可以没有值。注 2 指出，在非推导语境中使用的模板形参也算用到。

```cpp ok
template <class T> T f(int);            // #1
template <class T, class U> T f(U);     // #2
void g() {
    f<int>(1);                          // 调用 #1
}
```

两者都可行（#1：`f<int>(int)`；#2：`f<int, int>(int)`）。比较时只看有实参的形参类型：#1 是 `int`，#2 是 `U`。用 #1 的 `int` 推导 #2 的 `U`：成功（`T` 未出现，不需要值）；反向用合成类型 `Unique` 推导 #1 的 `int`：失败。#1 更特殊。

¶13（注 3）含模板形参包的函数模板的偏序，与包推导出的实参个数无关。

```cpp run ok title="pack_order.cpp"
#include <cstdio>
template<class...> struct Tuple { };
template<class... Types>             void g(Tuple<Types...>)          { std::puts("#1"); }
template<class T1, class... Types>   void g(Tuple<T1, Types...>)      { std::puts("#2"); }
template<class T1, class... Types>   void g(Tuple<T1, Types&...>)     { std::puts("#3"); }

int main() {
    g(Tuple<>());              // #1
    g(Tuple<int, float>());    // #2
    g(Tuple<int, float&>());   // #3
    g(Tuple<int>());           // #3：Types 为空，#2、#3 都匹配，#3 更特殊
}
```

最后一行值得注意：`Tuple<int>` 中 `Types&...` 推导为空包，与 `Types...` 推导为空包看起来没有区别。但偏序不看具体推出了几个，只看模式：`Types&...` 比 `Types...` 更特殊。

## 从函数声明推导（[temp.deduct.decl]）

¶1 在 *declarator-id* 指称函数模板特化的声明中，要通过推导确定它指哪个特化。具体用于：

- 显式实例化（`template void f(int*);`）；
- 显式特化（`template<> void f(int*);`）；
- 某些友元声明（`friend void f<>(T*);`）；
- 判断解分配函数模板的特化是否匹配某个放置分配函数（[[basic.stc.dynamic.deallocation]]、[[expr.new]]）。

`P` 是候选函数模板的类型，`A` 是声明中的函数类型（或匹配放置分配函数的解分配函数类型），按 [[temp.deduct.type]] 推导。

¶2 若在考虑偏序（[[temp.func.order]]）之后，没有匹配或有多个匹配，推导失败；在声明的情形下程序非良构。

```cpp error
template<class T> void f(T, int);
template<class T> void f(int, T);
template<> void f(int, int);   // error: 两个模板都匹配，偏序也分不出——二义
```

```cpp ok
template<class T> void f(T) { }      // #1
template<class T> void f(T*) { }     // #2
template<> void f(int*) { }          // 两者都匹配，#2 更特殊：这是 f<int>（#2 的特化）
template void f(double*);            // 同理：实例化 #2 的 f<double>
```

这正是 [[temp.expl.spec]] 中 Dimov/Abrahams 例子的机制：特化属于哪个模板，取决于声明时哪些模板可见。

[[temp.deduct.type#10]] 对这里的推导有一条特殊调整：顶层形参是转发引用 `T&&`、而 `A` 是左值引用时，把 `P` 改为 `T`，于是 `template<> void f(int&)` 能被识别为 `template<class T> void f(T&&)` 的 `f<int&>`。

## 实现视角

!!! impl "SFINAE 与编译器"
    - 编译器在代入时开启一个 SFINAE 陷阱（Clang 的 `SFINAETrap`）来实现 SFINAE：直接语境中产生的诊断被捕获并转为推导失败，而不输出。一旦进入实例化类模板、生成隐式成员等非直接语境的工作，陷阱被挂起，诊断照常输出。这正对应 ¶8 注 7。
    - 被剔除的候选会在 "no matching function" 错误的附注中列出，并说明原因（"substitution failure [with T = int]: ..."），这是调试 SFINAE 的主要手段。
    - 大量 SFINAE 重载（尤其是基于 `std::enable_if` 的）代价很高：每个候选都要做一次完整的代入。C++20 的约束（`requires`）在 ¶5 第 4 步检查，且概念的满足性结果会被缓存，通常更快，诊断也更好。

## 陷阱

!!! pitfall "写在签名里不等于在直接语境中"
    `typename Wrap<T>::type` 写在签名里，但错误发生在 `Wrap<T>` 的类体里，不在直接语境中，所以是硬错误。同理，`decltype(T{})` 若 `T` 的默认构造函数是隐式定义且其定义非良构（例如某个成员不可默认构造），隐式定义的生成也不在直接语境中。

!!! pitfall "返回类型推导（`auto f()`）不参与 SFINAE"
    `template<class T> auto size_of(const T& c) { return c.size(); }` 的返回类型需要实例化函数体才能得到，而函数体不在直接语境中。若用 `size_of(42)` 调用（且有其他候选），会因实例化函数体而硬错误。想要 SFINAE，就写 `-> decltype(c.size())`，或者用 `requires`。

!!! pitfall "noexcept 说明符不是代入位置"
    `noexcept(noexcept(T::f()))` 中的错误不会让推导失败，而是在选中后实例化 noexcept 说明符时报硬错误（¶7 注 4）。

!!! pitfall "代入顺序很重要"
    把返回类型从前置改成尾置（或反之），可能让一个原本 SFINAE 的模板变成硬错误（¶7 例 6）。重构签名时要注意。

## 思考题

!!! question "思考题 1"
    以下哪些调用会导致硬错误？
    ```cpp
    template<class T> struct Bad { static_assert(sizeof(T) == 0); using type = int; };
    template<class T> typename Bad<T>::type a(T);     void a(...);
    template<class T> decltype(Bad<T>{}) b(T);        void b(...);
    template<class T, class = typename T::type> void c(T); void c(...);
    void t() { a(1); b(1); c(1); }
    ```

<details markdown="1">
<summary>答案</summary>

`a(1)`：代入 `Bad<int>::type` 需要实例化 `Bad<int>`，`static_assert` 在类体中失败，不在直接语境中，是硬错误。
`b(1)`：`Bad<int>{}` 需要完整类型，同样实例化 `Bad<int>`，是硬错误。
`c(1)`：`int::type` 直接写在模板形参列表（代入位置 ¶7.3）中，属于在限定名中使用非类类型（¶11.3），推导失败，选 `c(...)`，没有错误。
</details>

!!! question "思考题 2"
    ```cpp
    template<class T> void f(T*, const T&);   // #1
    template<class T> void f(T, T&);          // #2
    ```
    对 `int i; f(&i, i);`，哪个被调用？

<details markdown="1">
<summary>答案</summary>

#1：`T = int`，形参 `(int*, const int&)`。#2：第一个形参推导 `T = int*`，第二个从 `i`（`int` 左值）推导 `T = int`，两者冲突，#2 推导失败。所以只有 #1 可行，调用 #1。这道题考的是：偏序只在两个模板都可行时才起作用，要先看推导是否成功。
</details>

!!! question "思考题 3"
    为什么 ¶8 要把访问检查明确纳入代入过程？如果不这样，会出现什么问题？

<details markdown="1">
<summary>答案</summary>

trait 如 `std::is_constructible<T, Args...>` 通常基于 `decltype(T(std::declval<Args>()...))` 的 SFINAE 实现。若访问检查不在代入过程中，私有构造函数会让检测表达式成立（因为不检查访问），trait 报告可构造，而真正构造时却报访问错误；或者反过来，访问错误在检测时作为硬错误出现，trait 根本无法用于具有私有构造函数的类型。把访问检查纳入代入，可访问就成了有效的一部分，trait 才能给出与真实代码一致的答案。注意，访问是在代入发生的语境中检查的，所以同一个 trait 在类的友元里和在外部可能给出不同答案。
</details>

## 小结

| 阶段 / 概念 | 出处 | 要点 |
|---|---|---|
| 显式实参代入 + [dcl.fct] 调整 | ¶2–¶3 | `f<int>` 与 `f<const int>` 同类型、不同函数 |
| 未推导的用默认模板实参 | ¶5 | 函数默认实参不能推导模板形参 |
| 约束检查、非依赖形参转换检查 | ¶5 | 在代入函数类型之前 |
| 推导代入位置 | ¶7 | 函数类型（不含 noexcept）、`explicit(bool)`、模板形参、部分特化实参 |
| 代入按词法顺序，遇失败即停 | ¶7 | 不同声明顺序不同 → {{ifndr}} |
| 无效类型/表达式 → 推导失败（SFINAE） | ¶8 | 仅限直接语境；访问检查包含在内 |
| 直接语境不含：lambda 体、单独实例化的构造、实例化副作用、语句 | ¶8–¶9 | 那里的错误是硬错误 |
| 取地址：从目标类型推导 | funcaddr | 无目标则只能显式指定 |
| 转换函数模板：返回类型对目标类型 | conv | P/A 调整与调用推导相反 |
| 偏序：变换后双向推导 | partial | `T&` 比 `T&&` 更特殊；非变参比变参更特殊 |
| 声明 → 特化：推导 + 偏序，无匹配或二义则非良构 | decl | — |
