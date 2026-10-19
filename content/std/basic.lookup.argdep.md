---
title: 实参依赖查找（ADL）
summary: 无限定的函数调用 f(args) 除了从调用处向外查找，还会到实参类型所属的命名空间里查找，并找到相关类的友元。
status: done
papers: P0846R0, P1787R6
related: basic.lookup, basic.lookup.unqual, over.match.oper, temp.dep.candidate, temp.names, class.friend, namespace.def, module.reach, module.context, customization.point.object, alg.func.obj
tags: 名字查找, ADL, 重载, 模块, 泛型编程
updated: 2026-10-19
---

!!! tldr
    - 写 `f(x)` 时，编译器除了按普通规则向外查找 `f`，还会到 `x` 的类型所属的命名空间里找名为 `f` 的函数，两边的结果合成一个重载集。这就是 ADL。
    - 写成 `N::f(x)` 或 `(f)(x)`，或者普通查找找到了类成员、块作用域里的函数声明、变量，ADL 就不会发生。
    - 要查找的命名空间由实参类型决定：类所在的命名空间、它的基类、模板实参的类型都算；`int`、`double` 这样的基本类型什么也不带来。
    - 只在类内声明的友元函数（隐藏友元）只能通过 ADL 找到。把运算符写成隐藏友元，是让它既能用、又不污染重载集的标准做法。
    - `using std::swap; swap(a, b);` 两步法、`std::ranges` 的定制点对象，都是为了在泛型代码里控制 ADL 而设计的。

## 为什么需要 ADL

```cpp run ok
#include <iostream>
#include <string>
int main() {
    std::string s = "hi";
    std::cout << s;   // 调用 std::operator<<(std::ostream&, const std::string&)
}
```

这里没有 `using namespace std;`，而 `string` 的输出运算符是 `std` 命名空间里的函数模板，不是 `std::ostream` 的成员。从全局的 `main` 向外查找，找不到 `std::operator<<`。

代码能编译，是因为**实参依赖查找**（argument-dependent lookup，ADL，又叫 Koenig 查找）：实参 `std::cout` 和 `s` 的类型都属于 `std`，所以查找 `operator<<` 时也要搜索 `std`。没有 ADL，命名空间里的运算符就只能写成 `std::operator<<(std::cout, s)`。

ADL 让一个类型的非成员函数，例如同一命名空间里的 `swap`、`operator==`、`begin`，用起来和成员函数一样自然。代价是调用哪个函数取决于实参类型来自哪里，ADL 有时会找到你没打算调用的函数。

## ADL 什么时候发生（¶1）

```cpp run ok
namespace N {
    struct S { };
    void f(S);
}
void g() {
    N::S s;
    f(s);         // OK：ADL 在 N 中找到 N::f
}
```

¶1 函数调用的被调用部分（文法上叫 *postfix-expression*）如果是一个不带限定的名字（*unqualified-id*），就先对它做无限定查找（[[basic.lookup.unqual]]）。只要这次查找没有找到下面三种声明之一，结果里还要并入 ADL 找到的函数：

- ¶1.1 类成员的声明；
- ¶1.2 栖居于块作用域的函数声明；
- ¶1.3 既不是函数、也不是函数模板的声明（变量、类型、函数对象等）。

ADL 的结果是并入，不是替代。无限定查找找到的函数和 ADL 找到的函数合成一个重载集，再交给重载决议。

### 关掉 ADL 的几种写法

| 写法 | 为什么没有 ADL |
|---|---|
| `N::f(x)` | 限定名，不是 *unqualified-id* |
| `(f)(x)` | 被调用部分是带括号的表达式，不是 *unqualified-id* |
| 在成员函数里调用，类或基类有名为 `f` 的成员 | ¶1.1：找到了类成员 |
| 同一块作用域里写了 `void f(int);` | ¶1.2：找到了块作用域函数声明 |
| 普通查找找到变量、函数对象、类型 | ¶1.3：找到了非函数 |

