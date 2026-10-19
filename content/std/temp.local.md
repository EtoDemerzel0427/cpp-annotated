---
title: 局部声明的名字
summary: 在类模板内部，类名 X 什么时候指当前特化 X<T>、什么时候指模板本身；模板形参的名字不能被重新声明；以及非依赖基类的成员为什么会遮住同名的模板形参。
status: done
covers: temp.local
papers: P1787R6
related: class.pre, temp.res, temp.dep.type, basic.scope.temp, basic.lookup.unqual, class.member.lookup, over.match.class.deduct
tags: 模板, 注入类名, 名字查找, 模板形参
updated: 2026-10-19
---

!!! tldr
    - 在类模板 `X` 内部，单独写 `X` 指当前特化 `X<T>`；后面跟实参列表、作为模板模板实参、或在友元类模板声明里时，`X` 指模板本身。
    - 所以类模板内部的 `X(args)` 不做类模板实参推导；要推导就写 `::X(args)`。
    - 从依赖基类继承的类名在定义处查不到，成员初始化器里要写 `D::Base(...)` 或 `Base<T>(...)`。
    - 模板形参的名字在它的作用域内不能再被声明成别的东西，友元函数声明除外。
    - 无限定查找先搜索类作用域（包括非依赖基类），后搜索模板形参，所以非依赖基类里同名的成员会遮住模板形参，而且没有任何诊断。

## 类模板里的 X 指什么（¶1）

