---
title: 通过继承的构造函数初始化
summary: using Base::Base 让基类构造函数直接参与派生类的构造：被选中时，基类子对象由它初始化，其余部分如同预置的默认构造函数；整个过程算一次函数调用；虚基类不由中间类初始化时整个调用（含实参求值）被省略；从多个同类型基类子对象继承同一构造函数非良构
status: done
since: c++11
papers: N2540, P0136R1
related: namespace.udecl, class.base.init, over.match.funcs, over.match.best, class.default.ctor, class.copy.ctor, dcl.init.aggr
tags: 构造函数, 继承构造函数, using 声明
updated: 2026-10-17
---

写一个"只是在基类上加点东西"的派生类时，最烦人的是把基类的每个构造函数都转发一遍：

```cpp
struct D : B {
    D(int x) : B(x) {}
    D(int x, double y) : B(x, y) {}
    D(const char* s) : B(s) {}
    // ……基类每加一个构造函数，这里就要跟着加
};
```

**继承构造函数**（inheriting constructors，C++11）用一行 `using B::B;` 解决这个问题。它的规则分在两处：

- [[namespace.udecl]] 规定 `using B::B;` **是什么**：它让 `B` 的构造函数在查找 `D` 的构造函数、形成重载候选集时，被当作 `D` 的构造函数（[[namespace.udecl#13]]）；
- 本节 [[class.inhctor.init]] 规定这样一个构造函数被**选中之后**，`D` 对象**如何初始化**。

C++17 通过 [[P0136R1]] 彻底重写了这套规则。读网上旧资料时尤其要注意：C++11/14 的"继承构造函数会为派生类**合成**一组新构造函数"的说法，在 C++17 起已经**不成立**了。

## 先看 using-declaration 这一半

在进入本节之前，先把 [[namespace.udecl]] 中与构造函数相关的规则集中梳理一遍：

| 规则 | 出处 |
|---|---|
| *using-declarator* 的 *nested-name-specifier* 的终端名与 *unqualified-id* 相同（`B::B`）时，它指名构造函数 | [[namespace.udecl#1]] |
| 指名构造函数时，类**继承**该名字的整个构造函数声明集合 | [[namespace.udecl#2]] |
| 必须指名**直接基类**（模板中可以是依赖基类） | [[namespace.udecl#3]] |
| 派生类中声明了"对应的"构造函数（参数列表相同），则同签名的基类构造函数**不被继承**（隐藏） | [[namespace.udecl#11]] |
| 继承的构造函数在查找派生类构造函数、形成重载候选集时被当作派生类的构造函数 | [[namespace.udecl#13]] |
| 指名构造函数的 *using-declarator* 不做访问检查 | [[namespace.udecl#14]] |
| 继承的构造函数的可访问性 = 用它构造**基类**对象时的可访问性；using-declaration 本身的访问说明被忽略 | [[namespace.udecl#16]] |

此外还有两条来自重载决议的规则：

- [[over.match.funcs#9]]：从类 `C` 继承来的、首个形参为"对 *cv1* `P` 的引用"的构造函数，在构造 `D` 且**只有一个实参**、`C` 与 `P` 引用相关、`P` 与 `D` 引用相关时，被**排除**出候选集——这就是"复制/移动构造函数不被继承"的现代表述；
- [[over.match.best#2.7]]：派生类构造函数与基类构造函数对所有实参的形参类型都相同时，**派生类的胜出**。

这几条一起决定了"哪些构造函数能被继承、哪些被隐藏"，下面分别举例。

### 派生类自己的构造函数隐藏同签名的继承构造函数

```cpp run title="hiding.cpp" ok
#include <cstdio>

struct B {
    B(int x, int y = 7) { std::printf("B(%d,%d)\n", x, y); }
    B(const char*)      { std::puts("B(const char*)"); }
};

struct D : B {
    using B::B;
    D(const char*) : B(1, 1) { std::puts("D(const char*)"); }  // 隐藏 B(const char*)
    int m = 42;
};

int main() {
    D a(1);      // B(1,7)：继承的 B(int, int = 7)，默认实参照常可用
    D b("x");    // B(1,1) / D(const char*)：派生类自己的构造函数
    return a.m == 42 ? 0 : 1;   // 继承构造函数也会用默认成员初始化器初始化 m
}
```

### 默认实参：C++17 起直接使用基类构造函数的默认实参

上例中 `D a(1)` 调用的就是 `B::B(int, int = 7)` **本身**，默认实参 `7` 自然可用。这是 C++17 的新模型：继承的构造函数**不是**派生类的新函数，而是基类构造函数在派生类构造函数查找中"露面"。

C++11/14 的旧模型则完全不同：对于带默认实参的基类构造函数，派生类会**隐式声明**一组构造函数——每种"省略尾部若干默认实参"的形参列表各一个，而这些合成的构造函数自己**没有**默认实参。所以过去常说"默认实参不会被继承"——在 C++17 下，这句话应理解为"派生类不会获得带默认实参的新构造函数，而是直接调用基类那个"，可观察效果上默认实参是生效的。

### 默认构造函数：派生类的隐式默认构造函数优先

`using B::B;` **不算**用户声明的构造函数，所以如果 `D` 没有其他用户声明的构造函数，`D` 仍然会有隐式声明的默认构造函数（[[class.default.ctor]]）。当 `B` 也有一个可以零实参调用的构造函数时，二者冲突靠 [[over.match.best#2.7]] 解决：派生类的胜出。

```cpp run title="default-ctor.cpp" ok
#include <cstdio>

struct A { A(int = 0) { std::puts("A(int = 0)"); } };

struct B : A {
    using A::A;
    B() { std::puts("B()"); }
};

int main() {
    B b;   // A(int = 0) / B()：B::B() 与 A::A(int = 0) 对零个实参都可行，
           // 由 [over.match.best]/2.7 选择派生类的 B::B()
}
```

如果 `B` 没有默认构造函数，`D` 的隐式默认构造函数被定义为删除的；`D d;` 非良构——基类那个"没有默认构造函数"的事实不会因为继承而改变。

### 复制/移动构造函数不被继承

`B(const B&)` 在构造 `D` 时，如果只有一个实参，按 [[over.match.funcs#9]] 被排除。因此不能用一个 `B` 对象"复制构造"出一个 `D`：

```cpp title="no-copy-from-base.cpp" error
struct B {
    B(int) {}
    B(const B&) = default;
};
struct D : B { using B::B; };

void f() {
    B bb(3);
    D d(bb);    // error: B(const B&) 不是候选；D 的隐式复制/移动构造函数需要 D
}
```

这条规则的动机：若允许继承，`D d(bb);` 会"复制"出一个只有 `B` 部分来自 `bb`、其余部分默认初始化的 `D`——这是**切片**（slicing）的逆操作，几乎总是错误。`D` 自己的复制/移动构造函数仍由 [[class.copy.ctor]] 正常隐式声明，`D d2(d);` 用的是它们。

### 特性原样继承：explicit、constexpr、删除、访问

因为调用的就是基类构造函数本身，它的 `explicit`、`constexpr`、`noexcept`、`= delete`、模板性、约束都**原样**保留：

```cpp title="properties.cpp" error
struct B {
    B(int) {}
    explicit B(double) {}
    constexpr B(long) {}
protected:
    B(char) {}
};
struct D : B { using B::B; };

constexpr D cd(1L);   // OK：B(long) 是 constexpr
D d1(2.0);            // OK：直接初始化可以用 explicit 构造函数
D d2 = 2.0;           // error: 复制初始化不考虑 explicit B(double)，剩下 B(int) 与 B(char) 二义
D d3('c');            // error: B(char) 是 protected；在 D 之外用它构造 B 不可访问
```

`d3` 说明 [[namespace.udecl#16]]：即使把 `using B::B;` 放在 `D` 的 `public:` 下，`protected` 的基类构造函数仍然只在"用它构造 `B` 对象时可访问"的地方可访问。

## 初始化如何进行（¶1）

¶1 当类型 `B` 的构造函数被用来初始化**不同类型** `D` 的对象（即它是被继承的），初始化**如同**用一个**预置的默认构造函数**来初始化 `D` 对象，以及从 `D` 到 `B` 路径上每一个"继承来源"的基类子对象，**除了** `B` 子对象由那个继承的构造函数初始化（前提是按 [[class.base.init]]，`B` 子对象**应当**作为 `D` 对象的一部分被初始化）。

换句话说，`using B::B;` 被选中时，`D` 的构造等价于：

```text
D(args...) : B(args...) {}   // 其余基类与成员：如同预置的默认构造函数——
                              // 有默认成员初始化器就用，否则默认初始化
```

但"等价"只是直觉——下面三点是这个"如同"与手写转发构造函数的真正区别。

### 差别一：整个初始化算一次函数调用，形参只初始化一次

¶1 第三句：**完整的初始化被视为一次函数调用**；特别地，除非被省略，继承构造函数的**形参的初始化**先于 `D` 对象任何部分的初始化。

这意味着实参直接初始化**基类构造函数的形参**，中间没有"派生类构造函数的形参"这一层，也就没有额外的复制/移动：

```cpp run title="single-call.cpp" ok
#include <cstdio>

struct NM {
    NM(int) { std::puts("NM(int)"); }
    NM(const NM&) = delete;           // 不可复制也不可移动
};
struct B { B(NM) { std::puts("B(NM)"); } };
struct D : B { using B::B; };

int main() {
    D d(1);   // NM(int) / B(NM)：1 直接初始化 B::B 的形参
}
```

用 `-std=c++14` 编译这段代码，Clang 会报告"复制形参需要调用被删除的构造函数"——C++11/14 的旧模型合成了 `D(NM n) : B(std::forward<NM>(n))` 这样的转发构造函数，必须移动或复制形参。手写的转发构造函数同样有这个问题。

### 差别二：虚基类不需要初始化时，整个调用连同实参一起省略

¶1 第二句：如果 `B` 子对象**不应**作为 `D` 对象的一部分被初始化（典型情形：`B` 是虚基类，而 `D` 不是最派生类），则继承构造函数的调用——**包括实参的求值**——被**省略**。

标准例 2（加上输出观察）：

```cpp run title="omitted.cpp" ok
#include <cstdio>

struct V { V() { std::puts("V()"); } V(int) { std::puts("V(int)"); } };
struct Q { Q() {} };
struct A : virtual V, Q {
    using V::V;
    A() = delete;
};
int bar() { std::puts("bar()"); return 42; }
struct B : A {
    B() : A(bar()) {}   // OK：A(bar()) 选中的是 A 继承来的 V(int)
};
struct C : B {};

int main() {
    C c;   // 按标准：只输出 V()。V 是虚基类，由最派生类 C 默认初始化；
           // A 不是最派生类，V 子对象不作为 A 的一部分初始化，于是 V(int) 的调用
           // 连同实参 bar() 的求值一起被省略（标准例的注释："bar is not invoked"）
}
```

注意 `A() = delete;` 并不妨碍 `B() : A(bar())`：被选中的是继承来的 `V(int)`，`A` 的其余部分（`Q` 子对象）"如同预置的默认构造函数"初始化，而不是调用 `A` 被删除的默认构造函数。

!!! warning "Clang 与标准的出入"
    本机 Clang 23 运行上例先输出 `V()`、再输出 `bar()`：它正确地没有调用 `V(int)`，却仍然**求值了实参** `bar()`，与 ¶1"including the evaluation of any arguments"不符。

    另外请留意：标准例只对 `C c;` 做了注释。若把 `main` 改为 `B b;`，按 ¶1 的字面读法结果相同——`B` 虽是最派生类，但继承构造函数初始化的是 `A` 对象，而 `A` 子对象永远不是最派生对象，`V` 子对象从不"作为 `A` 对象的一部分"初始化；`V` 由 `B` 自己（没有为 `V` 写 *mem-initializer*）默认初始化。

### 差别三：路径上的中间类"如同用预置默认构造函数"

标准例 1 中的 `W/X/Y/Z` 一组：

```cpp run title="chain.cpp" ok
struct W { W(int) {} };
struct X : virtual W { using W::W; X() = delete; };
struct Y : X { using X::X; };
struct Z : Y, virtual W { using Y::Y; };

int main() {
    Z z(0);   // OK
}
```

`Z z(0)` 选中的构造函数是 `W::W(int)`——它经由 `Y`、`X` 被一路继承到 `Z`。按 ¶1，初始化"如同"用预置默认构造函数初始化 `Z` 以及**继承来源路径上**的 `Y`、`X`，而 `W` 子对象（`Z` 是最派生类，所以虚基类 `W` 由 `Z` 初始化）由 `W(0)` 初始化。`X() = delete` 无关紧要，因为 `X` 子对象的初始化"如同"预置默认构造——而 `X` 唯一没有默认初始化手段的子对象 `W` 已经由继承构造函数负责了。

### 其余成员照常初始化

标准例 1 的前半：

```cpp title="d1-d2.cpp" error
struct B1 { B1(int, ...) {} };
struct B2 { B2(double) {} };
int get();

struct D1 : B1 {
    using B1::B1;      // 继承 B1(int, ...)
    int x;
    int y = get();
};

void test() {
    D1 d(2, 3, 4);     // OK：B1(2, 3, 4)；然后 d.x 默认初始化（不初始化）；然后 d.y = get()
    D1 e;              // error: D1 没有默认构造函数（B1 没有，隐式默认构造被删除）
}

struct D2 : B2 {
    using B2::B2;
    B1 b;              // B1 没有默认构造函数
};

D2 f(1.0);             // error: 成员 b 要"如同预置默认构造"那样初始化，但 B1 没有默认构造函数
```

`D2 f(1.0)` 是常见的意外：继承构造函数只管基类那一部分，派生类新增的成员必须能被默认初始化（或有默认成员初始化器）。

### 一个实用的包装器

标准例 1 末尾的 `Log` 模板展示了继承构造函数的典型用法——零成本地"包装"任意类：

```cpp run title="log-wrapper.cpp" ok
#include <iostream>
#include <string>

template<class T> struct Log : T {
    using T::T;   // 继承 T 的全部构造函数；依赖名 T::T 由 [namespace.udecl]/1 视为指名构造函数
    ~Log() { std::clog << "Destroying wrapper\n"; }
};

int main() {
    Log<std::string> s(3, 'x');   // 调用 std::string(size_type, char)
    std::cout << s << '\n';        // xxx
}                                  // Destroying wrapper
```

## 从多个同类型基类子对象继承：非良构（¶2）

¶2 如果被选中的构造函数是从**多个** `B` 类型的基类子对象继承来的，程序非良构。关键词是"基类**子对象**"：非虚继承的菱形里有两个 `B` 子对象，虚继承的菱形里只有一个。

```cpp title="multiple-subobjects.cpp" error
struct A { A(int) {} };
struct B : A { using A::A; };

struct C1 : B { using B::B; };
struct C2 : B { using B::B; };
struct D1 : C1, C2 {
    using C1::C1;
    using C2::C2;
};
D1 d1(0);   // error: 二义——两个 B 子对象（进而两个 A 子对象），该用哪条路径？

struct V1 : virtual B { using B::B; };
struct V2 : virtual B { using B::B; };
struct D2 : V1, V2 {
    using V1::V1;
    using V2::V2;
};
D2 d2(0);   // OK：只有一个（虚）B 子对象；它由继承的 A(int) 构造（经 B 的初始化），
            //     V1、V2 如同用预置默认构造函数初始化

struct M { M() {} M(int) {} };
struct N : M { using M::M; };
struct O : M {};
struct P : N, O { using N::N; using O::O; };
P p(0);     // OK：O::O 没有继承 M 的构造函数（O 没写 using），只有经 N 的那一条；
            //     N 的 M 子对象用 M(0)，O 的 M 子对象用 M()
```

`P` 一例说明了"继承来源"是逐条 *using-declaration* 追踪的：`using O::O;` 只带来 `O` 自己的构造函数（隐式的那些），并没有 `M(int)`。

## 初始化何时完成（¶3）

¶3 对象由继承构造函数初始化时，在**所有子对象的初始化完成**时，对象的初始化完成。

这是 [[class.base.init#11]]（"非委托构造函数返回时初始化完成"）的对应规则：继承构造函数的情形中，被调用的是 `B` 的构造函数，它返回时 `D` 的成员还没有初始化，因此不能以"构造函数返回"为准。完成时刻决定了对象生命周期何时开始（[[basic.life]]），以及异常时是否要调用 `D` 的析构函数（[[except.ctor#3]] 第 3.3 项：按 [[class.inhctor.init]] 初始化的子对象是"已知被初始化"的）。

## 其他相关规则

- **聚合**：有继承构造函数的类**不是**聚合（[[dcl.init.aggr]] 要求"没有用户声明的或继承的构造函数"）。
- **CTAD**：C++23 起，类模板实参推导也会考虑从基类继承的构造函数（[[over.match.class.deduct]]，并有 [[over.match.best#2.10]] 的决胜规则）。截至写作时，本机 Clang 对这一特性的支持并不完整。
- **成员函数中的 `using`** 与构造函数不同：普通成员的 *using-declarator* 要求所指名的声明可访问（[[namespace.udecl#14]]）；构造函数则不做此检查，而是在使用时按基类的访问性检查。

## 实现视角

!!! impl "编译器怎样实现继承构造函数"
    C++17 模型下，Clang 为每个**实际被使用**的继承构造函数在派生类中生成一个构造函数实体：它接收与基类构造函数相同的形参，按 ¶1 依次完成初始化（虚基类、调用基类构造函数、按预置默认构造的方式初始化其余成员）。Itanium ABI 为此定义了专门的 mangling：构造函数名写作 `CI1`/`CI2`（完整对象 / 基类子对象版本）后接基类类型。例如对 `struct D : B { using B::B; };` 中继承的 `B(std::string, int)`，Clang 生成的符号形如 `_ZN1DCI11BE...` 与 `_ZN1DCI21BE...`。

    "形参只初始化一次"在 ABI 层面的含义是：按值传递的非平凡类类型实参，在 Itanium ABI 中本来就由调用方创建临时对象、以地址传递，转发给基类构造函数时可以把同一地址继续传下去，而不必复制一次。编译器也可以在调用点直接内联展开这一过程。

## 历史与演进

!!! history "历史与演进"
    - **C++11**：[[N2540]] 引入继承构造函数。模型是**合成**：对基类的每个构造函数（复制/移动、默认构造除外），按"去掉尾部默认实参"的每种形参列表，在派生类中隐式声明一个同形参的构造函数，转发给基类。缺点包括：按值形参多一次复制/移动；默认实参不保留；不可移动的形参类型无法使用；构造函数模板的处理复杂；与 SFINAE 交互有一系列缺陷报告。
    - **C++17**：[[P0136R1]] 改为现行模型：基类构造函数**直接**作为派生类的构造候选；被选中后按 [class.inhctor.init] 初始化。默认实参、`explicit`、模板性、访问性自然随之保留；"复制/移动构造函数不继承"改为 [[over.match.funcs#9]] 的候选排除规则。本机 Clang 在 `-std=c++14` 模式下仍按旧模型复制按值形参（见上文 `single-call.cpp` 的说明）。
    - **C++23**：类模板实参推导可以使用继承的构造函数。

## 陷阱

!!! pitfall "以为派生类新增的成员会\"自动\"被继承构造函数初始化"
    继承构造函数只负责基类子对象。派生类新增的成员按预置默认构造函数的方式初始化：有默认成员初始化器就用它，否则默认初始化——内置类型成员就是不确定/错误值。给新增成员写默认成员初始化器。

!!! pitfall "以为 using B::B 能带来 B 的复制构造函数"
    `D d(b);`（`b` 是 `B`）不会编译。需要的话显式写 `D(const B& b) : B(b) {}`。

!!! pitfall "以为 public 的 using-declaration 能把 protected 构造函数变成 public"
    不能。继承的构造函数的访问性只看它在基类中的访问性（[[namespace.udecl#16]]）。普通成员函数的 using-declaration 才能改变访问性。

## 思考题

!!! question "思考题 1"
    下面的程序输出什么？如果删掉 `S` 中的 `S(int)`，又会怎样？

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

输出 `B(long)` 和 `S(int)`。`S(int)` 与 `B(int)` 的形参列表相同，按 [[namespace.udecl#11]]，`B(int)` 根本不被继承（被隐藏），候选只有 `S(int)` 与继承的 `B(long)`，前者是精确匹配。

删掉 `S(int)` 后，候选是继承的 `B(int)` 与 `B(long)`，选 `B(int)`，输出 `B(int)`。
</details>

!!! question "思考题 2"
    `struct B { B(int); }; struct D : B { using B::B; std::string s; };` 中，`D d(1);` 的初始化里，`B::B(int)` 的形参初始化、`B` 子对象初始化、`s` 的初始化三者的先后关系是什么？如果 `std::string` 的默认构造函数抛出异常，会调用哪些析构函数？

<details markdown="1">
<summary>答案</summary>

顺序为：形参初始化 → `B` 子对象（调用 `B::B(int)`）→ `s`（默认初始化）。¶1 规定形参的初始化先于 `D` 任何部分的初始化；其余部分按 [[class.base.init#15]] 的顺序。若 `s` 的构造抛出，`B` 子对象已完成初始化，是"已知被初始化"的子对象（[[except.ctor#3]] 第 3.3 项），调用 `B::~B()`；`D` 的初始化没有完成，不调用 `D::~D()`。
</details>

## 小结

| 问题 | C++17 起的答案 |
|---|---|
| `using B::B;` 做了什么 | `B` 的构造函数在 `D` 的构造函数查找与重载决议中被当作 `D` 的构造函数 |
| 被选中后 | `B` 子对象由它初始化，其余如同预置默认构造函数；整体是一次函数调用 |
| 默认实参、`explicit`、`constexpr`、访问性 | 原样来自基类构造函数 |
| 派生类同签名构造函数 | 隐藏对应的继承构造函数 |
| 默认构造函数 | `D` 的隐式默认构造函数照常声明，同形参时派生类的胜出 |
| 复制/移动构造函数 | 单实参且引用相关时从候选中排除 |
| 虚基类不由 `D` 初始化 | 整个调用（含实参求值）省略 |
| 从多个 `B` 子对象继承 | 非良构 |
| 初始化完成 | 所有子对象初始化完成时 |
