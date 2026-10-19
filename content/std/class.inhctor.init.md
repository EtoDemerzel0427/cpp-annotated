---
title: 通过继承的构造函数初始化
summary: using B::B 让基类的构造函数参与派生类的构造；被选中时，基类子对象由它初始化，派生类的其余部分如同由预置的默认构造函数初始化。
status: done
since: c++11
papers: N2540, P0136R1, P2582R1
related: namespace.udecl, class.base.init, over.match.funcs, over.match.best, class.default.ctor, class.copy.ctor, dcl.init.aggr
tags: 构造函数, 继承构造函数, using 声明
updated: 2026-10-19
---

!!! tldr
    - `using B::B;` 之后，`B` 的构造函数在构造 `D` 时也是候选。被选中时，`B` 子对象由它初始化，`D` 的其余基类和成员如同由预置的默认构造函数初始化。
    - C++17 起调用的就是基类构造函数本身：默认实参、`explicit`、`constexpr`、访问权限都原样保留，实参直接初始化基类构造函数的形参，没有中间的复制。
    - 派生类自己声明的同形参构造函数会隐藏继承来的那个；只有一个实参时，基类的复制和移动构造函数不参与构造 `D`。
    - 如果 `B` 是虚基类且这次初始化不负责构造它，继承构造函数的调用连同实参求值一起省略。
    - 同一个构造函数经由多个 `B` 类型的基类子对象继承而来时，程序非良构。

## `using B::B;` 是什么

```cpp
struct D : B {
    D(int x) : B(x) {}
    D(int x, double y) : B(x, y) {}
    D(const char* s) : B(s) {}
    // 基类每加一个构造函数，这里就要跟着加
};
```

派生类只是在基类上加一点东西时，把基类的每个构造函数都转发一遍很繁琐。C++11 的**继承构造函数**（[[g:inherited-constructor|inheriting constructor]]）用一行 `using B::B;` 代替这些转发。

