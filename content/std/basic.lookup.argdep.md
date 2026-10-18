---
title: 实参依赖查找（ADL）
summary: 对无限定函数调用 f(args)，除了从调用处往外找，还要到实参类型的"关联命名空间"里找、并收集关联类的友元；本页讲清何时触发、何时被抑制、关联实体如何计算，以及隐藏友元、swap 两步法、CPO/niebloid、运算符、f<T>(x)、模块中的 ADL。
status: done
papers: P0846R0, P1787R6
related: basic.lookup, basic.lookup.unqual, over.match.oper, temp.dep.candidate, temp.names, class.friend, namespace.def, module.reach, module.context, customization.point.object, alg.func.obj
tags: 名字查找, ADL, 重载, 模块, 泛型编程
updated: 2026-10-17
---

```cpp
#include <iostream>
#include <string>
int main() {
    std::string s = "hi";
    std::cout << s;           // 调用的是 std::operator<<(std::ostream&, const std::string&)
}
```

这段代码里没有 `using namespace std;`，`operator<<` 也不是 `std::ostream` 的成员（`string` 的输出运算符是命名空间作用域的函数模板）。在全局作用域的 `main` 中做无限定查找，根本找不到 `std::operator<<`。它能工作，靠的就是**实参依赖查找**（argument-dependent lookup，ADL，又称 Koenig 查找）：调用的实参类型属于 `std`，于是 `std` 也被搜索。

没有 ADL，运算符重载在命名空间里几乎不可用——你得写 `std::operator<<(std::cout, s)`。ADL 背后的理念常被概括为**接口原则**（interface principle）：一个类的接口不仅是它的成员，还包括与它在同一命名空间中、以它为参数的非成员函数（`swap`、`operator==`、`begin`/`end`……）。ADL 让这些函数用起来和成员一样自然。

代价是：ADL 让"调用哪个函数"依赖于实参类型来自哪里，可能找到你**没打算**调用的函数。本页先读规则（¶1–¶6），再讲围绕它形成的惯用法与陷阱。

## 何时进行 ADL（¶1）

¶1 当函数调用（[[expr.call]]）的 *postfix-expression* 是一个 *unqualified-id*，并且对它的**无限定查找**（[[basic.lookup.unqual]]）**没有**找到以下任何一种：

- ¶1.1 **类成员**的声明；
- ¶1.2 **栖身于块作用域的函数声明**；
- ¶1.3 **非函数、非函数模板**的声明；

那么该名字的查找结果还要**加上**在一组"关联命名空间"中的实参依赖查找的结果。关联命名空间取决于实参类型（对类型模板模板实参，还取决于模板实参所在的命名空间），见 ¶3–¶4。

注意 ADL 的结果是**并入**（includes）而非替代：无限定查找找到的函数与 ADL 找到的函数合成一个重载集，再交给重载决议。

### 抑制 ADL 的五种方式

| 写法 | 为什么没有 ADL |
|---|---|
| `N::f(x)` | 不是 *unqualified-id*（限定名） |
| `(f)(x)` | *postfix-expression* 是带括号的表达式，不是 *unqualified-id* |
| 在成员函数里调用，且类（或基类）有名为 `f` 的成员 | ¶1.1：找到了类成员 |
| 在块作用域中声明了 `void f(...);` | ¶1.2：找到了块作用域函数声明 |
| 无限定查找找到变量、函数对象、类型等 | ¶1.3：找到了非函数（例如 niebloid、CPO） |

```cpp run error
namespace N {
    struct S { };
    void f(S);
}

void g() {
    N::S s;
    f(s);             // OK：ADL 找到 N::f
    (f)(s);           // error: 括号抑制 ADL，无限定查找找不到 f
}

void h() {
    N::S s;
    void f(int);      // 块作用域函数声明
    f(s);             // error: ¶1.2 抑制 ADL，只剩 f(int)，N::S 不能转换为 int
}

void k() {
    N::S s;
    int f = 0;        // 非函数
    f(s);             // error: ¶1.3 抑制 ADL；int 不能被调用
}

struct M {
    void f(int);
    void m() {
        f(N::S{});    // error: ¶1.1 找到类成员 M::f，不做 ADL
    }
};
```