```cpp run error
namespace N {
    struct S { };
    void f(S);
}
void g() {
    N::S s;
    (f)(s);       // error: 括号关掉 ADL，普通查找找不到 f
}
void h() {
    N::S s;
    void f(int);  // 块作用域函数声明
    f(s);         // error: ¶1.2 关掉 ADL，只剩 f(int)，N::S 不能转换为 int
}
void k() {
    N::S s;
    int f = 0;    // 非函数
    f(s);         // error: ¶1.3 关掉 ADL；int 不能被调用
}
struct M {
    void f(int);
    void m() {
        f(N::S{});   // error: ¶1.1 找到成员 M::f，不做 ADL
    }
};
```

标准例 3（¶6）展示了 ¶1.2 的一个实际后果。块作用域里的 `extern` 声明让一个本来更好的候选消失了：

```cpp ok
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
    g(parm, 1);                   // OK：调用 ::g(NS::T, float)
}
```

`NS::g(T, int)` 对 `g(parm, 1)` 是精确匹配，本来会胜出。但无限定查找在块作用域找到了函数声明，ADL 没有发生，`NS::g` 根本不在候选里。

### 块作用域的 using 声明不关掉 ADL

`using std::swap;` 也写在块作用域里，但它不是 ¶1.2 说的函数声明。[[basic.lookup#3]] 规定，搜索找到 using 声明时，要换成它指名的那些声明，也就是 `std::swap` 的函数模板。它们栖居于命名空间 `std`，不在块作用域，所以 ADL 照常进行。后文的 swap 两步法就依赖这一点。

¶6 注 4 还指出，关联命名空间可以和无限定查找已经搜过的命名空间重合。两条路径找到同一个声明不算二义，它仍是重载集里的同一个函数。

## 先判定是不是函数调用（¶2）

¶2 注 1 提醒，表达式是不是函数调用，是在解析时用普通查找规则判定的。ADL 不参与这一步。这有两个后果。

第一个后果关于 `f<T>(x)`。名字后面跟 `<` 时，解析器要先决定它是不是模板名（[[temp.names#7]]）。C++20 起（[[P0846R0]]），只要无限定查找什么也没找到，或者找到的是函数，`<` 就当作模板实参列表的开始。于是 `f<T>(x)` 成了一次调用，ADL 可以找到真正的函数模板：

```cpp run error
int h;
void g();
namespace N {
    struct A {};
    template <class T> int f(T);
    template <class T> int g(T);
    template <class T> int h(T);
}
int x = f<N::A>(N::A());   // OK：f 没找到，按模板名处理，ADL 找到 N::f
int y = g<N::A>(N::A());   // OK：g 找到非模板函数，也按模板名处理
int z = h<N::A>(N::A());   // error: h 找到变量，h< 不开始模板实参列表
```

C++20 之前，`x`、`y` 两行都会被解析成比较表达式而出错。那时取 tuple 元素必须写 `std::get<0>(t)`，现在可以直接写：

```cpp run ok
#include <tuple>
int main() {
    std::tuple<int, double> t{1, 2.0};
    return get<0>(t) - 1;   // C++20 起 OK：ADL 在 std 中找到 std::get
}
```

第二个后果是，不是调用就没有 ADL：

```cpp run ok
typedef int f;
namespace N {
    struct A {
        friend void f(A &);
        operator int();
        void g(A a) {
            int i = f(a);   // f 是 typedef：这是类型转换 int(a)
            (void)i;
        }
    };
}
```

`f` 找到的是 typedef，`f(a)` 在语法上是函数式类型转换（[[expr.type.conv]]），所以不做 ADL，友元 `f` 也就不会被找到。

## 实参类型带来哪些关联实体（¶3）

¶3 对调用中的每个实参类型 `T`，标准规定了一组（可能为空的）[[g:associated-entities|关联实体]]（associated entities），主要是一些类和枚举。ADL 之后要到这些实体所在的命名空间里去找。关联实体只由类型本身决定，类型是用 typedef 还是 using 别名写出来的，都不影响结果。

| `T` 的种类 | 关联实体 |
|---|---|
| ¶3.1 `std::meta::info` {{c++26}} | 只有枚举类型 `std::meta::operators` |
| ¶3.2 其他基本类型（`int`、`double`、`std::nullptr_t`……） | 无 |
| ¶3.3 类类型（含联合） | 类本身；它是嵌套类时，外围的类；它是完整类型时，它的直接和间接基类 |
| ¶3.3 类模板特化，另加 | 类型模板实参的关联实体；用作模板模板实参的模板；用作模板模板实参的成员模板所属的类 |
| ¶3.4 枚举类型 | 枚举本身；它是类成员时，所属的类 |
| ¶3.5 `U*`、`U[n]` | `U` 的关联实体 |
| ¶3.6 函数类型 | 各参数类型和返回类型的关联实体 |
| ¶3.7 类 `X` 的成员函数指针 | 参数类型、返回类型的关联实体，加上 `X` |
| ¶3.8 类 `X` 的数据成员指针 | 成员类型的关联实体，加上 `X` |

实参也可以是函数名，即一个重载集（或取它的地址）。这时关联实体是集合中每个函数的参数类型和返回类型的关联实体之并；如果重载集用模板实参列表写出，还要加上那些模板实参带来的关联实体。

注 3 指出，常量模板实参、变量模板模板实参、概念模板实参不带来关联实体。

### 基本类型：什么也没有

`swap(i, j)`（`int`）不会通过 ADL 找到 `std::swap`。在模板里，`g(1)` 这样的调用在实例化时也不会找到模板定义之后才声明的 `g`，因为第二阶段的查找只靠 ADL。

### 反射值：一条专门的规则 {{c++26}}

`std::meta::info` 是 `decltype(^^int)` 的别名，本身是基本类型。按 ¶3.2 它什么也不带来，`members_of(r, ctx)` 这样的无限定调用就找不到 `std::meta::members_of`。¶3.1 因此把它的关联实体规定为枚举 `std::meta::operators`，这个枚举位于 `std::meta`，于是 `std::meta` 成了关联命名空间。

### 类：外围类和基类

外围类是关联实体，所以嵌套类的实参会带出外围类的友元。完整类型的基类也是关联实体，所以基类里定义的友元对派生类对象同样可用。

```cpp run error
namespace N {
    struct Out {
        struct In { };
        enum class E { a };
        friend void p(In) { }
        friend void q(E) { }
    };
}
namespace L {
    struct Base { friend void fb(const Base&) { } };
    struct D : Base { };
    struct Inc;                      // 只声明，不完整
}
void t(L::Inc* pi) {
    p(N::Out::In{});    // OK：In 的外围类 Out 是关联实体，找到 Out 的友元 p
    q(N::Out::E::a);    // OK：¶3.4 枚举是 Out 的成员
    fb(L::D{});         // OK：D 完整，基类 Base 是关联实体
    fb(*pi);            // error: Inc 不完整，不计基类
}
```

### 模板实参：最容易带来意外

ADL 的意外结果大多来自模板实参。`std::vector<N::X>` 让 `N` 和 `std` 都成为关联命名空间。实参的实参也算：`std::function<void(N::X)>` 的模板实参是函数类型 `void(N::X)`，按 ¶3.6 它的参数类型 `N::X` 带来 `N`。

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
    f(fn);                 // OK：模板实参 void(N::X) 的参数类型带来 N
    h(&N::cb);             // OK：实参是重载集 {N::cb}，cb 的参数类型带来 N
    z(O::Box<P::Y>{});     // OK：模板实参 P::Y 带来 P
}
```

别名不起作用，只看它代表的类型：

```cpp run error
namespace N { struct X {}; }
namespace T {
    using Alias = N::X;
    void f(Alias);
}
void t() {
    T::Alias a;
    f(a);        // error: a 的类型是 N::X，关联命名空间只有 N，不含 T
}
```

## 到哪里找、找什么（¶4）

¶4 调用的[[g:associated-namespaces|关联命名空间]]是每个关联实体的最内层外围非内联命名空间，再加上这些命名空间的内联命名空间集（[[namespace.def]]）。

这两条合起来，让库的版本化内联命名空间对 ADL 透明。libc++ 的 `std::vector` 实际上是 `std::__1::vector`，它最内层的外围非内联命名空间是 `std`，再加上 `std` 的内联命名空间集（含 `__1`）。所以相关函数无论声明在 `std` 还是 `std::__1`，ADL 都能找到。

对名字 `N`，ADL 找到满足下列任一条件的函数和函数模板声明：

- ¶4.1 在某个关联命名空间中搜索 `N` 时找到的；
- ¶4.2 被声明为某个关联类的友元，并且这个类的定义可达；
- ¶4.3 来自具名模块的导出声明，满足若干条件（见下文模块一节）。

ADL 只收集函数和函数模板。关联命名空间里名为 `N` 的变量或类型会被直接忽略，不会造成二义。

### 在关联命名空间里只做一次搜索

¶4.1 说的是**搜索**（search，[[basic.lookup]]），只看这个命名空间自己的声明。它不是从内向外的无限定查找，所以不看外层命名空间，也不跟随这个命名空间里的 using 指令：

```cpp run error
namespace M { }
namespace N {
    using namespace M;   // ADL 不会顺着它进入 M
    struct S { };
}
namespace M { void g(N::S); }

void t() {
    g(N::S{});    // error: 关联命名空间只有 N；在 N 中的搜索不跟随 using 指令
}
```

### 友元与隐藏友元

类内的 `friend void f(X);` 声明的是外围命名空间里的函数 `f`。但友元声明不绑定名字（[[class.friend#10]]、[[dcl.meaning.general#2]]）：在命名空间作用域出现匹配的声明之前，无限定查找和限定查找都找不到它。¶4.2 让 ADL 能找到它，条件是这个类是关联实体，并且定义可达。

只在类内声明（通常就在类内定义）、不在命名空间作用域再声明一次的友元函数，叫做**隐藏友元**（hidden friend）。它只能通过 ADL 找到：

```cpp run error
#include <ostream>
namespace N {
    class P {
        int v = 0;
        friend bool operator==(const P&, const P&) = default;
        friend std::ostream& operator<<(std::ostream& os, const P& p) {
            return os << p.v;
        }
        friend void touch(P&) { }
    };
}
void t(std::ostream& os) {
    N::P a, b;
    os << a;           // OK：ADL 找到 N::P 的友元
    (void)(a == b);    // OK
    touch(a);          // OK
    N::touch(a);       // error: 限定查找找不到隐藏友元
}
```

推荐把运算符和定制函数写成隐藏友元，理由有三个。

第一，重载集更小。命名空间作用域的 `operator<<` 会参与这个命名空间里每一次 `<<` 的查找。标准库这样的大命名空间里可能有上百个 `operator<<`，重载决议要逐个尝试，既拖慢编译，也让错误信息变长。隐藏友元只在实参确实涉及这个类时才出现。

第二，不会因为隐式转换被误选。只有实参的关联类就是这个类时，才找得到隐藏友元。一个只是能转换成这个类的类型，找不到它：

```cpp run error
namespace units {
    struct Meters { double v; Meters(double d) : v(d) {} };
    struct ToMeters { operator Meters() const { return 1.0; } };
    void show(Meters);                       // 命名空间作用域

    struct Feet {
        double v; Feet(double d) : v(d) {}
        friend void show2(Feet) { }          // 隐藏友元
    };
    struct ToFeet { operator Feet() const { return 1.0; } };
}
void t() {
    units::ToMeters m;
    show(m);                  // OK：ADL 在 units 中找到 show，经转换调用
    units::ToFeet f;
    show2(units::Feet(1.0));  // OK
    show2(f);                 // error: ToFeet 的关联实体不含 Feet
}
```

第三，友元可以直接访问私有成员，不需要额外公开 getter。

## 模块中的 ADL（¶4.3、¶5）

在模块中，一个声明是否在查找点之前可见，和它的定义是否可达，是两回事（[[basic.lookup#2]]、[[module.reach]]）。¶4.3 让 ADL 还能找到这样的函数：它被导出，附属于某个具名模块 `M`，不在当前翻译单元里，并且和某个附属于 `M` 的关联实体位于同一个最内层非内联命名空间。即使这个函数所在的命名空间在当前翻译单元里根本不可见，也能找到。

标准例 2 有三个翻译单元：

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

```cpp title="TU3: 模块 Q 的实现单元"
module Q;
import N;
namespace S {
    struct Z { template<typename T> operator T(); };
}
void test() {
    auto x = make();     // OK：x 的类型是模块 M 中的 R::X
    R::f(x);             // error: 此处没有导入 M，R 和 R::f 都不可见
    f(x);                // OK：¶4.3，R::f 被导出、附属于 M，与关联实体 R::X 同在 R
    f(x, S::Z());        // error: S 是关联命名空间，但 M 中的 S::f 不满足 ¶4.3：
                         //        S 中的关联实体 S::Z 附属于 Q，不附属于 M
    apply(x, S::Z());    // error: 实例化上下文中 S::f 可见，但 R::g 有内部链接，
                         //        不能在 TU2 之外使用
}
```

¶4 的最后一句针对模板里的依赖名。对依赖调用，上述查找还要从实例化上下文（[[module.context]]）中的每个点再做一次。此时忽略另一个翻译单元里附属于全局模块、并且已被丢弃（[[module.global.frag]]）或有内部链接的声明。常说的两阶段查找中“第二阶段只做 ADL”，在模块里的精确表述就是这一句。

[[temp.dep.candidate#1]] 另有一条：如果把所有翻译单元中关联命名空间里具有外部链接的函数都考虑进来，依赖调用会找到更好的匹配或者变得非良构，那么程序非良构，不要求诊断。

## 惯用法一：swap 两步法

泛型代码要交换两个 `T` 时，`std::swap(a, b)` 是限定名，会绕过用户为自己的类型写的高效 `swap`；`swap(a, b)` 遇到 `int` 时又没有关联命名空间，找不到 `std::swap`。标准做法是两步：

```cpp run ok
#include <utility>
namespace N {
    struct Big { int d[100]; };
    void swap(Big&, Big&) noexcept { }   // 自定义的高效 swap
}

template<class T>
void my_algo(T& a, T& b) {
    using std::swap;     // 第一步：让无限定查找找到 std::swap 作后备
    swap(a, b);          // 第二步：无限定调用，ADL 加入 T 所在命名空间的 swap
}

int main() {
    N::Big a, b;
    my_algo(a, b);       // 选 N::swap：非模板优于模板
    int i = 1, j = 2;
    my_algo(i, j);       // 选 std::swap
}
```

它能工作有三个前提：块作用域的 using 声明不关掉 ADL；重载集里同时有 `std::swap` 和 `N::swap`；重载决议中非模板优于模板，更特化的模板优于更一般的模板。

这个写法容易写错，比如忘了 `using` 或写成 `std::swap`。C++20 因此提供了 `std::ranges::swap`，它是一个定制点对象，在内部完成同样的事。

## 惯用法二：定制点对象与 niebloid

ADL 有两个系统性问题。一是劫持（hijacking）：泛型库里的无限定调用，可能被实参类型所在命名空间里碰巧同名的函数抢走。二是意外二义：库调用自己的函数时，ADL 在另一个关联命名空间里找到同样好的候选。

```cpp run error
#include <vector>
#include <iterator>
#include <algorithm>
namespace N {
    struct X { bool operator==(const X&) const = default; };
    template<class It> int distance(It, It) { return 0; }
    template<class It, class T> It find(It b, It, const T&) { return b; }
}
int main() {
    std::vector<N::X> v(3);
    auto n  = distance(v.begin(), v.end());      // error: std::distance 与 N::distance 二义
    auto it = find(v.begin(), v.end(), N::X{});  // error: std::find 与 N::find 二义
}
```

`v.begin()` 的类型是 `std::vector<N::X>` 的迭代器（libc++ 中是 `std::__wrap_iter<N::X*>`）。它的模板实参 `N::X*` 把 `N` 带进关联命名空间，`std` 本来就在其中。两个函数模板一样好，于是二义。

**定制点对象**（customization point object，CPO，[[customization.point.object]]）把库的入口做成对象而不是函数：

- 无限定查找找到的是一个变量，按 ¶1.3 关掉 ADL，调用方不会被劫持；
- ADL 只收集函数，永远不会找到这个对象，所以它不会和别处的同名函数形成二义；
- 对象的 `operator()` 内部再以受控的方式做 ADL，同时检查语义要求。例如 `std::ranges::swap` 先用 `template<class T> void swap(T&, T&) = delete;` 这样的重载（俗称毒丸）挡住 `std::swap`，再做 ADL；`std::ranges::begin` 原本也有这样的毒丸，[[P2602R2]] 之后它对非成员 `begin` 只做实参依赖查找（[[range.access.begin#2]]），不再需要毒丸。

`std::ranges` 里的算法（`find`、`sort`……）也有同样的性质，俗称 niebloid（得名于 Eric Niebler）。C++20 只要求它们不被 ADL 找到、被无限定查找找到时关掉 ADL，没有规定必须是对象。C++26 起，标准直接把它们定义为**算法函数对象**（algorithm function object，[[alg.func.obj]]）：

```cpp run ok
#include <ranges>
#include <vector>
#include <algorithm>
void foo() {
    using namespace std::ranges;
    std::vector<int> vec{1, 2, 3};
    auto it = find(begin(vec), end(vec), 2);   // std::ranges::find：对象，关掉 ADL
    (void)it;
}
```

## 惯用法三：运算符

运算符表达式 `a @ b` 没有限定写法，也不能靠加括号关掉 ADL。[[over.match.oper#3]] 规定，它的非成员候选来自对 `operator@` 的无限定查找加 ADL，并且忽略所有成员函数；成员候选另外在 `a` 的类里搜索。所以和具名调用不同，运算符的 ADL 总会进行。

无限定查找找到就停。所以命名空间里只要声明了任何一个 `operator<<`，外层的 `operator<<` 就看不见了，只能靠 ADL：

```cpp run error
#include <iostream>
#include <vector>
std::ostream& operator<<(std::ostream& os, const std::vector<int>&) { return os; }
struct G {};
std::ostream& operator<<(std::ostream& os, G) { return os; }

namespace N {
    struct Z {};
    std::ostream& operator<<(std::ostream& os, Z);   // 无限定查找在 N 停下
    void f(const std::vector<int>& v, G g) {
        std::cout << g;   // OK：G 在全局命名空间，ADL 找到 ::operator<<
        std::cout << v;   // error: ADL 只看 std，找不到全局的那个
    }
}
```

为某个类型定义的运算符，应该放在这个类型所在的命名空间里，最好写成隐藏友元。在全局为 `std` 里的类型（如 `std::vector<int>`）写运算符，只是碰巧能被无限定查找看到，换个命名空间就失效。往 `std` 里加这种声明又是标准禁止的（[[namespace.std]]）。

## 其他容易忽略的情形

```cpp run ok
#include <iostream>
#include <string>
#include <iterator>
int main() {
    endl(std::cout);        // OK：std::cout 的类型在 std，ADL 找到 std::endl
    std::string arr[3];
    auto b = begin(arr);    // OK：数组元素类型 std::string 带来 std
    (void)b;
}
```

- lambda 的闭包类型是类类型，它的最内层外围命名空间就是 lambda 出现的地方。把 lambda 作为实参，也会把这个命名空间带进来。
- `f(nullptr)`、`f(0)`、`f(1.0)` 永远没有 ADL。
- `std::array<N::X, 3>` 带来 `N`（类型实参）。`std::integral_constant<N::E, N::E::a>` 里的 `N::E::a` 是常量模板实参，不带来任何东西，但类型实参 `N::E` 照样带来 `N`。

!!! impl "实现视角"
    - Clang 在 `Sema::ArgumentDependentLookup` 中实现 ADL，用 `FindAssociatedClassesAndNamespaces` 按 ¶3 计算关联类和关联命名空间。隐藏友元的声明放在命名空间里，但带有一个标记，使它对普通查找不可见。
    - 模块：Clang 在实例化时按实例化上下文计算 ADL 能看到哪些声明。`#include` 进全局模块片段、但没有被引用而被丢弃的函数，在其他翻译单元里对 ADL 不可见（[[temp.dep.candidate#5]] 的例 4）。
    - ADL 影响编译速度：大量命名空间作用域的运算符模板会让每个 `<<` 都触发昂贵的重载决议。C++20 起，标准库的新组件（如 ranges 的视图和迭代器）大量把运算符规定为隐藏友元，这是原因之一。

!!! history "历史与演进"
    - C++98：ADL 进入标准，最初是为运算符设计的，后来推广到所有无限定函数调用。
    - C++11：引入内联命名空间，关联命名空间包括内联命名空间集。这时的条文明确写着，关掉 ADL 的是“不是 using 声明的块作用域函数声明”。
    - C++20：[[P0846R0]] 让 `f<T>(x)` 在找不到模板或只找到函数时也按模板名解析，从而能借助 ADL 调用函数模板并显式给出模板实参。模块带来了 ¶4.3 和实例化上下文中的 ADL；ranges 带来了 CPO 和 niebloid。
    - C++23：[[P1787R6]] 用搜索、关联实体等概念重写了本节。using 声明不关掉 ADL 这一点不再单独写出，改由 [[basic.lookup#3]] 的替换规则得出。
    - C++26：¶3.1 让 `std::meta::info` 关联 `std::meta`；niebloid 被规定为算法函数对象。

## 常见误解

!!! pitfall "限定调用和无限定调用只是写法不同"
    `std::swap(a, b)` 和 `using std::swap; swap(a, b)` 可能调用不同的函数，`std::begin(r)` 和 `std::ranges::begin(r)` 的语义也不同。在泛型代码里，选择调用形式就是选择查找规则。

!!! pitfall "只有实参自己的命名空间才会被搜索"
    模板实参也会带来命名空间。`std::vector<mylib::Widget>` 让 `mylib` 里的同名函数参与 `std` 算法内部的无限定调用；反过来，`mylib::Container<std::string>` 让 `std` 的函数参与你的调用。给库函数起 `distance`、`find`、`size`、`data` 这类名字时尤其要小心。

!!! pitfall "用括号或限定名关掉 ADL 就安全了"
    `(swap)(a, b)` 确实不会被劫持，但也找不到用户的定制。需要既可定制、又不会被劫持的调用时，用 CPO。

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

原样时，无限定查找在 `B` 中找到 `B::f`。它是命名空间成员，不关掉 ADL，ADL 再加入 `A::f`。重载集是 `{B::f(X, long), A::f(X, int)}`，实参 `0` 是 `int`，`A::f` 精确匹配，胜出。

加上块作用域声明后，无限定查找在块作用域找到函数声明，¶1.2 关掉 ADL，只剩 `B::f(A::X, long)`，于是调用它。本机 Clang 23 运行结果与此一致。
</details>

!!! question "思考题 2"
    为什么 niebloid 被无限定查找找到时必须关掉 ADL，只做到自己不被 ADL 找到还不够？

<details markdown="1">
<summary>答案</summary>

如果只是不被 ADL 找到，那么在 `using namespace std::ranges; find(it, it, v)` 中，无限定查找找到 `ranges::find` 之后，ADL 仍会把 `std::find`（迭代器关联 `std`）乃至用户命名空间里的 `find` 加进重载集。`std::find` 是不受约束的函数模板，常常是同样好或更好的匹配，结果要么绕过了 ranges 版本，要么二义。只有关掉 ADL，才能保证调用的是那个受约束的 ranges 算法。用对象实现时，¶1.3 自然做到了这一点。
</details>

!!! question "思考题 3"
    `template<int N> struct C {}; namespace N2 { enum E { e }; void f(C<e>); }`，在全局写 `f(C<N2::e>{})` 能找到 `N2::f` 吗？

<details markdown="1">
<summary>答案</summary>

不能。`C<N2::e>` 是全局类模板的特化，关联实体只有它自己，位于全局命名空间。`N2::e` 是常量模板实参，按注 3 不带来关联实体。所以关联命名空间只有全局命名空间，找不到 `N2::f`。本机 Clang 23 报告 `f` 未声明。
</details>

## 小结

| 问题 | 答案 |
|---|---|
| 何时做 | 无限定名字作函数调用，且普通查找没找到类成员、块作用域函数声明或非函数 |
| 结果怎么用 | 与无限定查找的结果合成一个重载集 |
| 关联什么 | 类本身、外围类、基类（完整时）、类型模板实参、函数类型的参数和返回类型；基本类型什么也没有 |
| 在哪找 | 最内层外围非内联命名空间及其内联命名空间集，只做搜索（不跟随 using 指令）；外加关联类的友元 |
| 只找什么 | 函数和函数模板 |
| 隐藏友元 | 只能被 ADL 找到；重载集小，不会因隐式转换被误选 |
| swap 两步法 | `using std::swap; swap(a, b);`，using 声明不关掉 ADL |
| CPO / niebloid | 对象：关掉 ADL，在内部受控地做 ADL |
| 运算符 | 非成员候选 = 无限定查找（忽略成员）+ ADL，无法关掉 |
| `f<T>(x)` | C++20 起找不到或只找到函数时按模板名解析，可以用 ADL |
