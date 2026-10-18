---
title: 构造与析构
summary: 正在构造或析构的对象能做什么：构造开始前/析构结束后引用成员是 UB；不经 this 读取正在初始化的对象得到未指定值；转换到基类、形成成员指针的时机要求；构造/析构期间虚调用、typeid、dynamic_cast 都按"当前构造函数/析构函数的类"处理
status: done
related: class.base.init, basic.life, class.virtual, class.abstract, expr.typeid, expr.dynamic.cast, class.dtor, except.ctor, dcl.contract.func
tags: 构造函数, 析构函数, 虚函数, 多态, UB
updated: 2026-10-17
---

[[basic.life]] 把对象的一生划成三段：生命周期之前、生命周期之内、生命周期之后。但对类类型来说，"之前"和"之后"并不是铁板一块——**构造函数正在执行**、**析构函数正在执行**这两个时期，对象处在一种"半成品"状态：它的一部分子对象已经可用，另一部分还没有（或已经不再）可用。[[basic.life#7]] 与 [[basic.life#8]] 都把这两个时期交给本节处理："for an object under construction or destruction, see [class.cdtor]"。

本节回答四个问题：

1. 构造**开始之前**、析构**结束之后**，能不能碰对象的成员和基类？（¶1）
2. 构造期间，如果不经由构造函数的 `this` 去读对象，读到什么？（¶2）
3. 构造/析构期间，把对象指针转换为基类指针、取成员地址，需要什么前提？（¶3）
4. 构造/析构期间的**多态**行为：虚函数调用、`typeid`、`dynamic_cast` 的结果是什么？（¶4–¶6）

最后一个问题是本节最重要的内容，可以用一句话概括：**正在构造或析构的对象，在多态意义上"就是"当前那个构造函数或析构函数所属的类的对象**。

## 构造之前、析构之后（¶1）

¶1 两条对称的 UB 规则：

- 对于有**非平凡构造函数**的对象，在构造函数**开始执行之前**引用它的任何非静态成员或基类，是 {{ub}}；
- 对于有**非平凡析构函数**的对象，在析构函数**执行完毕之后**引用它的任何非静态成员或基类，是 {{ub}}。

"引用"（refer to）的范围很广：不只是读写值，**取地址、向基类转换**也算。标准例 1 用一个"先声明后定义"的全局对象演示（这是动态初始化顺序问题的典型场景，见 [[basic.start.dynamic]]）：

```cpp run title="before-ctor.cpp" ub
struct X { int i; };
struct Y : X { Y() {} };                 // 非平凡构造函数
struct A { int a; };
struct B : public A { int j; Y y; };     // 因为成员 y，B 的默认构造函数非平凡

extern B bobj;
B* pb = &bobj;                           // OK：只取完整对象的地址
int* p1 = &bobj.a;                       // UB：引用基类成员
int* p2 = &bobj.y.i;                     // UB：引用成员的成员

A* pa = &bobj;                           // UB：向基类转换
B bobj;                                  // bobj 的定义（动态初始化在上面几行之后）

extern X xobj;
int* p3 = &xobj.i;                       // OK：X 的所有构造函数都是平凡的
X xobj;

int main() {}
```

为什么只限"非平凡"？平凡构造函数什么都不做，对象一旦有了存储就"等价于构造好了"（它的生命周期在存储获得、空初始化完成时就开始，[[basic.life#2]]）。非平凡构造函数则可能还没有建立对象的内部结构（例如 vptr、虚基类偏移），这时连"成员在哪"都可能无从计算。

在 `pa = &bobj` 这一行上这一点最为明显：`B` 到 `A` 的转换对非虚基类只是加一个常量偏移，实践中"碰巧能用"；但如果 `A` 是虚基类，偏移量要从 `bobj` 的 vptr 里读，而 vptr 此时还没被构造函数设置——这就是为什么标准把所有这类操作都定为 UB，而不是区别对待。

标准例 1 的第二部分在构造函数里演示了同样的问题：

```cpp run title="before-member-ctor.cpp" ub
struct W { int j; };
struct X : public virtual W {};
struct Y {
    int* p;
    X x;
    Y() : p(&x.j) {}   // UB：x 尚未构造（p 先于 x 初始化），&x.j 需要经虚基类 W 定位
};

int main() { Y y; (void)y; }
```

## 不经 `this` 读取正在初始化的对象（¶2）

¶2 在对象初始化期间，如果通过一个**不是**（直接或间接）从构造函数的 `this` 指针得到的 glvalue 去访问它的任何子对象的值、或其对象表示的任何元素，得到的值是 {{unspec}}。

这条规则的动机是**优化**。看标准例 2：

```cpp run title="unspecified-value.cpp" unspecified
#include <cstdio>

struct C;
void no_opt(C*);

struct C {
    int c;
    C() : c(0) { no_opt(this); }
};

const C cobj;

void no_opt(C* cptr) {
    int i = cobj.c * 100;   // cobj.c 的值未指定
    cptr->c = 1;            // 经由 this 得来的指针修改：合法
    std::printf("%d %d\n", i, cobj.c * 100);   // 第二个值同样未指定
}

int main() {}
```

`cobj` 是一个 `const` 对象。编译器很想假设"`cobj.c` 一旦初始化就不会变"，于是可以把 `cobj.c` 的读取常量折叠，或者缓存在寄存器里。但构造期间 `const` 对象**可以**被修改（`const` 语义在最派生对象的构造函数结束时才生效，[[class.ctor.general#4]]），如果标准要求通过名字 `cobj` 读到的值必须"最新"，这些优化在构造期间就都不成立了。¶2 的折中是：经 `this` 派生出来的访问是可靠的；绕过 `this` 的访问只能得到未指定值——编译器愿意给什么就是什么。

注意这里是**未指定**（unspecified），不是 UB：程序不会因此"什么都可能发生"，只是读到的值不确定是哪一个。

标准例 2 的另一半更常见：

```cpp run title="self-ref-global.cpp" unspecified
#include <cstdio>

extern struct D d;
struct D {
    D(int a) : a(a), b(d.a) {}   // 通过全局名 d 而不是 this 读取 d.a
    int a, b;
};
D d = D(1);                      // d.b 的值未指定

int main() { std::printf("%d\n", d.b); }
```

C++17 起 `D d = D(1);` 中 `D(1)` 直接初始化 `d`（保证复制消除，[[class.copy.elision]]），所以构造函数中的 `this` 就是 `&d`，`d.a` 指的确实是正在初始化的同一个对象——但因为不是"经由 `this`"，值仍是未指定的。修正方法很简单：写 `b(this->a)` 或直接 `b(a)`（在 *mem-initializer* 中这里的 `a` 是形参；若想读成员，写 `this->a`）。

## 转换到基类与形成成员指针（¶3）

¶3 两个前提条件：

1. **向基类转换**：要把指向类 `X` 对象的指针（或 glvalue）显式或隐式转换为指向其直接或间接基类 `B` 的指针（或引用），`X` 的构造、以及 `X` 的所有直接或间接派生自 `B` 的基类的构造，都必须**已经开始**，且这些类的析构都**尚未完成**；否则 {{ub}}。
2. **形成成员指针 / 访问成员值**：要形成指向对象 `obj` 的直接非静态成员的指针（或访问该成员的值），`obj` 的构造必须已经开始、析构尚未完成；否则 {{ub}}。

第一条的关键是"**路径**"：从 `X` 到 `B` 可能有多条继承路径，经由的每一个中间类都必须"在构造中或构造完毕"。标准例 3：

```cpp run title="conversion-path.cpp" ub
struct A {};
struct B : virtual A {};
struct C : B {};
struct D : virtual A { D(A*) {} };
struct X { X(A*) {} };

struct E : C, D, X {
    E() : D(this),   // UB：E* → A* 可能走 E* → D* → A*，但此时 D 尚未开始构造
                     // "D((C*)this)" 则是良定义的：E* → C* 合法（E() 已经开始），
                     //  C* → A* 合法（C 已构造完毕）
          X(this) {} // 良定义：构造 X 时，C/B/D/A 这一子格已全部构造完毕
};

int main() { E e; }
```

`D(this)` 的问题在于：`E*` 到 `A*` 的转换，编译器可以选择经过 `D` 的路径来找虚基类 `A`——而这需要读取 `D` 子对象里的信息（虚基类偏移），但 `D` 正是马上要构造、尚未开始构造的那个子对象。`(C*)this` 先显式走到已构造完毕的 `C`，再从 `C` 找 `A`，就避开了未构造的 `D`。

第二条比第一条宽松：只要 `obj` 的构造**开始**了即可，不要求被指向的成员已经初始化。所以在 *mem-initializer* 里写 `r(a)`（把引用成员绑定到尚未初始化的成员 `a`，[[class.base.init#17]]）、或 `p(&member)` 都是良定义的——只要没有像 ¶1 那个例子那样经过尚未构造的**成员的**虚基类。

## 构造/析构期间的虚函数调用（¶4）

¶4 成员函数（包括虚函数）可以在构造或析构期间调用（[[class.base.init#18]] 划出了例外的 UB 时段）。当虚函数被**直接或间接**地从构造函数或析构函数中调用——包括在非静态数据成员的构造或析构期间，以及构造函数的后置条件断言、析构函数的前置条件断言求值期间（{{c++26}}，[[dcl.contract.func]]）——且调用作用的对象就是正在构造或析构的那个对象（称之为 *x*），那么被调用的是**构造函数或析构函数所属的类中的最终覆盖函数**，而不是更派生类中覆盖它的函数。

```cpp run title="virtual-in-ctor.cpp" ok
#include <cstdio>

struct Base {
    Base()  { call(); }
    virtual ~Base() { call(); }
    virtual const char* name() const { return "Base"; }
    void call() const { std::printf("%s\n", name()); }   // 间接调用也受 ¶4 约束
};

struct Derived : Base {
    Derived()  { call(); }
    ~Derived() override { call(); }
    const char* name() const override { return "Derived"; }
};

int main() {
    Derived d;   // Base（Base 构造期间）/ Derived（Derived 构造期间）
}                // Derived（Derived 析构期间）/ Base（Base 析构期间）
```

### 为什么这样设计？

构造顺序是基类先于派生类（[[class.base.init#15]]）。在 `Base` 的构造函数执行时，`Derived` 的成员**全都还没有初始化**。如果此时调用 `Derived::name()`，它很可能读到未初始化的成员——一个必然出错的调用。析构反过来：`Base` 的析构函数执行时，`Derived` 的成员**已经全部析构**了。

所以 C++ 的选择是：在构造/析构期间，对象的"动态类型"逐步变化——构造 `Base` 部分时它表现为 `Base`，构造 `Derived` 部分时表现为 `Derived`；析构时反向退化。这与 Java、C# 的选择正好相反（它们在基类构造函数中会分派到派生类的覆盖函数，派生类字段此时是默认零值）。

### 纯虚函数

如果按 ¶4 的规则，分派到的最终覆盖函数是一个**纯虚函数**，结果是 UB（[[class.abstract#6]]）。直接调用时编译器能发现：

```cpp run title="pure-virtual.cpp" ub
struct B {
    B() { init(); }          // 经由非虚的 init() 间接调用：编译器通常不会警告
    void init() { f(); }
    virtual void f() = 0;
    virtual ~B() = default;
};
struct D : B { void f() override {} };

int main() { D d; }   // UB：B 构造期间 f() 的最终覆盖函数是纯虚的 B::f
```

在 Itanium ABI 下，抽象类虚表中纯虚函数的槽位指向 `__cxa_pure_virtual`，它打印一条消息后终止程序；本机（libc++abi）的运行结果是打印 "Pure virtual function called!" 后 abort。若把 `B()` 改为直接调用 `f()`，Clang 会给出 `-Wcall-to-pure-virtual-from-ctor-dtor` 警告。

### 经过其他对象表达式的调用：何时 UB

¶4 最后一句处理更微妙的情形：虚函数调用使用了**显式的类成员访问**（`p->f()` 或 `obj.f()`），而对象表达式指向的是 *x* 的**完整对象**或该完整对象的某个基类子对象，但**不是** *x* 本身或 *x* 的某个基类子对象——行为未定义。

标准例 4（加上输出）：

```cpp run title="virtual-other-path.cpp" ub
#include <cstdio>

struct V {
    virtual void f() { std::puts("V::f"); }
    virtual void g() { std::puts("V::g"); }
    virtual ~V() = default;
};
struct A : virtual V { void f() override { std::puts("A::f"); } };
struct B : virtual V {
    void g() override { std::puts("B::g"); }
    B(V*, A*);
};
struct D : A, B {
    void f() override { std::puts("D::f"); }
    void g() override { std::puts("D::g"); }
    D() : B((A*)this, this) {}
};

B::B(V* v, A* a) {
    f();       // V::f，不是 A::f（A 不是 B 的基类，B 的最终覆盖函数是 V::f）
    g();       // B::g，不是 D::g
    v->g();    // v 指向 B 的基类 V：良定义，B::g
    a->f();    // UB：a 的类型 A 不是 B 的基类——A 子对象属于完整对象 D，但不属于 x（B 子对象）
}

int main() { D d; }
```

`a->f()` 为什么是 UB？在构造 `B` 子对象期间，`A` 子对象**已经**构造完毕（它在 `B` 之前），按理它应该表现为一个完整的 `A`……但它所在的完整对象 `D` 的虚表正处于"构造 `B` 阶段"的中间状态，`A` 子对象的 vptr 指向什么，取决于实现在何时、以何种顺序设置各个子对象的 vptr。标准不愿意约束这些实现细节，于是规定为 UB。本机 Clang 运行上例，`a->f()` 打印的是 `V::f`——既不是 `A` 子对象"本该"表现出的 `A::f`，也不是最终的 `D::f`。一种合理的解释是 Itanium ABI 的布局细节：`V` 只含一个 vptr（"近乎空"的类），可以作为 `A` 的主基类与 `A` 共用 vptr 位置；`B` 的构造函数为虚基类 `V` 安装构造虚表时，也就改写了 `A` 子对象看到的 vptr。这类细节正是标准拒绝给出定义的原因。

## 构造/析构期间的 `typeid`（¶5）

¶5 `typeid` 可以在构造或析构期间使用。在构造函数（包括非静态数据成员的 *mem-initializer* 或默认成员初始化器）、析构函数，或它们直接、间接调用的函数中，若 `typeid` 的操作数指向正在构造或析构的对象，结果是表示**构造函数或析构函数所属类**的 `std::type_info`。若操作数指向正在构造/析构的对象，而其**静态类型**既不是该构造/析构函数所属的类，也不是它的基类，则 {{ub}}。

## 构造/析构期间的 `dynamic_cast`（¶6）

¶6 `dynamic_cast` 同理：在同样的语境中，若操作数指向正在构造或析构的对象，该对象被视为一个**最派生对象**，其类型是构造/析构函数所属的类。若操作数的静态类型不是指向该类或其基类的指针（或该类、其基类的对象），{{ub}}。

标准例 5 合并了 `typeid` 与 `dynamic_cast` 的情形：

```cpp run title="typeid-dyncast.cpp" ok
#include <cstdio>
#include <typeinfo>

struct V { virtual void f() {} virtual ~V() = default; };
struct A : virtual V {};
struct B : virtual V { B(V*, A*); };
struct D : A, B { D() : B((A*)this, this) {} };

B::B(V* v, A* /*a*/) {
    std::printf("%d\n", typeid(*this) == typeid(B));      // 1：B 的 type_info
    std::printf("%d\n", typeid(*v) == typeid(B));         // 1：*v 的类型 V 是 B 的基类，得到 B
    std::printf("%d\n", dynamic_cast<B*>(v) == this);     // 1：V 是 B 的基类，结果是 B*
    std::printf("%p\n", static_cast<void*>(dynamic_cast<D*>(v)));  // 空指针：此时对象"就是"B
    // typeid(*a);            // UB：A 不是 B 的基类
    // dynamic_cast<B*>(a);   // UB：同上
}

int main() { D d; }
```

注意 `dynamic_cast<D*>(v)` 返回空指针：在 `B` 构造期间，对象被视为一个最派生类型为 `B` 的对象，它"没有" `D` 部分。

## 三条规则背后的统一模型

¶4–¶6 合起来描述的就是：**构造/析构期间，对象的动态类型是当前构造函数/析构函数所属的类**。[[intro.object]] 中"最派生对象"的概念、[[basic.life]] 中"生命周期"的概念，到这里都被"构造期间的类"取代。

| 时刻 | 虚调用分派到 | `typeid(*this)` | `dynamic_cast<Derived*>(this)` |
|---|---|---|---|
| `Base` 构造函数中 | `Base` 的最终覆盖函数 | `Base` | 空指针 |
| `Derived` 构造函数中 | `Derived` 的最终覆盖函数 | `Derived` | 非空 |
| 生命周期内 | 真正最派生类的最终覆盖函数 | 最派生类 | 非空 |
| `Derived` 析构函数中 | `Derived` 的最终覆盖函数 | `Derived` | 非空 |
| `Base` 析构函数中 | `Base` 的最终覆盖函数 | `Base` | 空指针 |

## 实现视角

!!! impl "vptr 在构造过程中被改写"
    在 Itanium ABI 与 MSVC ABI 中，这一模型的实现方式是：**每个构造函数在初始化完基类之后、初始化成员之前，把对象的 vptr 设为本类的虚表**；析构函数则在执行函数体之前把 vptr 设回本类的虚表（基类析构函数会在之后再把它改为基类的虚表）。因此：

    - 在 `Base()` 中，vptr 指向 `Base` 的虚表，虚调用自然落到 `Base` 的版本；
    - `typeid` 读的是虚表中的 RTTI 指针，`dynamic_cast` 也依赖它，所以二者也"看到" `Base`。

    有虚基类时，中间类的 vptr 在构造期间指向的是特殊的**构造虚表**（construction vtable），由 VTT 提供（见 [[class.base.init]] 的实现视角）。这正是 ¶4 中"经其他路径调用"（`a->f()`）是 UB 的实现层面原因：其他子对象的 vptr 在此时可能指向构造虚表，也可能指向最终虚表。

    这也解释了 ¶1：在构造函数开始前，vptr 根本没有被写入，任何需要读 vptr 的操作（虚调用、向虚基类转换）都会读到垃圾。

!!! impl "优化器如何利用 ¶4"
    由于构造函数中对 `this` 的虚调用一定分派到本类的最终覆盖函数，编译器可以把 `Base()` 中的 `name()` **直接去虚化**为 `Base::name()` 的静态调用。本机 Clang 在 `-O1` 下对 `Base::Base() { sink(name()); }` 生成的就是对 `Base::name` 的直接调用（`-O0` 下仍经虚表间接调用）。

## 历史与演进

!!! history "历史与演进"
    - **C++98**：本节的主体规则（¶1、¶3–¶6）在 C++98 中已经存在，措辞基本相同。
    - **C++26**：¶4 增加了契约断言（构造函数的后置条件、析构函数的前置条件）也适用"按当前类分派"的规定；[[class.base.init#18]] 则把构造函数前置条件、析构函数后置条件中的成员函数调用定为 UB（[[dcl.contract.func]]）。

## 陷阱

!!! pitfall "在基类构造函数里调用虚函数期望“模板方法”行为"
    `Base() { init(); }` 想让派生类定制 `init()`——不会生效，派生类的版本不会被调用。替代方案：两段式初始化（构造后调用 `init()`）、工厂函数、或者把定制点作为构造函数参数（策略对象 / CRTP）。

!!! pitfall "在析构函数里通过虚函数做“派生类清理”"
    同理，`~Base() { cleanup(); }` 中的 `cleanup()` 只会调用 `Base::cleanup`。派生类的清理应放在派生类自己的析构函数里。

!!! pitfall "在构造函数里把 this 交给其他线程或全局注册表"
    其他代码通过这个指针访问对象时，对象可能还在构造中：虚调用分派到基类版本、成员尚未初始化、不经 `this` 读到未指定值（¶2），跨线程无同步时还会构成数据竞争。尽量在构造完成之后再发布 `this`。

## 思考题

!!! question "思考题 1"
    下面的程序输出什么？

    ```cpp
    #include <cstdio>
    struct B;
    struct M { M(B* b); };
    struct B {
        M m;
        B() : m(this) {}
        virtual const char* who() const { return "B"; }
        virtual ~B() = default;
    };
    struct D : B { const char* who() const override { return "D"; } };
    M::M(B* b) { std::puts(b->who()); }
    int main() { D d; }
    ```

<details markdown="1">
<summary>答案</summary>

输出 `B`。`M` 的构造函数在 `B` 的构造期间（初始化 `B` 的非静态数据成员 `m` 时）被调用，¶4 明确"包括在非静态数据成员的构造期间"。`b` 指向的正是正在构造的 `B` 对象（*x* 本身），所以分派到 `B` 的最终覆盖函数 `B::who`。

实现层面：`B` 的构造函数在初始化成员 `m` 之前，已经把 vptr 设为 `B` 的虚表。
</details>

!!! question "思考题 2"
    `struct S { int x; S() { g(this); } }; const S s; void g(S* p) { p->x = 1; }`，之后在 `main` 中读 `s.x`，得到什么？这与 ¶2 有关吗？

<details markdown="1">
<summary>答案</summary>

得到 `1`。`p` 是从构造函数的 `this` 得来的，通过它修改 `const` 对象在构造期间是允许的：`const` 与 `volatile` 语义不作用于正在构造的对象，在最派生对象的构造函数结束时才生效（[[class.ctor.general#4]]）。¶2 只约束**构造期间**、**不经 `this`** 的读取；`main` 中读 `s.x` 发生在初始化完成之后，值就是 `1`。
</details>

## 小结

| 规则 | 段落 | 后果 |
|---|---|---|
| 非平凡构造开始前 / 非平凡析构结束后引用成员或基类 | ¶1 | UB |
| 初始化期间不经 `this` 访问对象的值 | ¶2 | 未指定值 |
| 向基类转换：路径上各类的构造已开始、析构未完成 | ¶3 | 否则 UB |
| 形成直接成员的指针 / 访问其值：对象构造已开始、析构未完成 | ¶3 | 否则 UB |
| 构造/析构期间对 *x* 的虚调用 | ¶4 | 分派到当前类的最终覆盖函数 |
| 经过 *x* 之外的完整对象路径的虚调用 | ¶4 | UB |
| `typeid` / `dynamic_cast` 作用于 *x* | ¶5–¶6 | 当前类；静态类型不是当前类或其基类时 UB |