每个类都把自己的名字注入到自己的作用域里，这个名字叫[[g:injected-class-name|**注入类名**]]（injected-class-name，[[class.pre#2]]）。所以在类的定义里写类名，找到的是这个成员，而不是外层作用域的声明。

¶1 类模板也有注入类名，而且它有两种用法：

| 写法 | 含义 |
|---|---|
| 后面跟模板实参列表：`X<int>` | 模板名，指类模板本身 |
| 作为类型模板模板形参的实参：`TT<X>` | 模板名 |
| 友元类模板声明中详述类型说明符的最后一个标识符：`template<class> friend class X;` | 模板名 |
| 其他所有情况 | 类型名，等于 `X` 加上模板头的实参列表，即 `X<T>`；形参包对应 `X<Ts...>` |

```cpp run ok
#include <type_traits>
template<template<class> class> struct TT { };

template<class T> struct X {
    X* self;            // 类型名：X<T>*
    X<int>* other;      // 模板名加实参列表：X<int>*
    TT<X> tt;           // 模板模板实参：指模板 X 本身
};

template<class... Ts> struct P { using self = P; };    // P 即 P<Ts...>
static_assert(std::is_same_v<P<int, char>::self, P<int, char>>);
int main() { }
```

这样设计是因为在类模板内部，绝大多数时候要说的就是当前这个特化：拷贝构造函数 `X(const X&)`、赋值运算符返回的 `X&`、链表节点的 `X* next`。如果每处都要写 `X<T>`，模板形参一多就很啰嗦。同时又要能提到别的特化（`X<int>`）和模板本身（传给模板模板形参），所以按语境区分两种用法。

### 注入类名使 CTAD 不起作用

在类模板内部，`X(args)` 里的 `X` 是类型名 `X<T>`，不会进行类模板实参推导（CTAD，[[over.match.class.deduct]]）。要推导，就用 `::X` 绕开注入类名（¶5）：

```cpp run ok
#include <type_traits>
template<class T> struct X {
    T v;
    X(T t) : v(t) { }
    auto a() { return X(1.5); }      // X<T>：1.5 被转换为 T
    auto b() { return ::X(1.5); }    // 模板名：推导出 X<double>
};
static_assert(std::is_same_v<decltype(X<int>(0).a()), X<int>>);
static_assert(std::is_same_v<decltype(X<int>(0).b()), X<double>>);
int main() { }
```

`X<int>::a()` 里的 `X(1.5)` 把 `1.5` 转换成 `int` 值 `1`。Clang 23 对此给出 `-Wliteral-conversion` 警告，但这种写法很容易在没有警告的情况下藏住 bug。

### 外层作用域的名字总是指模板（¶5）

¶5 如果用的是模板的正常名字，也就是外围作用域里的名字而不是注入类名，它总是指类模板本身：

```cpp error
template<class T> class X {
    X* p;           // X<T>
    X<T>* p2;
    X<int>* p3;
    ::X* p4;        // error: 缺少模板实参列表
};
```

`::X` 跳过了类作用域，在全局找到模板 `X`。在需要类型的地方单独写模板名，只有 CTAD 适用的场合（带初始化器的变量声明、函数式转型等）才合法，数据成员不属于这种场合。

## 特化的注入类名（¶2）

¶2 类模板的显式特化和部分特化也有注入类名。用作类型名时，它等于模板名加上这个特化自己的模板实参：

```cpp run ok
template<template<class> class T> class A { };
template<class T> class Y;
template<> class Y<int> {
    Y* p;                                 // Y<int>
    Y<char>* q;                           // Y<char>
    A<Y>* a;                              // A<::Y>：指模板本身
    class B {
        template<class> friend class Y;   // ::Y
    };
};

template<class T> class Y<T*> {
    Y* p;                                 // Y<T*>，不是 Y<T>
};
int main() { }
```

在部分特化 `Y<T*>` 里，`Y` 指 `Y<T*>`，即部分特化的实参列表，而不是由它的形参组成的 `Y<T>`。

## 继承来的注入类名（¶3）

¶3 类模板或其特化的注入类名，无论从哪里指名，都既可以当模板名也可以当类型名。注入类名是类的成员，所以会被继承。派生类可以通过限定名拿到基类的注入类名，两种用法都还在：

```cpp run ok
template <class T> struct Base {
    Base* p;
};

template <class T> struct Derived : public Base<T> {
    typename Derived::Base* p;    // Derived::Base<T>：用作类型名
};

template<class T, template<class> class U = T::template Base> struct Third { };
Third<Derived<int>> t;            // OK: 注入类名用作模板

int main() { }
```

`Derived::Base` 需要 `typename`：`Base` 来自依赖基类 `Base<T>`，定义处查不到，按 [[temp.dep.type#5]] 是依赖名。

!!! impl "Clang 与标准例 2 的分歧"
    标准例 2 写的是 `template<class> class U = T::Base`，没有 `template` 关键字，并注明 OK。Clang 23 拒绝这种写法，报告模板模板形参的默认实参必须是类模板；写成 `T::template Base` 后接受。后一种写法（`template` 后面不跟实参列表）已被弃用（[[depr.template.template]]），但仍然良构。

### 依赖基类的类名在定义处查不到

¶3 解释了一个常见的编译错误：

<div class="compare" markdown="1">

```cpp error
template<class T>
struct Base { Base(int) { } };
template<class T>
struct D : Base<T> {
  D() : Base(0) { }  // error
};
D<int> d;
```

```cpp run ok
template<class T>
struct Base { Base(int) { } };
template<class T>
struct D : Base<T> {
  D() : D::Base(0) { }  // OK
};
D<int> d;
int main() { }
```

</div>

左边无限定的 `Base` 在定义处查找。`D` 自己的作用域里没有它，依赖基类不被搜索（[[class.member.lookup#4]]），于是继续向外，在全局找到类模板 `::Base`。没有实参列表的模板名不是基类的名字，Clang 报告它既不是数据成员也不是基类。

右边的 `D::Base` 是依赖的限定名，实例化时在 `D<int>` 中找到基类 `Base<int>` 的注入类名。写 `Base<T>(0)` 也可以，基类模板名很长时 `D::Base` 更方便。

## 多个基类的注入类名（¶4）

¶4 查找在多个基类里都找到注入类名时，可能产生二义（[[class.member.lookup]]）。但如果找到的注入类名都是同一个类模板的特化，而这个名字被当作模板名用，那么它指类模板本身，不算二义：

<div class="compare" markdown="1">

```cpp error
template <class T> struct Base { };
template <class T>
struct D2 : Base<int>, Base<char> {
  typename D2::Base b;
  // error: Base<int> 还是 Base<char>？
};
D2<int> d2;
```

```cpp run ok
template <class T> struct Base { };
template <class T>
struct D2 : Base<int>, Base<char> {
  typename D2::Base<double> d;
  // OK: 指模板 Base
};
D2<int> d2;
int main() { }
```

</div>

当作类型名时，`Base` 分别是 `Base<int>` 和 `Base<char>`，确实二义。当作模板名时，两个都指同一个模板，二义只是表面上的。这里的 `Base` 是非依赖基类的成员，定义处就能查到是模板，所以 `<` 前不需要写 `template`。

## 模板形参不能被重新声明（¶6）

¶6 模板形参的名字不得绑定到后面的声明上，只要那个声明的位点（locus，名字开始生效的位置，见 [[basic.scope.pdecl]]）落在这个模板形参所属的作用域内。

```cpp error
template<class T, int i> class Y {
    int T;                    // error: 模板形参被隐藏
    void f() {
        char T;               // error: 模板形参被隐藏
    }
    friend void T();          // OK: 友元声明不在这里绑定名字
};

template<class X> class X;    // error: 被模板形参隐藏
```

有了这条规则，在模板内部 `T` 始终指那个模板形参，不会在某一行之后变成别的东西。它的覆盖面很广：

```cpp error
template<class T> struct S {
    template<class T> void f();      // error: 内层模板形参与外层同名
};
template<class T> void g(int T);     // error: 函数形参与模板形参同名
template<class T> struct S2 { void h(); };
template<class T> void S2<T>::h() {
    using T = int;                   // error: 类外成员定义的函数体也在范围内
}
```

`friend void T();` 可以，是因为友元函数声明不把名字绑定到类作用域里（[[class.friend]]、[[basic.scope.scope]]），它的目标作用域是最内层的外围命名空间，不在模板形参的作用域内。

`template<class X> class X;` 中，类模板名 `X` 的位点在模板头之后，落在模板形参 `X` 的作用域内，所以也被禁止。

!!! note "与 C++23 之前措辞的区别"
    C++20 及以前的写法是"模板形参不得在其作用域内（包括嵌套作用域）被重新声明"。[[P1787R6]] 把它改写为基于绑定和位点的表述，效果基本相同，但能直接说明友元声明为什么不受影响。

## 查找时先找类成员，再找模板形参（¶7）

!!! pitfall "非依赖基类的成员会遮住模板形参"
    ```cpp run ok
    #include <type_traits>
    struct NB { using U = int; };
    template<class U> struct E : NB {
        U y;            // NB::U（int），不是模板形参 U
    };
    static_assert(std::is_same_v<decltype(E<double>::y), int>);
    int main() { }
    ```
    `E<double>::y` 的类型是 `int`。¶6 只禁止在模板形参的作用域内声明同名实体，`NB::U` 声明在 `NB` 里，不受限制；而查找顺序又让它先被找到。编译器对此不给任何诊断，所以给模板形参起 `value_type`、`size_type` 这类常见的名字时要小心。

    依赖基类不会造成这个问题，因为定义处不搜索依赖基类（[[temp.dep.type#3]]）。`template<class value_type> struct D : Base<value_type> { value_type x; };` 中的 `value_type` 始终是模板形参。

¶7 无限定查找时，模板声明的模板形参作用域，被安排在所声明模板关联的最外层作用域之后立即考虑，即使模板形参列表实际上并不在那个作用域的外面（例如类外定义的成员）。

注 1 指出了最重要的后果：类模板的作用域，包括它的非依赖基类，在模板形参作用域之前搜索。上面的陷阱就是这样产生的。标准的例 6 展示了类外成员定义中的三种情况：

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
    V v{};                              // V 是模板形参，不是 N::V
    (void)v;
}

template<class B> template<class C> void N::A<B>::g(C) {
    B b;                                // B 是基类 ::B，不是模板形参
    C c;                                // C 是模板形参，不是 A::C
    static_assert(__is_same(B, ::B));
    (void)b; (void)c;
}

template void N::A<int>::f();
template void N::A<int>::g(int);
int main() { }
```

- `f` 中的 `V`：类 `A` 里没有 `V`，接下来是模板形参作用域，找到形参 `V`。命名空间 `N` 的 `typedef void V` 排在模板形参之后，被遮住。
- `g` 中的 `B`：外层模板头声明的是类模板 `A` 的成员，它关联的最外层作用域是类 `A`。所以先搜索类 `A`，在非依赖基类 `::B` 中找到注入类名 `B`，模板形参 `B` 被遮住。
- `g` 中的 `C`：内层模板头声明的是成员模板 `g`，它关联的最外层作用域是 `g` 的函数形参作用域。模板形参 `C` 紧随其后，排在类 `A` 之前，所以 `C` 指模板形参而不是 `A::C`。

为什么这样安排？这样类外定义的成员与写在类内时含义相同。成员函数写在类内时，类作用域本来就比外围的模板头更近；写到类外后，¶7 把模板形参作用域排在类作用域之后，模拟出同样的嵌套关系。代价就是上面的陷阱。

!!! history "历史与演进"
    - C++98 已经有注入类名、模板形参不可重新声明、类外成员定义中的查找顺序这些规则。
    - 类模板的注入类名可以当模板名用，是 C++03 通过缺陷报告 [[CWG176]] 明确的。
    - C++17 引入 CTAD 之后，注入类名在类模板内部是类型名这一点，意味着 `X(args)` 不做推导。
    - C++23 的 [[P1787R6]] 把 ¶6、¶7 改写为基于绑定、位点和模板形参作用域（[[basic.scope.temp]]）的表述。¶7 中"即使父作用域不包含模板形参列表"一句，就是为类外成员定义写的。

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

`Node` 是嵌套类的注入类名，指 `List<T>::Node`。`List` 是外层类模板的注入类名，嵌套类内部仍然能找到外层类的成员；这里用作类型名，指 `List<T>`。两者都是当前实例化（[[temp.dep.type#1]]）。
</details>

!!! question "思考题 2"
    ```cpp
    struct Base { using T = long; };
    template<class T> struct S : Base {
        T a;
        void f(T b);
    };
    ```
    `a` 和 `b` 的类型是什么？如果把基类换成 `template<class> struct Base2 { using T = long; };`，写成 `S : Base2<T>` 呢？

<details markdown="1">
<summary>答案</summary>

第一种情况：`S` 的类作用域（包括非依赖基类 `Base`）先于模板形参作用域被搜索，`T` 找到 `Base::T`，`a` 和 `b` 都是 `long`，与模板实参无关。¶6 不适用，因为 `Base::T` 不是声明在模板形参的作用域内。

第二种情况：`Base2<T>` 是依赖基类，定义处不搜索，`T` 就是模板形参。两个版本只差基类是否依赖，含义却完全不同。
</details>

## 小结

| 规则 | 段落 | 要点 |
|---|---|---|
| 注入类名的两种用法 | ¶1 | 带实参列表、模板模板实参、友元类模板时是模板名；其他时候是 `X<T...>` |
| 特化的注入类名 | ¶2 | 类型名等于该特化自己的实参 |
| 继承来的注入类名 | ¶3 | 通过 `Derived::Base` 指名时两种用法都还在 |
| 多个基类的注入类名 | ¶4 | 当作模板名时不二义 |
| 外层作用域的名字 | ¶5 | `::X` 总是模板本身，可以触发 CTAD |
| 模板形参不能被重新声明 | ¶6 | 成员、局部变量、内层模板形参、同名类模板都不行；友元函数可以 |
| 查找顺序 | ¶7 | 类作用域（含非依赖基类）先于模板形参作用域 |
