---
title: 无限定名字查找
summary: 不带 :: 或成员访问前缀的名字从所在位置的作用域开始逐层向外搜索，找到就停；using 指令提名的命名空间在特定的那一层并入。函数体、成员函数、友元、局部类、模板等各种情形的查找顺序都由这一个算法推出。
status: done
papers: P1787R6
related: basic.lookup, class.member.lookup, basic.lookup.argdep, namespace.udir, basic.scope.scope, basic.scope.pdecl, class.mem, temp.local, class.friend
tags: 名字查找, 作用域, using 指令
updated: 2026-10-19
---

!!! tldr
    - 无限定名字从它所在位置的直接作用域开始，一层层向外搜索，在某一层找到任何声明就停下。
    - 所以内层的一个同名声明会隐藏外层所有的同名声明，包括外层函数的全部重载。
    - using 指令本身不声明名字，它让被提名命名空间的名字在同时包含指令和该命名空间的最内层作用域那一层参与搜索，这一层往往比想象的更靠外。
    - 在类外定义成员函数时，函数名之后的部分属于类作用域，可以直接用成员名；写在函数名之前的返回类型不属于。
    - 类模板中，类自己的成员和非依赖基类的成员比模板形参先被找到。

`x`、`f(a)`、`T`、`operator+` 这些名字前面没有 `N::`，也不跟在 `.`、`->` 之后，编译器只能从它们所在的位置往外找。本节规定了往外找的精确含义。

## 一层层向外，找到就停（¶2–¶4）

```cpp run ok
void h(int);
namespace N {
    void h(double);
    void k() { h(1); }   // 调用 N::h(double)，::h(int) 不是候选
}
```