它的规则分在两处。[[namespace.udecl]] 规定 `using B::B;` 是什么：在查找 `D` 的构造函数、形成重载候选集时，`B` 的构造函数被当作 `D` 的构造函数（[[namespace.udecl#13]]）。本页 [[class.inhctor.init]] 规定这样的构造函数被选中以后，`D` 对象怎样初始化。

C++17 通过 [[P0136R1]] 重写了这套规则。C++11/14 的旧模型是为派生类合成一组转发构造函数；C++17 起不再合成，候选就是基类构造函数本身。网上不少旧资料描述的是旧模型。

### 哪些构造函数能用

```cpp run title="hiding.cpp" ok
#include <cstdio>

struct B {
    B(int x, int y = 7) { std::printf("B(%d,%d)\n", x, y); }
    B(const char*)      { std::puts("B(const char*)"); }
};

struct D : B {
    using B::B;
    D(const char*) : B(1, 1) { std::puts("D(const char*)"); }
    int m = 42;
};

int main() {
    D a(1);     // B(1,7)：默认实参照常可用
    D b("x");   // B(1,1) / D(const char*)
    return a.m == 42 ? 0 : 1;   // m 用默认成员初始化器
}
```

决定候选集的规则有这几条：

- `D` 自己声明了形参列表相同的构造函数时，基类那个不被继承（[[namespace.udecl#11]]）。上例中 `D(const char*)` 隐藏了 `B(const char*)`。
- `D a(1)` 调用的就是 `B(int, int = 7)` 本身，所以默认实参可用。旧模型下，派生类会为每种省略尾部默认实参的形参列表各合成一个构造函数，它们自己没有默认实参，过去常说默认实参不被继承就是指这个。
- `using B::B;` 不算用户声明的构造函数，`D` 照常有隐式声明的默认构造函数、复制和移动构造函数。当 `D` 的构造函数和继承来的构造函数对所有实参的形参类型都相同时，派生类的胜出（[[over.match.best#2.7]]）。
- 只有一个实参时，继承来的、首个形参为 `B` 的引用的构造函数（复制、移动构造函数之类）不是构造 `D` 的候选（[[over.match.funcs#9]]）。

最后一条的效果是不能用一个 `B` 对象构造 `D`：

```cpp title="no-copy-from-base.cpp" error
struct B {
    B(int) {}
    B(const B&) = default;
};
struct D : B { using B::B; };

void f() {
    B bb(3);
    D d(bb);   // error: B(const B&) 不是候选
}
```

如果允许，`D d(bb);` 会得到一个只有 `B` 部分来自 `bb`、其余部分默认初始化的 `D`，几乎总是错误。需要这种构造时显式写 `D(const B& b) : B(b) {}`。

### 属性原样保留

```cpp title="properties.cpp" error
struct B {
    B(int) {}
    explicit B(double) {}
    constexpr B(long) {}
protected:
    B(char) {}
};
struct D : B { using B::B; };

constexpr D cd(1L);  // OK：B(long) 是 constexpr
D d1(2.0);           // OK：直接初始化
D d2 = 2.0;          // error: 不考虑 explicit B(double)，
                     //   B(int) 与 B(char) 二义
D d3('c');           // error: B(char) 是 protected
```

`d3` 说明了 [[namespace.udecl#16]]：继承来的构造函数，在用它构造 `B` 对象时可访问的地方才可访问，*using-declaration* 本身写在哪个访问说明符下被忽略。所以即使把 `using B::B;` 放在 `public:` 下，也不能把 protected 构造函数变成 public 的。普通成员函数的 *using-declaration* 才能改变访问权限。

## 被选中之后怎样初始化（¶1）

¶1 类型 `B` 的构造函数被用来初始化另一个类型 `D` 的对象时（即它是继承来的），初始化如同用一个预置的默认构造函数初始化 `D` 对象，以及继承路径上的每个基类子对象；唯一的例外是 `B` 子对象由这个继承的构造函数初始化。

直观地说，选中 `using B::B;` 带来的构造函数，大致相当于写了：

```text
D(args...) : B(args...) {}
// 其余基类和成员：有默认成员初始化器就用，否则默认初始化
```

但有三点与手写的转发构造函数不同。

### 形参只初始化一次

```cpp run title="single-call.cpp" ok
#include <cstdio>

struct NM {
    NM(int) { std::puts("NM(int)"); }
    NM(const NM&) = delete;   // 不可复制，也不可移动
};
struct B { B(NM) { std::puts("B(NM)"); } };
struct D : B { using B::B; };

int main() {
    D d(1);   // NM(int) / B(NM)
}
```

¶1 第三句：整个初始化被视为一次函数调用；除非被省略（见下一小节），继承构造函数的形参先于 `D` 对象的任何部分初始化。实参直接初始化 `B::B` 的形参，没有派生类构造函数的形参这一层，也就没有额外的复制或移动。

同一段代码用 `-std=c++14` 编译，本机 Clang 23 报告 copying parameter of type 'NM' invokes deleted constructor：旧模型合成的转发构造函数要把形参再传给 `B`。手写的转发构造函数也有同样的问题。

### 虚基类不归它初始化时，整个调用被省略

```cpp run title="omitted.cpp" ok
#include <cstdio>

struct V {
    V() { std::puts("V()"); }
    V(int) { std::puts("V(int)"); }
};
struct Q { Q() {} };
struct A : virtual V, Q {
    using V::V;
    A() = delete;
};
int bar() { std::puts("bar()"); return 42; }
struct B : A {
    B() : A(bar()) {}   // 选中的是 A 继承来的 V(int)
};
struct C : B {};

int main() {
    C c;   // 按标准：只输出 V()
}
```

¶1 第二句：如果 `B` 子对象不应作为 `D` 对象的一部分初始化，继承构造函数的调用，包括实参的求值，被省略。典型情形是 `B` 为虚基类，而 `D` 不是最派生类：虚基类只由最派生类初始化（[[class.base.init#15]]）。

这是标准例 2。`A(bar())` 选中的是继承来的 `V(int)`，但 `A` 子对象不是最派生对象，`V` 不作为 `A` 的一部分初始化，于是 `V(int)` 的调用连同 `bar()` 一起省略。`V` 由最派生类 `C` 默认初始化，输出 `V()`。`A() = delete;` 不妨碍这一切，因为 `A` 的其余部分（`Q` 子对象）如同由预置的默认构造函数初始化，并没有调用被删除的 `A()`。

把 `main` 改成 `B b;` 结论相同：`A` 子对象永远不是最派生对象，`V` 总是由 `B` 初始化。

!!! warning "Clang 与标准不一致"
    本机 Clang 23 运行上例输出 `V()`，然后输出 `bar()`。它正确地没有调用 `V(int)`，却仍然求值了实参 `bar()`，与 ¶1 的 including the evaluation of any arguments 不符。改成 `B b;` 也一样。

### 路径上的中间类

```cpp run title="chain.cpp" ok
struct W { W(int) {} };
struct X : virtual W { using W::W; X() = delete; };
struct Y : X { using X::X; };
struct Z : Y, virtual W { using Y::Y; };

int main() {
    Z z(0);   // OK
}
```

`Z z(0)` 选中的是经由 `Y`、`X` 一路继承到 `Z` 的 `W(int)`。初始化如同用预置的默认构造函数初始化 `Z` 以及路径上的 `Y`、`X`，而 `W`（`Z` 是最派生类，所以虚基类 `W` 由 `Z` 初始化）由 `W(0)` 初始化。`X() = delete` 不相干：`X` 子对象如同由预置默认构造函数初始化，它唯一没有默认构造方式的子对象 `W` 已经由继承构造函数负责了。

### 新增的成员必须能默认初始化

```cpp title="d1-d2.cpp" error
struct B1 { B1(int, ...) {} };
struct B2 { B2(double) {} };
int get();

struct D1 : B1 {
    using B1::B1;   // 继承 B1(int, ...)
    int x;
    int y = get();
};

void test() {
    D1 d(2, 3, 4);  // OK：B1(2, 3, 4)，x 不初始化，y = get()
    D1 e;           // error: D1 没有默认构造函数
}

struct D2 : B2 {
    using B2::B2;
    B1 b;           // B1 没有默认构造函数
};

D2 f(1.0);          // error: b 无法默认初始化
```

继承的构造函数只负责基类那一部分。`D1 d(2, 3, 4)` 中 `x` 是默认初始化的，没有值；`D2 f(1.0)` 失败，因为成员 `b` 要像在预置默认构造函数中那样初始化，而 `B1` 没有默认构造函数。给派生类新增的成员写默认成员初始化器，可以避免这两种问题。

标准例 1 最后用一个模板展示了继承构造函数的典型用途，包装任意类：

```cpp run title="log-wrapper.cpp" ok
#include <iostream>
#include <string>

template<class T> struct Log : T {
    using T::T;   // 继承 T 的全部构造函数
    ~Log() { std::clog << "Destroying wrapper\n"; }
};

int main() {
    Log<std::string> s(3, 'x');      // std::string(size_type, char)
    std::cout << s << std::endl;     // xxx
}                                    // Destroying wrapper
```

## 经由多个同类型子对象继承（¶2）

```cpp title="multiple-subobjects.cpp" error
struct A { A(int) {} };
struct B : A { using A::A; };

struct C1 : B { using B::B; };
struct C2 : B { using B::B; };
struct D1 : C1, C2 {
    using C1::C1;
    using C2::C2;
};
D1 d1(0);   // error: 两个 B 子对象，用哪一个？

struct V1 : virtual B { using B::B; };
struct V2 : virtual B { using B::B; };
struct D2 : V1, V2 {
    using V1::V1;
    using V2::V2;
};
D2 d2(0);   // OK：只有一个虚基类 B 子对象

struct M { M() {} M(int) {} };
struct N : M { using M::M; };
struct O : M {};
struct P : N, O { using N::N; using O::O; };
P p(0);     // OK：只有经由 N 的这一条
```

¶2 如果被选中的构造函数是从多个 `B` 类型的基类子对象继承来的，程序非良构。要数的是子对象：非虚继承的菱形里有两个 `B` 子对象，虚继承的菱形里只有一个。

`D2 d2(0)` 初始化虚基类 `B`（`B` 再用 `A(0)` 初始化它的基类 `A`），然后如同由预置默认构造函数初始化 `V1` 和 `V2`。`P p(0)` 合法，是因为 `O` 没有写 `using M::M;`，`using O::O;` 只带来 `O` 自己的隐式构造函数。于是 `N` 里的 `M` 由 `M(0)` 初始化，`O` 里的 `M` 由 `M()` 初始化。

## 初始化何时完成（¶3）

¶3 对象由继承的构造函数初始化时，所有子对象的初始化都完成，对象的初始化才完成。

这对应于 [[class.base.init#11]] 的“非委托构造函数返回时初始化完成”。继承构造函数的情形里，被调用的是 `B` 的构造函数，它返回时 `D` 的成员还没有初始化，所以不能以构造函数返回为准。完成的时刻决定了对象生命周期何时开始（[[basic.life]]），也决定了异常时是否调用 `D` 的析构函数：按本节初始化的子对象是“已知被初始化”的，异常时会被析构（[[except.ctor#3]] 第 3.3 项），而 `D` 本身的析构函数只有在初始化完成后才会调用。

## 其他相关规则

- 有继承构造函数的类不是聚合（[[dcl.init.aggr]]）。
- C++23 起，类模板实参推导也会考虑继承来的构造函数（[[over.match.class.deduct]]，[[P2582R1]]），并有相应的决胜规则 [[over.match.best#2.10]]。截至写作时，本机 Clang 23 还不支持：`template<class T> struct D : B<T> { using B<T>::B; }; D d(1);` 推导失败。

!!! impl "Clang 生成的符号"
    C++17 模型下，Clang 为每个实际用到的继承构造函数在派生类中生成一个构造函数实体，它接收与基类构造函数相同的形参，按 ¶1 完成初始化。Itanium ABI 为它定义了专门的名字修饰：`CI1`、`CI2`（完整对象、基类子对象版本）后接基类类型。例如 `struct D : B { using B::B; int m = 1; };` 中继承的 `B(int)`，本机 Clang 23 生成 `_ZN1DCI11BEi` 和 `_ZN1DCI21BEi`。

## 历史与演进

!!! history
    - C++11 通过 [[N2540]] 引入继承构造函数，模型是合成：对基类的每个构造函数（复制、移动、默认构造函数除外），按每种省略尾部默认实参的形参列表，在派生类中隐式声明一个同形参的构造函数并转发给基类。按值传递的形参因此多一次复制或移动，默认实参不保留，不可移动的形参类型无法使用。
    - C++17 的 [[P0136R1]] 改成现行模型：基类构造函数直接作为派生类的构造候选。默认实参、`explicit`、模板、访问权限随之自然保留；复制和移动构造函数不继承改写成 [[over.match.funcs#9]] 的候选排除规则。
    - C++23 的 [[P2582R1]] 让类模板实参推导也能使用继承的构造函数。

## 思考题

!!! question "思考题 1"
    下面的程序输出什么？删掉 `S(int)` 之后呢？

    ```cpp
    #include <cstdio>
    struct B {
        B(int)  { std::puts("B(int)"); }
        B(long) { std::puts("B(long)"); }
    };
    struct S : B {
        using B::B;
        S(int) : B(0L) { std::puts("S(int)"); }
    };
    int main() { S s(1); }
    ```

<details markdown="1">
<summary>答案</summary>

输出 `B(long)` 和 `S(int)`。`S(int)` 与 `B(int)` 形参列表相同，按 [[namespace.udecl#11]]，`B(int)` 不被继承。候选只有 `S(int)` 和继承来的 `B(long)`，前者精确匹配。

删掉 `S(int)` 后，候选是继承来的 `B(int)` 和 `B(long)`，选中 `B(int)`，输出 `B(int)`。
</details>

!!! question "思考题 2"
    `struct B { B(int); }; struct D : B { using B::B; std::string s; };` 中，`D d(1);` 的 `B::B(int)` 形参初始化、`B` 子对象初始化、`s` 的初始化按什么顺序发生？如果 `s` 的初始化抛出异常，会调用哪些析构函数？

<details markdown="1">
<summary>答案</summary>

顺序是形参、`B` 子对象、`s`。¶1 规定形参先于 `D` 的任何部分初始化，其余部分按 [[class.base.init#15]] 的顺序。

`s` 的构造抛出异常时，`B` 子对象已经初始化完成，是已知被初始化的子对象（[[except.ctor#3]] 第 3.3 项），所以调用 `B::~B()`。`D` 的初始化没有完成，不调用 `D::~D()`。
</details>
