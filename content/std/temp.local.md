---
title: 局部声明的名字
summary: 类模板的注入类名何时是模板名、何时是类型名（X 还是 X<T>）；多个基类注入类名的二义如何消解；模板形参的名字不得在其作用域内被重新绑定；以及无限定查找中模板形参作用域排在类作用域之后，因此非依赖基类的成员会遮蔽同名模板形参。
status: done
covers: temp.local
papers: P1787R6
related: class.pre, temp.res, temp.dep.type, basic.scope.temp, basic.lookup.unqual, class.member.lookup, over.match.class.deduct
tags: 模板, 注入类名, 名字查找, 模板形参
updated: 2026-10-17
---

在类模板 `X` 的定义里写 `X`，它指的是什么？是模板 `X` 本身，还是当前这个特化 `X<T>`？如果基类恰好有一个成员叫 `T`，`T` 又指什么？本节 [[temp.local]]（locally declared names）回答的就是模板内部这些局部名字的问题，内容分两块：

1. **注入类名**（injected-class-name，¶1–¶5）：每个类都在自己的作用域里注入了自己的名字（[[class.pre#2]]）。对类模板来说，这个名字有双重身份，既能当模板名用，也能当类型名用。
2. **模板形参的名字**（¶6–¶7）：模板形参不能被同作用域内的后续声明重新绑定；而在无限定查找中，模板形参的作用域排在类作用域之后，这带来一个反直觉的后果。

前置知识：注入类名的一般规则见 [[class.pre]]；模板形参作用域见 [[basic.scope.temp]]；无限定查找的作用域顺序见 [[basic.lookup.unqual]]。

## 类模板的注入类名（¶1）

¶1 和普通类一样，类模板也有注入类名。它可以用作 *template-name*，也可以用作 *type-name*：

| 用法 | 含义 |
|---|---|
| 后面跟 *template-argument-list*：`X<int>` | 模板名，指类模板本身 |
| 作为类型模板模板形参的实参：`TT<X>` | 模板名 |
| 友元类模板声明里详述类型说明符的最后一个标识符：`template<class> friend class X;` | 模板名 |
| 其他所有情况 | 类型名，等价于 `X<` 模板头的实参列表 `>`，即 `X<T>`（对形参包是 `X<Ts...>`） |

```cpp run ok
#include <type_traits>
template<template<class> class> struct TT { };

template<class T> struct X {
    X* self;            // 类型名：X<T>*
    X<int>* other;      // 模板名 + 实参列表：X<int>*
    TT<X> tt;           // 模板模板实参：模板名，指 X 本身
};

template<class... Ts> struct P { using self = P; };    // P 即 P<Ts...>
static_assert(std::is_same_v<P<int, char>::self, P<int, char>>);
int main() { }
```

为什么要这样设计？在类模板内部，绝大多数时候你想表达的是当前这个特化本身：拷贝构造函数 `X(const X&)`、赋值运算符返回 `X&`、`X* next`……如果注入类名只能当模板名用，就得处处写 `X<T>`，模板形参一多就很啰嗦且易错。同时，又需要能在内部提到别的特化（`X<int>`）或模板本身（传给模板模板形参），所以注入类名需要根据语境切换身份。

### 注入类名会抑制 CTAD

一个实用后果：在类模板内部，`X(args)` 中的 `X` 是类型名 `X<T>`，不会进行类模板实参推导（[[over.match.class.deduct]]）。想要推导，必须用全局限定的 `::X` 绕开注入类名（¶5）：

```cpp run ok
#include <type_traits>
template<class T> struct X {
    T v;
    X(T t) : v(t) { }
    auto a() { return X(1.5); }      // 注入类名：X<T>，1.5 被转换为 T
    auto b() { return ::X(1.5); }    // 模板名：CTAD 推导出 X<double>
};
static_assert(std::is_same_v<decltype(X<int>(0).a()), X<int>>);
static_assert(std::is_same_v<decltype(X<int>(0).b()), X<double>>);
int main() { }
```

`X<int>::a()` 里的 `X(1.5)` 把 `1.5` 收窄成 `int`（Clang 会给出字面量转换警告），很容易写出这种 bug。

## 特化与部分特化的注入类名（¶2）

¶2 类模板的显式特化或部分特化也有注入类名，当用作类型名时，等价于模板名后跟该特化自己的模板实参：

```cpp run ok
template<template<class> class T> class A { };
template<class T> class Y;
template<> class Y<int> {
    Y* p;                                 // Y<int>
    Y<char>* q;                           // Y<char>
    A<Y>* a;                              // A<::Y>：模板模板实参，指模板本身
    class B {
        template<class> friend class Y;   // ::Y：友元类模板声明
    };
};

template<class T> class Y<T*> {
    Y* p;                                 // Y<T*>，不是 Y<T>
};
int main() { }
```

对部分特化 `Y<T*>`，注入类名 `Y` 指的是 `Y<T*>`，即部分特化的实参列表，而不是它自己的形参 `T` 组成的 `Y<T>`。这与 [[temp.dep.type#1]] 中当前实例化的定义一致。

## 在任何指名之处都可两用（¶3）

¶3 类模板或其特化的注入类名，无论从哪里指名，都可以用作模板名或类型名。重点在“从哪里”：注入类名是类的成员，所以会被继承，派生类可以通过限定名拿到基类的注入类名，并且它仍然保有双重身份。

```cpp run ok
template <class T> struct Base {
    Base* p;
};

template <class T> struct Derived : public Base<T> {
    typename Derived::Base* p;            // Derived::Base<T>：基类注入类名，用作类型名
};

template<class T, template<class> class U = T::template Base> struct Third { };
Third<Derived<int>> t;                    // OK：注入类名用作模板

int main() { }
```

`Derived::Base` 需要 `typename`：`Derived` 是当前实例化，`Base` 来自依赖基类 `Base<T>`，定义时查不到，于是按 [[temp.dep.type#5]] ¶5.4 是依赖名。

!!! impl "Clang 与标准例 2 的分歧"
    标准例 2 中写的是 `template<class> class U = T::Base`（没有 `template` 关键字），并注明 OK，即默认实参使用注入类名作模板。截至写作时（Clang 23），Clang 拒绝这种写法，提示模板模板形参的默认实参必须是类模板；加上 `template` 写成 `T::template Base` 后 Clang 接受。注意后一种写法（`template` 前缀后不跟实参列表）按 [[temp.names#11]] 已被弃用（[[depr.template.template]]），但仍然良构。

### 依赖基类的注入类名

¶3 还解释了一个常见的编译错误：在依赖基类的派生类里，无限定地写基类名：

```cpp error
template<class T> struct Base { Base(int) { } };
template<class T> struct D : Base<T> {
    D() : Base(0) { }        // error: Base 的注入类名在依赖基类里，定义时找不到
};
D<int> d;
```

```cpp run ok
template<class T> struct Base { Base(int) { } };
template<class T> struct D : Base<T> {
    D() : D::Base(0) { }     // OK：D::Base 是依赖名，实例化时找到 Base<int> 的注入类名
};
D<int> d;
int main() { }
```

无限定的 `Base` 在定义处查找：`D` 的作用域里没有，依赖基类不被搜索（[[class.member.lookup#4]]），继续向外在全局找到的是类模板 `::Base`，它没有实参列表，不是基类的名字。写 `Base<T>(0)` 或 `D::Base(0)` 都可以；后者在基类模板名很长时更方便。

## 多个注入类名的二义（¶4）

¶4 查找可能在多个基类里找到注入类名而产生二义（[[class.member.lookup]]）。但如果找到的注入类名全都指向同一个类模板的特化，并且这个名字被用作模板名，那么它指的是类模板本身，不是二义的：

```cpp run ok
template <class T> struct Base { };
template <class T> struct D2 : Base<int>, Base<char> {
    typename D2::template Base<double> d;   // OK：用作模板名，指类模板 Base
};
D2<int> d2;
int main() { }
```

```cpp error
template <class T> struct Base { };
template <class T> struct D2 : Base<int>, Base<char> {
    typename D2::Base b;                    // error: 二义：Base<int> 还是 Base<char>？
};
D2<int> d2;
```

用作类型名时，`Base` 分别是 `Base<int>` 和 `Base<char>`，确实二义；用作模板名时，两个都指同一个模板，二义只是表面上的。（标准例 3 写作 `typename Derived::Base<double>`，没有 `template` 关键字。按 [[temp.names#7]] ¶7.3.4 这是仅类型语境中的终端名，不需要 `template`；Clang 23 尚未实现这条，仍要求加 `template`。）

## 模板的正常名字（¶5）

¶5 使用模板的正常名字（来自外围作用域，而不是注入类名）时，它总是指类模板本身，而非某个特化：

```cpp error
template<class T> class X {
    X* p;           // X<T>
    X<T>* p2;
    X<int>* p3;
    ::X* p4;        // error: 缺少模板实参列表；::X 不是注入类名
};
```

`::X` 跳过了类作用域，在全局找到的是模板 `X`。在需要类型的位置使用不带实参的模板名，除了 CTAD 适用的场合（变量声明的初始化、函数式转型等）以外都是错误。上面的 CTAD 例子正是利用了这一点。

## 模板形参不得被重新绑定（¶6）

¶6 模板形参的名字，不得被绑定到任何后续声明上，只要那个声明的位点（locus）被该模板形参所属的作用域包含。

```cpp error
template<class T, int i> class Y {
    int T;                    // error: 模板形参被隐藏
    void f() {
        char T;               // error: 模板形参被隐藏
    }
    friend void T();          // OK：友元声明不在这里绑定名字
};

template<class X> class X;    // error: 被模板形参隐藏
```

这条规则消除了模板中一类很难读懂的代码：在类或函数内部，`T` 始终指那个模板形参，不会某行之后突然变成别的东西。注意它的覆盖面：

```cpp error
template<class T> struct S {
    template<class T> void f();      // error: 内层模板形参与外层同名
};
template<class T> void g(int T);     // error: 函数形参与模板形参同名
template<class T> struct S2 { void h(); };
template<class T> void S2<T>::h() {
    using T = int;                   // error: 成员定义的块作用域也被包含
}
```

为什么 `friend void T();` 可以？友元函数声明不会把名字绑定到类作用域里（[[class.friend]]、[[basic.scope.scope]]），它的名字目标作用域是最内层外围命名空间，不被模板形参作用域包含，所以没有违反 ¶6。

最后一行 `template<class X> class X;`：类模板的名字 `X` 的位点在其模板头之后，处于模板形参 `X` 的作用域内，也被禁止。

!!! note "与 C++20 之前措辞的区别"
    旧标准的写法是“模板形参不得在其作用域内（包括嵌套作用域）被重新声明”。[[P1787R6]] 把它改写为基于绑定与位点的表述，效果基本相同，但更清楚地解释了友元声明为什么不受影响。

## 模板形参作用域的查找顺序（¶7）

¶7 无限定名字查找时，*template-declaration* 的模板形参作用域，被安排在所声明模板关联的最外层作用域之后立即考虑，即使它的父作用域并不包含 *template-parameter-list*（例如类外定义的成员）。

注 1 点出了最重要的后果：类模板的作用域（包括其非依赖基类）在模板形参作用域之前被搜索。

```cpp run ok
struct B { };
namespace N {
    typedef void V;
    template<class T> struct A : B {
        typedef void C;
        void f();
        template<class U> void g(U);
    };
}

template<class V> void N::A<V>::f() {   // 这里不考虑 N::V
    V v{};                              // V 仍是模板形参，不是 N::V（void）
    (void)v;
}

template<class B> template<class C> void N::A<B>::g(C) {
    B b;                                // B 是基类 ::B，不是模板形参！
    C c;                                // C 是模板形参，不是 A 的成员 C
    static_assert(__is_same(B, ::B));
    (void)b; (void)c;
}

template void N::A<int>::f();
template void N::A<int>::g(int);
int main() { }
```

逐一分析三个名字（以无限定查找的作用域链 块 → 类 `A`（含基类）→ 模板形参 → 命名空间 `N` → 全局为准）：

- `f` 中的 `V`：`A` 里没有 `V`，接下来是 `f` 的模板形参作用域，找到形参 `V`。命名空间 `N` 里的 `typedef void V` 在模板形参之后才被考虑，因而被遮住。这是符合直觉的结果。
- `g` 中的 `B`：类 `A` 的作用域先被搜索，它的非依赖基类 `::B` 的注入类名 `B` 就在其中，于是找到的是基类，而不是外层模板形参 `B`。这个结果是反直觉的：写在模板头里的形参名被基类成员遮蔽了。
- `g` 中的 `C`：`g` 是成员模板，有两层模板头。先看“所声明模板关联的最外层作用域”：对 `C` 的那层模板头而言，所声明的是 `g`，它的最外层关联作用域是 `g` 的函数形参/块作用域，所以紧随其后的是 `C` 的模板形参作用域，在类作用域之前，`C` 指模板形参而不是 `A::C`。而 `B` 那一层模板头所声明的是类模板 `A` 的成员，其关联的最外层作用域是类 `A`，所以类作用域先于 `B` 被查。

!!! pitfall "非依赖基类的成员会遮蔽模板形参"
    ```cpp run ok
    #include <type_traits>
    struct NB { using U = int; };
    template<class U> struct E : NB {
        U y;            // NB::U（int），不是模板形参 U！
    };
    static_assert(std::is_same_v<decltype(E<double>::y), int>);
    int main() { }
    ```
    `E<double>::y` 的类型是 `int`。¶6 禁止的是在模板形参的作用域内再声明同名实体；`NB::U` 是在 `NB` 中声明的，不受 ¶6 约束，而查找顺序又让它先被找到。编译器对这种 bug 不报任何错误，所以给模板形参起 `value_type`、`size_type`、`U` 这类常见名字时要格外小心。

    依赖基类则不会造成这个问题：依赖基类在定义时不被搜索（[[temp.dep.type#3]]），所以 `template<class value_type> struct D : Base<value_type> { value_type x; };` 中的 `value_type` 始终是模板形参。

为什么标准选择这样的顺序？对类外定义的成员，这条规则保证写在类外和写在类内含义相同：类内定义 `A` 的成员函数时，类作用域本来就在外围模板头之内（更近），类外定义时 ¶7 把模板形参作用域安排在类作用域之后，模拟出同样的嵌套关系。代价就是上面这个陷阱。

## 历史与演进

!!! history "历史与演进"
    - C++98：注入类名、模板形参不可重声明、类外成员定义中的查找顺序等规则均已存在（当时散布在 [temp.local] 的若干段落中）。
    - 注入类名可以用作模板模板实参、多个基类注入类名用作模板名时不二义等规则，是 C++98 之后通过核心语言缺陷报告补充明确的。
    - C++17：引入 CTAD 后，注入类名是类型名而非模板名，这条规则意味着类模板内部的 `X(args)` 不做推导。
    - C++23：[[P1787R6]] 把 ¶6、¶7 改写为基于绑定、位点、模板形参作用域的精确表述（[[basic.scope.temp]]），其中 ¶7 那句“即使父作用域不包含模板形参列表”正是为类外成员定义而设。

## 思考题

!!! question "思考题 1"
    ```cpp
    template<class T> struct List {
        struct Node { Node* next; List* owner; };
    };
    ```
    `Node` 中的 `Node*` 和 `List*` 各指什么类型？

<details markdown="1">
<summary>答案</summary>

`Node` 是嵌套类的注入类名，指 `List<T>::Node`；`List` 是外层类模板的注入类名（从嵌套类内部仍然可以找到外层类的成员），用作类型名，指 `List<T>`。二者都是当前实例化（[[temp.dep.type#1]] ¶1.1）。
</details>

!!! question "思考题 2"
    ```cpp
    struct Base { using T = long; };
    template<class T> struct S : Base {
        T a;
        void f(T b);
    };
    ```
    `a` 和 `b` 的类型是什么？如果把基类换成 `template<class> struct Base2 { using T = long; };` 并写 `S : Base2<T>` 呢？

<details markdown="1">
<summary>答案</summary>

第一种情况：`S` 的类作用域（包括非依赖基类 `Base`）先于模板形参作用域被搜索，`T` 找到 `Base::T`，`a` 和 `b` 的类型都是 `long`，与模板实参无关。¶6 不适用，因为 `Base::T` 并非声明在模板形参的作用域内。

第二种情况：`Base2<T>` 是依赖基类，定义时不被搜索，`T` 就是模板形参。这两个版本只差一个基类是否依赖，含义却完全不同。
</details>

## 小结

| 规则 | 段落 | 要点 |
|---|---|---|
| 注入类名的双重身份 | ¶1 | 带实参列表 / 模板模板实参 / 友元类模板 → 模板名；其他 → `X<T...>` |
| 特化的注入类名 | ¶2 | 类型名用法等价于该特化自己的实参 |
| 继承来的注入类名 | ¶3 | 通过 `Derived::Base` 等方式指名时仍可两用 |
| 多基类注入类名 | ¶4 | 用作模板名时不二义 |
| 正常名字 | ¶5 | `::X` 总是模板本身，可触发 CTAD |
| 模板形参不得被重新绑定 | ¶6 | 成员、局部变量、内层模板形参、同名类模板都不行；友元函数可以 |
| 查找顺序 | ¶7 | 类作用域（含非依赖基类）先于模板形参作用域 |