¶3 **无限定名字查找**（unqualified name lookup）从名字所在的程序点出发，在它的直接作用域（包含它的最小作用域，[[basic.scope.scope#1]]）中做一次无限定搜索。

¶2 在作用域 S 中做**无限定搜索**（[[g:unqualified-search]]），就是在 S 中搜索（类作用域的搜索还包括基类，[[class.member.lookup]]），同时搜索在这一层生效的 using 指令所提名的命名空间（见下一节）。如果什么也没找到，就到 S 的父作用域中继续做无限定搜索。

上例中，`k` 的函数体和形参作用域里都没有 `h`，于是到命名空间 `N`，找到 `N::h(double)` 就停了，全局的 `h(int)` 根本没有被看到。重载决议只在 `{N::h(double)}` 中选，`1` 转换为 `double`。

旧标准有专门的条款规定内层声明隐藏外层同名声明。今天不需要了，隐藏就是找到即停的结果。如果实参是类类型，ADL 还可能把别处的函数加进来（[[basic.lookup.argdep]]）。

注 1 补充两点。搜索类作用域时也搜索它的基类；只有一个基类时，就好像基类的作用域直接包含派生类的作用域。与作用域链上某个作用域相关联的模板形参作用域也在考虑之列（[[temp.local]]，见下文）。

¶4 **无限定名字**指不紧跟在嵌套名说明符（`N::`）之后、也不紧跟在成员访问的 `.` 或 `->` 之后的名字，中间可以隔着 `template` 关键字或 `~`。除非另有规定，它在出现处做无限定名字查找。另有规定的常见情形有：

- 函数调用 `f(args)` 的 `f` 还要加上 ADL 的结果（[[basic.lookup.argdep]]）；
- 运算符表达式中查找非成员的 `operator@` 时忽略成员函数（[[over.match.oper#3]]）；
- 声明中被声明的名字本身不是使用，不做查找；
- 下文第 5 段的转换类型和第 6 段的友元声明符。

## using 指令在哪一层生效（¶1–¶2）

```cpp run ok
#include <type_traits>
namespace A { int i = 1; }
namespace B {
    long i = 2;
    void f() {
        using namespace A;
        static_assert(std::is_same_v<decltype(i), long>);   // 找到 B::i
    }
}
void g() {
    using namespace A;
    static_assert(std::is_same_v<decltype(i), int>);        // 找到 A::i
}
```

在 `B::f` 里写了 `using namespace A;`，找到的却是 `B::i`，不是 `A::i`。

¶1 一个 using 指令在作用域 S、程序点 P 处是**活跃的**（[[g:active-using-directive]]），条件是它先于 P，并且栖居于 S，或者栖居于另一个在 S 中活跃的 using 指令所提名的命名空间。后一种情况是递归的：S 中有 `using namespace A;`，A 中又有 `using namespace C;`，那么 A 中这条指令在 S 中也活跃。这就是 using 指令的传递性（[[namespace.udir#5]]）。

¶2 在作用域 S 中做无限定搜索时，搜索的是：

- ¶2.1 S 本身；
- ¶2.2 对每个包含 P、并且是 S 或在 S 之内的作用域 U，在 U 中活跃的 using 指令所提名的、在 S 之内的命名空间。

第 2.2 项有两个条件：using 指令要在 S 之内（或就是 S），被提名的命名空间也要在 S 之内。所以被提名的命名空间要等到搜索走到同时包含指令和它的最内层作用域时，才并入搜索。[[namespace.udir#3]] 的注 2 用一句更直观的话说了同样的事：

!!! std
    During unqualified name lookup, the names appear as if they were declared in the nearest enclosing namespace which contains both the using-directive and the designated namespace.

在 `B::f` 中查找 `i`：

| 搜索的作用域 | 命名空间 A 是否并入 | 结果 |
|---|---|---|
| `f` 的函数体 | A 不在函数体之内，不并入 | 无 |
| `f` 的形参作用域 | 同上 | 无 |
| 命名空间 `B` | A 不在 B 之内，不并入 | 找到 `B::i`，停止 |

A 要到全局作用域才并入，可是搜索在 B 就停了。在全局函数 `g` 中，全局作用域同时包含指令和 A，`A::i` 在全局这一层参与搜索，这一层没有别的 `i`，于是找到 `A::i`。

如果并入的那一层本来就有同名声明，查找就有二义：

```cpp run error
int x = 0;
namespace A { int x = 1; }
void f() {
    using namespace A;
    x = 2;            // error: 全局这一层同时找到 ::x 和 A::x
}
```

局部声明总是先被找到，using 指令盖不过它们：

```cpp run ok
namespace N { int y = 0; }
int f() {
    using namespace N;
    int y = 1;        // 块作用域的 y
    return y;         // 局部的 y；N::y 要到全局这一层才参与
}
```

!!! tip "与 using 声明对比"
    `using N::y;` 是声明，它把 `y` 绑定在所在的作用域中。在块里写了 `using N::y;` 再写 `int y;`，就是冲突的重声明。using 指令不声明任何名字（[[namespace.udir#4]]），只决定在哪一层顺带搜索哪个命名空间。

## 各种位置的查找顺序

旧标准用十几段文字逐一列出命名空间成员函数、成员函数体、友元函数、构造函数初始化列表等处的查找顺序。今天这些都可以由作用域如何嵌套（[[basic.scope]]）加上找到即停推出来。

### 声明点

查找只能找到声明点在使用处之前的声明，而变量的声明点在完整声明符之后、初始化器之前（[[basic.scope.pdecl#1]]）：

```cpp run ok
const int i = 2;
void g() {
    int i[i];      // 方括号里的 i 是 ::i，新的 i 还没有生效
    (void)i;
}
```

`int v = v;` 则相反，初始化器中的 `v` 就是正在声明的 `v`。它的生命期还没有开始，读取它是未定义行为（[[basic.life]]）。这不属于 C++26 的错误行为，错误行为针对的是生命期已经开始、只是没有初始化的变量（[[basic.indet]]）。

### 类外定义的命名空间成员

`void N::g() { ... }` 中，`N::g` 之后的部分属于命名空间 N 的作用域（[[basic.scope.namespace]]）。所以函数体中的名字依次在 `g` 的函数体、形参作用域、N、全局中查找，虽然这个定义在文本上写在全局：

```cpp run ok
namespace N { void g(); int helper(); }
void N::g() {
    helper();        // OK：找到 N::helper
}
```

### 成员函数

类定义里的成员函数体是[[g:complete-class-context]]（[[class.mem#10]]）。搜索走到类作用域时从类定义的末尾开始搜索（[[class.member.lookup#3]]），所以可以使用后面才声明的成员。默认实参、默认成员初始化器、`noexcept` 说明符也一样；数组边界、成员的类型则不是完整类上下文：

```cpp run error
struct X {
    int f(int a = k) { return a + m; }   // OK：默认实参和函数体都能看到后面的成员
    static constexpr int k = 3;
    int m = 0;
    int arr[k2];                         // error: 数组边界里 k2 还没有声明
    static constexpr int k2 = 4;
};
```

在类外定义 `X::T X::f() { ... }` 时，`X::f` 之后的形参列表、尾置返回类型和函数体属于类作用域（[[basic.scope.class]]），之前的返回类型不属于，要写全限定名：

```cpp run error
struct X { using T = int; T f(); T g(); auto h() -> T; };

X::T X::f() { T local = 0; return local; }  // OK：返回类型要限定，函数体内直接用 T
auto X::h() -> T { return 0; }              // OK：尾置返回类型在 X::h 之后
T X::g() { return 0; }                      // error: 返回类型处的 T 不在 X 的作用域里
```

### 友元函数

在类里定义的友元函数，函数体在文本上位于类定义之内，作用域链经过类作用域，可以直接使用类的成员名：

```cpp run ok
struct X {
    static constexpr int k = 3;
    int m = 0;
    friend int peek(const X& x) { return x.m + k; }   // k 是 X::k
};
int main() { return peek(X{}) - 3; }
```

在类外定义的友元函数不在类作用域中（[[class.friend#6]]），因为 [[basic.scope.class]] 把友元声明排除在外。

友元声明本身不绑定名字（[[class.friend#10]]）。写了 `friend void f(X);` 之后，在外层命名空间做无限定查找找不到这个 `f`，只有 ADL 能找到它。隐藏友元（hidden friend）的惯用法就建立在这一点上（[[basic.lookup.argdep]]）。

### 局部类

局部类成员函数的作用域链经过外层函数的块作用域，所以能找到外层函数的局部变量。但 odr-use 它们是非良构的（[[basic.def.odr#10]]），不构成 odr-use 的用法（`sizeof`、读取可用于常量表达式的常量）则可以：

```cpp run error
void f() {
    int n = 1;
    const int c = 2;
    struct L {
        int g() { return sizeof(n) + c; }   // OK：n 没有被 odr-use；c 是常量
        int h() { return n; }               // error: odr-use 了外层函数的局部变量
    };
    (void)n;
}
```

### 模板形参

[[temp.local#7]] 规定，无限定查找在与模板声明相关联的最外层作用域之后，紧接着考虑这个模板声明的模板形参作用域，即使在类外定义中这个作用域在文本上并不包含模板形参列表。由此得出：类模板的成员，包括非依赖基类的成员，比模板形参先被找到。标准的例 6：

```cpp run ok
#include <type_traits>
struct B { };
namespace N {
    typedef void V;
    template<class T> struct A : B {
        typedef void C;
        void f();
        template<class U> void g(U);
    };
}

template<class V> void N::A<V>::f() {      // 这里不考虑 N::V
    V v;                                   // V 是模板形参（int），不是 N::V
    static_assert(!std::is_void_v<V>);
}

template<class B> template<class C> void N::A<B>::g(C) {
    B b;                                   // B 是基类 ::B，不是模板形参
    C c;                                   // C 是 g 的模板形参，不是 A::C
    static_assert(std::is_same_v<B, ::B>);
}
template struct N::A<int>;
template void N::A<int>::g(long);
```

`f` 中查找 `V` 的顺序是：`f` 的函数体、形参作用域、类 `A`（含基类 `B`）、`A` 的模板形参作用域、`N`、全局。所以在到达 `N` 之前就找到了模板形参 `V`。

`g` 中的 `B`：类 `A` 的作用域（含基类 `B` 的注入类名）在 `A` 的模板形参作用域之前，所以 `B` 指基类。`C` 则是成员模板 `g` 自己的模板形参：与 `g` 相关联的最外层作用域是它的形参作用域，`g` 的模板形参作用域紧跟其后，排在类 `A` 之前。

模板形参的名字不能在它的作用域内再声明（[[temp.local#6]]），所以模板形参被成员隐藏的情况，只会经由基类成员或类外定义出现。

### 依赖基类

搜索走到类模板的作用域时，只合并非依赖的基类（[[class.member.lookup#4]]）。依赖基类的成员要写 `this->`、`Derived::` 或 `typename Derived::`：

```cpp run error
template<class T> struct Base { using type = T; };
template<class T> struct D : Base<T> {
    typename D::type y;   // OK：限定名，查找推迟到实例化
    type x;               // error: 无限定查找不进入依赖基类
};
```

## 两条特殊规则（¶5、¶6）

### 转换函数中的类型名（¶5）

`x.operator T()` 调用的是 `x` 所属类的转换函数，这个 `T` 很可能是那个类的成员类型。如果只在调用处查找 `T`，就无法写出这样的调用。

¶5 所以，转换函数名 `operator ...` 中类型部分的无限定名字，先按整个转换函数名的查找方式去找；找不到，再做普通的无限定查找。两种情况都只考虑类型和特化为类型的模板。标准的例 1：

```cpp run ok
struct T1 { struct U { int i; }; };
struct T2 { };
struct U1 {};
struct U2 {};

struct B {
    using T = T1;
    using U = U1;
    operator U1 T1::*();
    operator U1 T2::*();
    operator U2 T1::*();
    operator U2 T2::*();
};

template<class X, class T>
int g() {
    using U = U2;
    X().operator U T::*();                // #1
    X().operator U decltype(T())::*();    // #2
    return 0;
}
int x = g<B, T2>();   // #1 调用 B::operator U1 T1::*
                      // #2 调用 B::operator U1 T2::*
```

`#1` 中，`operator U T::*` 跟在 `.` 之后，在 `X` 也就是 `B` 中查找；它里面的 `U`、`T` 也先在 `B` 中找，分别得到 `B::U`（U1）和 `B::T`（T1）。`#2` 中，`U` 同样在 `B` 中找到；`decltype(T())` 里的 `T` 是表达式中的普通名字，找到模板形参 `T`（T2）。

### 带限定名的友元声明（¶6）

`friend void A::f(F);` 把 `A` 中已有的某个 `f` 声明为友元，形参类型 `F` 自然应该按 `A::f` 原来的语境理解。类外定义成员时，函数名之后的部分属于类作用域，本来就是这样；但友元声明不在此列（[[basic.scope.class]]），所以需要单独规定。

¶6 友元声明的声明符中，如果被声明的名字是限定名，其嵌套名说明符指定类或命名空间 S，那么出现在这个名字之后的无限定名字，先在 S 的作用域中搜索；找不到，再做普通的无限定查找。标准的例 2：

```cpp run error
using I = int;
using D = double;
namespace A {
    inline namespace N { using C = char; }
    using F = float;
    void f(I);
    void f(D);
    void f(C);
    void f(F);
}
struct X0 { using F = float; };
struct W {
    using D = void;
    struct X : X0 {
        void g(I);
        void g(::D);
        void g(F);
    };
};
namespace B {
    typedef short I, F;
    class Y {
        friend void A::f(I);        // error: A 中没有 I，找到 B::I（short），没有 A::f(short)
        friend void A::f(D);        // OK：A 中没有 D，找到 ::D（double）
        friend void A::f(C);        // error: 在 A 中搜索不包括内联命名空间 N
        friend void A::f(F);        // OK：在 A 中找到 A::F（float）
        friend void W::X::g(I);     // error: 没有 X::g(short)
        friend void W::X::g(D);     // OK：X 和 X0 中都没有 D，找到 ::D
        friend void W::X::g(F);     // OK：在 X 的基类 X0 中找到 F
    };
}
```

- `A::f(C)`：第 6 段说的是在 S 中做一次搜索，而搜索不包括内联命名空间；只有限定名字查找才会再搜索内联命名空间（[[namespace.qual#1]]）。所以找不到 `C`。
- `W::X::g(D)`：在 X（含 X0）中找不到 `D`，于是回到友元声明所在处做普通的无限定查找。作用域链是 Y、B、全局，不经过 W，所以找到 `::D`。

!!! impl "Clang 的实现情况"
    本机 Clang 23 对 S 是类的情形实现了这条规则（`W::X::g(F)` 通过），对 S 是命名空间的情形没有实现：它把 `friend void A::f(F);` 里的 `F` 解析为 `B::F`（short），报告友元声明与 A 中的任何声明都不匹配。按标准这一行是良构的。其余各行 Clang 的判定与标准一致。

## 实现视角

!!! impl "编译器怎么做"
    - Clang 的无限定查找沿 `Scope` 和 `DeclContext` 链向外走。每到一层，它用 `UnqualUsingDirectiveSet` 把 using 指令提名的命名空间挂到同时包含指令与该命名空间的最近外层命名空间那一层，与第 2.2 项的规定等价。
    - MSVC 在 `/permissive-` 之前会在实例化时再查一遍依赖基类，使上面 `type x;` 之类的代码也能编译；Clang 和 GCC 按标准报错。

## 历史与演进

!!! history
    - C++20 及以前，本节是十几段的场景清单，分别描述命名空间作用域、类定义、成员函数定义、友元、构造函数初始化列表、静态数据成员定义等处的查找顺序。
    - C++23 由 [[P1787R6]] 压缩为现在的六段：活跃的 using 指令、无限定搜索、无限定查找、无限定名字的定义，以及转换类型和友元声明符两条特例。各种场景改由作用域规则推出，关键是 [[basic.scope.class]]、[[basic.scope.namespace]] 中函数名之后的部分也属于该作用域这一规定。

## 常见误解

!!! pitfall "using namespace 能盖过外层的同名声明"
    `namespace B { long i; void f() { using namespace A; i; } }` 中的 `i` 仍然是 `B::i`。using 指令引入的名字要到同时包含指令和目标命名空间的那一层才参与搜索。

!!! pitfall "头文件里写 using namespace std 只是少打几个字"
    在全局作用域写了 `using namespace std;`，std 的名字就在全局这一层参与搜索。日后标准库加入一个和你的全局函数同名的函数（例如 `std::size`、`std::data`），原来没有二义的代码可能变成二义，或者悄悄改调另一个函数。

!!! pitfall "类外定义的返回类型可以直接用成员类型"
    返回类型在函数名之前，不在类作用域中。要么写 `X::T X::f()`，要么用尾置返回类型 `auto X::f() -> T`。

## 思考题

!!! question "思考题 1"
    ```cpp
    namespace A { int n = 1; }
    namespace B { using namespace A; }
    namespace C {
        int n = 2;
        namespace D {
            using namespace B;
            int get() { return n; }
        }
    }
    ```
    `C::D::get()` 返回几？

<details markdown="1">
<summary>答案</summary>

返回 2。D 中的指令提名 B；按第 1 段的传递性，B 中提名 A 的指令在 D 中也活跃。但同时包含这些指令和 A 的作用域只有全局作用域。沿作用域链搜索：`get` 的函数体、形参作用域、D（A、B 都不在 D 之内）、C，在 C 中找到 `C::n` 就停了。`A::n` 要到全局这一层才并入。
</details>

!!! question "思考题 2"
    第 5 段要求转换函数名里的类型先按整个转换函数名的方式查找，第 6 段要求友元声明符里的名字先在 S 中搜索。两者的共同动机是什么？

<details markdown="1">
<summary>答案</summary>

一个名字的含义应当由它所指的那个声明的语境决定，而不是由使用处的语境决定。`x.operator T()` 指的是 `x` 的类中的转换函数，其中的 `T` 通常是那个类的成员；`friend void A::f(F)` 指的是 A 中已有的 `f`，`F` 应当按 A 中的含义理解。没有这两条，就很难甚至无法在别处指名这些声明。
</details>