!!! lawyer "块作用域的 using 声明不抑制 ADL"
    `void t() { using std::swap; swap(a, b); }` 中，无限定查找在块作用域找到的是一个 *using-declarator*。按 [[basic.lookup#3]]，单次搜索会把它**替换**为它指名的声明——`std::swap` 的那些函数模板，它们栖身于命名空间 std，而不是块作用域。因此 ¶1.2 不适用，ADL 照常进行。这正是"swap 两步法"能工作的规范依据（见下文）。而块作用域里的 `extern void swap(T&, T&);` 是块作用域函数声明，会抑制 ADL。

¶1 末尾的例子之外，标准例 3（¶6）展示了 ¶1.2 的一个实用后果：

```cpp run ok
namespace NS {
    class T { };
    void f(T);
    void g(T, int);
}
NS::T parm;
void g(NS::T, float);
int main() {
    f(parm);                      // OK：ADL 找到 NS::f
    extern void g(NS::T, float);  // 块作用域函数声明
    g(parm, 1);                   // OK：调用 ::g(NS::T, float)；NS::g(T, int) 本是更好的匹配，但 ADL 被抑制
}
```

## 语法判定先于 ADL（¶2）

¶2 注 1 提醒：判断一个表达式**是不是**函数调用的 *postfix-expression*，用的是普通查找规则，ADL 不参与解析。两个推论：

**其一，`f<T>(x)`。** 名字后面跟 `<` 时，要先决定它是不是模板名（[[temp.names#7]]）。C++20 起（P0846R0），若无限定查找**什么也没找到**，或找到了**一个或多个函数**，`<` 也被当作模板实参列表的开始；于是 `f<T>(x)` 成为一个调用，ADL 可以找到真正的函数模板：

```cpp run error
int h;
void g();
namespace N {
    struct A {};
    template <class T> int f(T);
    template <class T> int g(T);
    template <class T> int h(T);
}

int x = f<N::A>(N::A());   // OK：f 什么也没找到，按模板名处理，ADL 找到 N::f
int y = g<N::A>(N::A());   // OK：g 找到一个函数（非模板），也按模板名处理
int z = h<N::A>(N::A());   // error: h 找到变量，h< 不开始模板实参列表
```

C++20 之前，`x` 和 `y` 两行都会被解析成 `(f < N::A) > (N::A())` 之类的比较表达式而出错——所以那时 `std::get<0>(t)` 必须写限定名或先 `using std::get;`。现在可以写 `get<0>(t)`：

```cpp run ok
#include <tuple>
int main() {
    std::tuple<int, double> t{1, 2.0};
    return get<0>(t) - 1;      // C++20 起 OK：get 未找到 → 模板名；ADL 在 std 中找到 std::get
}
```

**其二，不是调用就没有 ADL。**

```cpp
typedef int f;
namespace N {
    struct A {
        friend void f(A &);
        operator int();
        void g(A a) {
            int i = f(a);    // f 是 typedef：这是函数式类型转换 int(a)，不是调用
        }
    };
}
```

`f(a)` 在语法上是显式类型转换（[[expr.type.conv]]），ADL 无从谈起，友元 `f` 不会被找到。

## 关联实体（¶3）

¶3 对调用中的每个实参类型 T，有一组（可能为空的）[[g:associated-entities|关联实体]]（associated entities）。它**完全**由实参的类型（以及类型模板模板实参）决定；**指定类型时用到的 typedef 名与 using 声明不起作用**——只看类型本身，不看你怎么拼写它。

| T 的种类 | 关联实体 |
|---|---|
| ¶3.1 `std::meta::info` {{c++26}} | 仅枚举类型 `std::meta::operators` |
| ¶3.2 其他基本类型（`int`、`double`、`std::nullptr_t`、`void`……） | 空 |
| ¶3.3 类类型（含联合） | 类本身；它是成员时，所属的类；若是完整类型，它的直接与间接基类 |
| ¶3.3 类模板特化，**另加** | 类型模板形参所对应实参类型的关联实体；用作类型模板模板实参的模板；用作类型模板模板实参的成员模板所属的类 |
| ¶3.4 枚举类型 | 枚举本身；它是类成员时，所属的类 |
| ¶3.5 指向 U 的指针、U 的数组 | U 的关联实体 |
| ¶3.6 函数类型 | 各参数类型与返回类型的关联实体 |
| ¶3.7 指向类 X 的成员函数的指针 | 参数类型、返回类型的关联实体，加上 X 的关联实体 |
| ¶3.8 指向类 X 的数据成员的指针 | 成员类型的关联实体，加上 X 的关联实体 |

另外，若实参是一个**重载集**（或其地址），关联实体是集合中每个成员的关联实体之并，即其参数类型与返回类型的关联实体；若该重载集用 *template-id* 命名，还要加上其模板模板实参以及类型模板实参的关联实体。

注 3：**常量模板实参**、变量模板模板实参、概念模板实参不贡献关联实体。

### 逐项说明

**¶3.1（C++26）。** `std::meta::info` 是 `decltype(^^int)` 的**类型别名**，本身是一个基本类型（[[basic.fundamental]]）。若无特殊规则，以反射值为实参的调用不会关联任何命名空间，`members_of(r, ctx)` 这样的无限定调用就找不到 `std::meta::members_of`。标准于是规定它的关联实体是 `std::meta::operators` 这个枚举——该枚举位于 `std::meta`，从而把 `std::meta` 变成关联命名空间。C++23 及之前没有反射，不存在此规则。

**¶3.2 基本类型没有关联实体**——所以 `swap(i, j)`（`int`）不会找到 `std::swap`，两阶段查找中 `g(1)` 在实例化时找不到定义点之后才声明的 `g`。

**¶3.3 类：所属类与基类。** "所属的类"意味着嵌套类的实参会把**外围类的友元**带进来；"完整类型的基类"意味着在基类中定义的隐藏友元对派生类对象也可用。

```cpp run error
namespace N {
    struct Out {
        struct In { };
        enum class E { a };
        friend void p(In) { }        // Out 的友元，参数是嵌套类
        friend void q(E) { }
    };
}
namespace L {
    struct Base { friend void fb(const Base&) { } };
    struct D : Base { };
    struct Inc;                      // 不完整
}

void t(L::Inc* pi) {
    p(N::Out::In{});    // OK：In 的关联实体含所属类 Out → Out 的友元 p 被找到
    q(N::Out::E::a);    // OK：¶3.4 枚举是类成员 → 所属类 Out
    fb(L::D{});         // OK：D 完整，基类 Base 是关联实体 → Base 的友元
    fb(*pi);            // error: Inc 不完整，基类不计入（这里它根本没有定义）
}
```

**¶3.3 类模板特化：模板实参。** 这是 ADL 最容易"出人意料"的来源：`std::vector<N::X>` 把 `N` 和 `std` 都变成关联命名空间。更进一步，实参的实参也算——`std::function<void(N::X)>` 的模板实参是函数类型 `void(N::X)`，按 ¶3.6 其参数类型 `N::X` 带来 N。

```cpp run ok
#include <functional>
namespace N {
    struct X {};
    void f(std::function<void(X)>);
    void h(void (*)(X));
    void cb(X);
}
namespace O { template<class T> struct Box {}; }
namespace P { struct Y {}; void z(O::Box<Y>); }

void t() {
    std::function<void(N::X)> fn;
    f(fn);                 // OK：模板实参 void(N::X) → 参数类型 N::X → N
    h(&N::cb);             // OK：实参是重载集 {N::cb} 的地址 → cb 的参数类型 N::X → N
    z(O::Box<P::Y>{});     // OK：Box<P::Y> 的模板实参 P::Y → P
}
```

**typedef 不起作用：**

```cpp run error
namespace N { struct X {}; }
namespace T {
    using Alias = N::X;
    void f(Alias);
}
void t() {
    T::Alias a;
    f(a);        // error: a 的类型是 N::X，关联命名空间只有 N；T 与别名无关
}
```

## 关联命名空间与 ADL 找到什么（¶4）

¶4 调用的[[g:associated-namespaces|关联命名空间]]是：各关联实体的**最内层外围非内联命名空间**，以及这些命名空间的**内联命名空间集**（[[namespace.def]]）中的每个元素。

"非内联"与"内联命名空间集"两条配合起来，使库的版本化内联命名空间对 ADL 透明：libc++ 的 `std::vector` 实际上是 `std::__1::vector`，其最内层外围非内联命名空间是 `std`，再加上 std 的内联命名空间集（含 `__1`）——无论函数声明在 `std` 还是 `std::__1`，都能找到。

对名字 N，ADL 找到满足下列任一条件的**函数与函数模板**声明：

- ¶4.1 在任一关联命名空间中对 N 的**搜索**所找到的；
- ¶4.2 被声明为关联实体中**某个具有可达定义的类**的**友元**的；
- ¶4.3 （模块）被导出、附属于具名模块 M、**不**出现在查找点所在的翻译单元中，并且与某个附属于 M 的关联实体声明有相同的最内层外围非内联命名空间。

### ¶4.1：是"搜索"，不是"无限定搜索"

在关联命名空间中做的是**搜索**（单次搜索），不是无限定搜索：关联命名空间中的 **using 指令被忽略**，外层命名空间也不看。

```cpp run error
namespace M { }
namespace N {
    using namespace M;     // ADL 不会顺着它进入 M
    struct S { };
}
namespace M { void g(N::S); }

void t() {
    g(N::S{});    // error: 关联命名空间只有 N；在 N 中的搜索不跟随 using 指令
}
```

另外 ADL 只收集**函数与函数模板**——即使关联命名空间中名为 N 的是一个变量或类型，也会被忽略（不会造成二义）。

### ¶4.2：友元与"隐藏友元"

友元声明不绑定名字（[[class.friend#10]]、[[dcl.meaning.general#2]]）：类内的 `friend void f(X);` 声明了外围命名空间的函数 `f`，但这个名字在命名空间中"不可见"——无限定查找和限定查找都找不到它，直到命名空间作用域出现一个匹配的声明。¶4.2 让 ADL 能找到它：只要该类是关联实体、且其定义可达。

只在类内声明（通常就在类内定义）、不在命名空间作用域重新声明的友元函数，称为**隐藏友元**（hidden friend）。它**只能**通过 ADL 被找到：

```cpp run error
#include <ostream>
namespace N {
    class P {
        int v = 0;
        friend bool operator==(const P&, const P&) = default;
        friend std::ostream& operator<<(std::ostream& os, const P& p) { return os << p.v; }
        friend void touch(P&) { }
    };
}
void t(std::ostream& os) {
    N::P a, b;
    os << a;           // OK：ADL（N::P 的友元）
    (void)(a == b);    // OK
    touch(a);          // OK
    N::touch(a);       // error: 限定查找找不到隐藏友元
}
```

**为什么提倡隐藏友元？**

1. **重载集更小。** 命名空间作用域的 `operator==`、`operator<<` 会参与该命名空间内**每一次**同名运算符的查找；标准库这样的大命名空间里可能有上百个 `operator<<`，重载决议要逐个尝试，拖慢编译、让错误信息冗长。隐藏友元只在实参确实涉及该类时才出现。
2. **不会通过隐式转换被意外选中。** 隐藏友元只有当实参类型的关联类**就是**这个类时才被找到；一个仅仅**能转换成**该类的类型找不到它：

```cpp run error
namespace units {
    struct Meters { double v; Meters(double d) : v(d) {} };
    struct ToMeters { operator Meters() const { return 1.0; } };
    void show(Meters);                                  // 命名空间作用域

    struct Feet {
        double v; Feet(double d) : v(d) {}
        friend void show2(Feet) { }                     // 隐藏友元
    };
    struct ToFeet { operator Feet() const { return 1.0; } };
}
void t() {
    units::ToMeters m;
    show(m);                 // OK：ADL 在 units 中找到 show(Meters)，经用户定义转换调用
    units::ToFeet f;
    show2(units::Feet(1.0)); // OK
    show2(f);                // error: ToFeet 的关联类不含 Feet，show2 找不到
}
```

3. **访问私有成员**：友元天然有访问权，无需公开 getter。

### ¶4.3 与 ¶5：模块中的 ADL

模块让"名字是否先于查找点"与"声明是否可达"分离（[[basic.lookup#2]]、[[module.reach]]）。¶4.3 规定：即使一个函数在当前 TU 中**不先于**调用点（例如它所在的命名空间 R 根本没被导出或在此处不可见），只要它被导出、附属于模块 M、且与某个附属于 M 的关联实体在同一命名空间，ADL 就能找到它。

标准例 2（三个翻译单元，改写注释）：

```cpp title="TU1: 模块 M"
export module M;
namespace R {
    export struct X {};
    export void f(X);
}
namespace S {
    export void f(R::X, R::X);
}
```

```cpp title="TU2: 模块 N"
export module N;
import M;
export R::X make();
namespace R { static int g(X); }
export template<typename T, typename U> void apply(T t, U u) {
    f(t, u);
    g(t);
}
```

```cpp title="TU3: 模块单元 Q"
module Q;
import N;
namespace S {
    struct Z { template<typename T> operator T(); };
}
void test() {
    auto x = make();     // OK：decltype(x) 是模块 M 中的 R::X
    R::f(x);             // error: R 与 R::f 在此都不"先于"（M 未被导入）
    f(x);                // OK：¶4.3——R::f 被导出、附属于 M，与关联实体 R::X 同在 R
    f(x, S::Z());        // error: S 虽是关联命名空间，但 M 中的 S::f 与附属于 M 的关联实体
                         //        不在同一命名空间（S::Z 附属于 Q，不是 M）
    apply(x, S::Z());    // error: 实例化上下文中 S::f 可见，但 R::g 具有内部链接，
                         //        不能在 TU2 之外使用
}
```

¶4 最后一句针对**依赖名**：模板中依赖的调用名，除了在模板定义处之外，还要从**实例化上下文**（[[module.context]]）中的每个点做上述查找；此时额外忽略那些出现在其他 TU、附属于全局模块、并且被丢弃（[[module.global.frag]]）或具有内部链接的声明。这是两阶段查找中"第二阶段只做 ADL"在模块世界中的精确表述。[[temp.dep.candidate]] 进一步规定：若考虑所有 TU 中的外部链接函数会得到不同（更好）的匹配或使调用非良构，则程序 {{ifndr}}。

## 关联命名空间可以与普通查找重叠（¶6）

¶6 注 4：关联命名空间可以包含无限定查找已经考虑过的命名空间。两条路径找到同一个声明不会造成二义——它们只是同一重载集里的同一个函数。上面 `NS::f` 的例子就是如此（若 `main` 在 NS 内部，f 会被两种查找同时找到）。

## 惯用法一：std::swap 两步法

泛型代码想交换两个 `T`：

- 写 `std::swap(a, b)`：限定名，没有 ADL，用户为自己类型在其命名空间里写的高效 `swap` 被**绕过**；
- 写 `swap(a, b)`：若 `T` 是 `int`，没有关联命名空间，又找不到 `std::swap`；
- **两步法**：

```cpp run ok
#include <utility>
namespace N {
    struct Big { int d[100]; };
    void swap(Big&, Big&) noexcept { }      // 自定义的高效 swap
}

template<class T>
void my_algo(T& a, T& b) {
    using std::swap;     // 第一步：让无限定查找能找到 std::swap 作为后备
    swap(a, b);          // 第二步：无限定调用；ADL 加入 T 所在命名空间的 swap
}

int main() {
    N::Big a, b;
    my_algo(a, b);       // 选 N::swap（非模板，比 std::swap 模板更优）
    int i = 1, j = 2;
    my_algo(i, j);       // 选 std::swap
}
```

能工作的三个前提：块作用域的 using 声明不抑制 ADL（见 ¶1 的 lawyer 框）；重载集同时含 `std::swap` 与 `N::swap`；重载决议中非模板优于模板、更特化的模板优于更泛的模板。

这个"咒语"容易写错（忘了 `using`、写成 `std::swap`），C++20 于是提供了 `std::ranges::swap`：一个**定制点对象**，内部替你完成两步法。

## 惯用法二：定制点对象（CPO）与 niebloid

ADL 有两个系统性问题：

1. **劫持（hijacking）**：泛型库里每个无限定调用都可能被实参类型所在命名空间中**碰巧同名**的函数劫持；
2. **意外二义**：库自己的函数被无限定调用时，ADL 可能在另一个关联命名空间里找到同样好的候选。

```cpp run error
#include <vector>
#include <iterator>
#include <algorithm>
namespace N {
    struct X { bool operator==(const X&) const = default; };
    template<class It> int distance(It, It) { return 0; }     // 用户自己的 distance
    template<class It, class T> It find(It b, It, const T&) { return b; }
}
int main() {
    std::vector<N::X> v(3);
    auto n  = distance(v.begin(), v.end());     // error: 二义：std::distance 与 N::distance
    auto it = find(v.begin(), v.end(), N::X{}); // error: 二义：std::find 与 N::find
}
```

`v.begin()` 的类型是 `std::vector<N::X>` 的迭代器（libc++ 中是 `std::__wrap_iter<N::X*>`），模板实参 `N::X*` 把 N 带进关联命名空间，std 本来就是——两个同样好的函数模板，二义。

**定制点对象**（customization point object，[[customization.point.object]]）的思路：把库的入口做成**对象**而不是函数。

- 无限定查找找到的是一个**变量**（非函数），按 ¶1.3 **抑制 ADL**——调用者无法被劫持；
- 对象不能重载，ADL 也永远不会"找到"它（ADL 只收集函数），所以它不会与别处的同名函数形成二义；
- 对象的 `operator()` 内部再以受控的方式做 ADL（例如 `std::ranges::begin` 会查找实参的成员 `begin()` 或经 ADL 找到的非成员 `begin`，并用"毒丸"重载 `void begin(auto&) = delete;` 之类的手段阻止无限定查找找到 `std::begin`），并检查语义要求（返回类型须满足迭代器概念等）。

`std::ranges` 中的**算法**（`find`、`sort`……）也是这种对象，俗称 **niebloid**（得名于 Eric Niebler）。C++20 只规定它们"不被 ADL 找到、被无限定查找找到时抑制 ADL"，未要求必须是对象；当前草案（[[alg.func.obj]]）直接把它们定义为**算法函数对象**（algorithm function object），即一种 CPO：

```cpp run ok
#include <ranges>
#include <vector>
#include <algorithm>
void foo() {
    using namespace std::ranges;
    std::vector<int> vec{1, 2, 3};
    auto it = find(begin(vec), end(vec), 2);   // std::ranges::find：对象，抑制 ADL，不会选到 std::find
    (void)it;
}
```

## 惯用法三：运算符与 ADL

运算符表达式 `a @ b` 不能加括号来抑制 ADL，也不存在"限定"写法。[[over.match.oper#3]] 规定其**非成员候选**是"对 `operator@` 做无限定查找（含 ADL），**忽略所有成员函数**"。与具名调用的关键差别：

- 具名调用中，无限定查找找到类成员会**抑制** ADL（¶1.1）；
- 运算符查找中，成员函数被忽略，ADL 总会进行；成员候选另由"在 T1 的作用域中搜索 `operator@`"产生。

一个经典陷阱：无限定查找"找到就停"，所以**命名空间里只要声明了任何 `operator<<`，外层的 `operator<<` 就看不见了**，只能靠 ADL：

```cpp run error
#include <iostream>
#include <vector>
std::ostream& operator<<(std::ostream& os, const std::vector<int>&) { return os; }
struct G {};
std::ostream& operator<<(std::ostream& os, G) { return os; }

namespace N {
    struct Z {};
    std::ostream& operator<<(std::ostream& os, Z);   // 有了这个，查找在 N 停下
    void f(const std::vector<int>& v, G g) {
        std::cout << g;   // OK：G 在全局命名空间，全局是关联命名空间 → ADL 找到 ::operator<<
        std::cout << v;   // error: 无限定查找停在 N；ADL 只看 std（vector<int>、ostream 的命名空间）
    }
}
```

教训：**为某个类型定义的运算符，应该放在该类型所在的命名空间（最好是隐藏友元）**。给 `std` 中的类型（如 `std::vector<int>`）在全局写运算符，本质上依赖无限定查找"刚好能看到"，一换命名空间就失效；而往 `std` 里添加这种声明又是标准禁止的（[[namespace.std]]）。

## 更多意外

```cpp run ok
#include <iostream>
#include <string>
#include <iterator>
int main() {
    endl(std::cout);              // OK：std::cout 的类型在 std → ADL 找到 std::endl
    std::string arr[3];
    auto b = begin(arr);          // OK：数组 → 元素类型 std::string → std → std::begin
    (void)b;
}
```

- `endl(std::cout)`、`begin(arr)` 无需 `std::`——ADL 来自实参类型，而不是你"使用了标准库"。
- **lambda 闭包类型**是类类型，其最内层外围命名空间就是 lambda 出现处的命名空间，所以传 lambda 作实参也会关联该命名空间。
- `f(nullptr)`、`f(0)`、`f(1.0)` 永远没有 ADL。
- **常量模板实参不贡献**：`std::array<N::X, 3>` 关联 N（类型实参），但 `std::integral_constant<N::E, N::E::a>` 的 `N::E::a` 不贡献（类型实参 `N::E` 仍然贡献 N）。

!!! impl "实现视角"
    - Clang 在 `Sema::ArgumentDependentLookup` 中实现 ADL，用 `FindAssociatedClassesAndNamespaces` 按 ¶3 计算关联类与命名空间；友元通过"在命名空间中存在但对普通查找不可见"的声明标记实现（¶4.2）。
    - 模块：Clang 在实例化时依据实例化上下文计算 ADL 可见集；¶4 中"忽略被丢弃的全局模块片段声明"使 `#include` 进全局模块片段但未被引用的函数在其他 TU 中对 ADL 不可见（[[temp.dep.candidate]] 例 4）。
    - ADL 对编译时间有实际影响：大量命名空间级运算符模板会让每个 `<<` 都触发昂贵的重载决议。这也是 C++20 起标准库新组件（如 ranges 的视图与迭代器类型）大量把运算符规定为隐藏友元的动机之一。

!!! history "历史与演进"
    - **C++98**：ADL 进入标准（最初为运算符设计，后推广到所有无限定函数调用），俗称 Koenig 查找。
    - **C++11**：内联命名空间；关联命名空间包括内联命名空间集。
    - **C++20**：P0846R0 让 `f<T>(x)` 在找不到模板或只找到函数时也按模板名解析，从而可以借 ADL 调用函数模板并显式指定模板实参；模块引入 ¶4.3 与实例化上下文中的 ADL；ranges 引入 CPO 与 niebloid。
    - **C++23**：P1787R6 改用"搜索"、"关联实体"重新表述本节；明确块作用域函数声明（而非 using 声明）才抑制 ADL。
    - **C++26**：¶3.1 为 `std::meta::info` 关联 `std::meta`；niebloid 被规范为算法函数对象（[[alg.func.obj]]）。

## 陷阱

!!! pitfall "以为限定调用和无限定调用只是写法不同"
    `std::swap(a, b)` 与 `using std::swap; swap(a, b)` 可能调用不同的函数；`std::begin(r)` 与 `std::ranges::begin(r)` 的语义也不同。在泛型代码里选择调用形式就是在选择查找规则。

!!! pitfall "被模板实参拉进来的命名空间"
    `std::vector<mylib::Widget>` 会让 mylib 中所有同名函数参与 `std` 算法的无限定调用；反之 `mylib::Container<std::string>` 让 std 的函数参与你的调用。给库函数起 `distance`、`find`、`size`、`data` 这样的名字时尤其要小心。

!!! pitfall "用括号或限定名“关闭”ADL 也关闭了定制"
    `(swap)(a, b)` 确实不会被劫持，但也找不到用户的定制。需要"可定制但不可劫持"时，用 CPO。

## 思考题

!!! question "思考题 1"
    ```cpp
    namespace A { struct X {}; void f(X, int); }
    namespace B {
        void f(A::X, long);
        void g() { f(A::X{}, 0); }
    }
    ```
    `B::g` 中的调用选哪个 `f`？如果在 `g` 的函数体开头加一行 `void f(A::X, long);` 呢？

<details markdown="1">
<summary>答案</summary>

原样：无限定查找在 B 中找到 `B::f`（命名空间成员，不抑制 ADL），ADL 再加入 `A::f`；重载集 `{B::f(X,long), A::f(X,int)}`，实参 `0` 是 `int`，`A::f` 精确匹配胜出。

加块作用域声明后：无限定查找在块作用域找到函数声明，¶1.2 抑制 ADL，只剩 `B::f(A::X, long)`，调用它。
</details>

!!! question "思考题 2"
    为什么 niebloid 必须是"无限定查找找到时抑制 ADL"，而不仅仅是"自己不被 ADL 找到"？

<details markdown="1">
<summary>答案</summary>

只做到"不被 ADL 找到"，`using namespace std::ranges; find(it, it, v)` 中无限定查找找到 `ranges::find` 后，ADL 仍会把 `std::find`（迭代器关联 std）乃至用户命名空间的 `find` 加入重载集。由于 `std::find` 是不受约束的函数模板，它常常是同等或更好的匹配，于是 ranges 版本被绕过或出现二义。只有抑制 ADL，才能保证调用的就是那个受约束的 ranges 算法。用对象实现时，¶1.3 自动提供了这一点。
</details>

!!! question "思考题 3"
    `template<int N> struct C {}; namespace N2 { enum E { e }; void f(C<e>); }`，在全局写 `f(C<N2::e>{})` 能找到 `N2::f` 吗？

<details markdown="1">
<summary>答案</summary>

不能。`C<N2::e>` 是全局类模板的特化，其关联实体是 `C<…>` 本身（全局命名空间）；模板实参 `N2::e` 是**常量**模板实参，按注 3 不贡献关联实体。所以关联命名空间只有全局命名空间，`N2::f` 找不到。
</details>

## 小结

| 问题 | 答案 |
|---|---|
| 何时做 | 无限定 *unqualified-id* 作函数调用，且普通查找没找到类成员、块作用域函数声明或非函数 |
| 结果怎么用 | 与无限定查找的结果合并成重载集 |
| 关联什么 | 实参类型的类、所属类、基类（完整时）、模板类型实参、函数类型的参数/返回类型……；基本类型无 |
| 在哪找 | 最内层外围非内联命名空间 + 其内联命名空间集；只做**搜索**（忽略 using 指令）；外加关联类的友元 |
| 只找什么 | 函数与函数模板 |
| 隐藏友元 | 只能被 ADL 找到；重载集小、不被隐式转换误选 |
| swap 两步法 | `using std::swap; swap(a, b);`——using 声明不抑制 ADL |
| CPO/niebloid | 对象：抑制 ADL，内部受控地做 ADL |
| 运算符 | 非成员候选 = 无限定查找（忽略成员）+ ADL，不能用括号关闭 |
| `f<T>(x)` | C++20 起找不到或只找到函数时按模板名解析，ADL 可用 |
