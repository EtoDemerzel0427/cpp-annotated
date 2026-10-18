---
title: 虚函数
summary: 虚函数与多态类；覆盖的判定（对应声明、cv 与引用限定符）、协变返回类型的全部条件、最终覆盖者及其唯一性、override/final、默认实参按静态类型、限定调用抑制虚调用、deleted 与 consteval 的配对规则；vtable/vptr、thunk 与去虚化
status: draft
papers: P1064R0, P0847R7
related: class.derived, class.abstract, class.access.virt, class.cdtor, expr.call, dcl.fct.default, basic.scope.scope, class.dtor, except.spec, expr.dynamic.cast, expr.typeid
tags: 类, 虚函数, 多态, 覆盖, ABI
updated: 2026-10-17
---

**虚函数**（virtual function）是 C++ 运行期多态的唯一语言机制：通过基类的指针或引用调用虚函数时，实际执行的是对象**动态类型**中的那个版本。本节回答三个问题：

1. **哪些函数是虚函数**，一个派生类中的函数**何时覆盖**（override）基类的虚函数？
2. 对一个对象而言，**最终被调用的是哪个函数**（最终覆盖者，final overrider）？它必须唯一。
3. 覆盖时有哪些**一致性约束**：返回类型（协变）、引用限定符、`final`/`override`、deleted、consteval、约束子句。

真正"调用时发生什么"写在 [[expr.call#2]]：若选中的函数是虚函数、且没有用限定名调用，则调用其在对象动态类型中的最终覆盖者——这种调用称为**虚函数调用**（virtual function call）。构造与析构期间的特殊行为在 [[class.cdtor#4]]。访问检查用静态类型（[[class.access.virt]]）。

## 虚函数与多态类（¶1）

¶1：一个非静态成员函数是**虚函数**，如果它

- **首次声明**时带关键字 `virtual`，或者
- **覆盖**了在基类中声明的某个虚成员函数（见 ¶2）。

脚注 85：在覆盖函数的声明上再写 `virtual` 是合法但冗余的。这意味着"virtual 性"是**继承下来的**：派生类里同签名的函数自动是虚函数，无论写不写 `virtual`。（C++11 后推荐写 `override` 而不是 `virtual`，见 ¶5。）

含有（声明或继承的）虚函数的类称为**多态类**（polymorphic class）。多态类决定了 `dynamic_cast` 能否向下转换（[[expr.dynamic.cast]]）、`typeid` 是否求值其操作数并返回动态类型（[[expr.typeid]]）。

脚注 86：即使所有虚函数都是**立即函数**（`consteval`），该类仍是多态类，哪怕其内部表示不需要任何额外开销（因为 consteval 虚函数只在编译期被调用，运行期 vtable 里不需要它们）。

### 哪些函数不能是虚函数

| 不能是虚函数的 | 依据 |
|---|---|
| 非成员函数、静态成员函数 | ¶11 注 4、[[dcl.fct.spec]]：虚调用需要一个对象来决定调用目标 |
| 构造函数 | [[class.ctor]]：构造时对象的动态类型尚不存在 |
| 成员函数模板 | [[temp.mem#3]]：vtable 大小必须在类定义时确定，而模板的特化数目无界 |
| 带尾随 *requires-clause* 的函数 | ¶6 |
| **显式对象成员函数**（`this` 形参） | [[dcl.fct#7]]：带显式对象形参的成员声明符不能声明为 `static` 或 `virtual` |

```cpp title="cannot-be-virtual.cpp" error
struct S {
    virtual static void a();                 // error: 静态成员不能是虚函数
    template<class T> virtual void b(T);     // error: 成员函数模板不能是虚函数
    virtual void c(this S& self);            // error: 显式对象成员函数不能是虚函数
};
template<class T> struct R {
    virtual void d() requires true;          // error: 虚函数不能有尾随 requires 子句
};
```

## 覆盖与最终覆盖者（¶2）

### 何时覆盖

¶2 第一句给出覆盖的定义：

!!! std
    If a virtual member function F is declared in a class B, and, in a class D derived (directly or indirectly) from B, a declaration of a member function G corresponds to a declaration of F, ignoring trailing requires-clauses, then G overrides F.

    若虚成员函数 F 声明于类 B，且在（直接或间接）派生自 B 的类 D 中，某个成员函数 G 的声明与 F 的声明**对应**（忽略尾随 requires 子句），则 G **覆盖** F。

"对应"（correspond）是 [[basic.scope.scope#4]] 定义的术语，原本用于判断同一作用域中的两个声明是否冲突/重声明。对两个非静态成员函数，"对应"要求：

- **同名**（或者都是析构函数——因此派生类的析构函数覆盖基类的虚析构函数，尽管它们"名字"不同）；
- **非对象形参类型列表相同**（non-object-parameter-type-list，即去掉隐式/显式对象形参后的形参类型列表，顶层 cv 已被忽略）；
- **对象形参对应**（[basic.scope.scope]/3）：这一条把 **cv 限定符**和**引用限定符**纳入比较——`void f() const` 与 `void f()` 不对应，所以不覆盖。

不在比较范围内的：**返回类型**（由 ¶8 另行约束）、**异常说明**（由 [[except.spec#5]] 另行约束）、**访问权**（脚注 87：判断覆盖时不考虑访问控制）、默认实参、`constexpr`。

!!! lawyer "跨类比较对象形参"
    [basic.scope.scope]/3 对隐式对象成员函数比较"对象形参的类型"，而 `B::f` 的对象形参类型是 `B&`、`D::f` 的是 `D&`——逐字看二者并不相同。¶2 显然意在比较的是"除所属类之外"的部分：cv 限定与引用限定。实现都是这样理解的；读这段措辞时不必被字面上的 `B`/`D` 差异困住。

```cpp run title="overriding-basics.cpp" ok
#include <cstdio>

struct B {
    virtual void f(int)          { std::puts("B::f(int)"); }
    virtual void g() const       { std::puts("B::g() const"); }
    virtual ~B() = default;
private:
    virtual void h()             { std::puts("B::h"); }
public:
    void call_h() { h(); }
};

struct D : B {
    void f(int) override         { std::puts("D::f(int)"); }    // 覆盖
    void f(long)                 { std::puts("D::f(long)"); }   // 新函数，不覆盖（形参不同）
    void g()                     { std::puts("D::g()"); }       // 新函数，不覆盖（缺 const）
    ~D() override = default;                                     // 析构函数也会覆盖
    void h() override            { std::puts("D::h"); }         // 覆盖：不考虑访问权
};

int main() {
    D d;
    B& b = d;
    b.f(1);       // D::f(int)
    b.g();        // B::g() const
    b.call_h();   // D::h
}
```

（Clang 对 `D::g` 会给出"隐藏了重载的虚函数"之类的警告——这几乎总是 bug 的信号。）

¶3（注 2）：被覆盖的虚函数**不必可见**。中间类 `D` 声明 `f(int)` 隐藏了 `B::f()`，但 `D2::f()` 仍然覆盖 `B::f()`：覆盖是在**类的层次结构**上定义的，不经过名字查找。

```cpp run title="override-invisible.cpp" ok
#include <cstdio>

struct B  { virtual void f() { std::puts("B::f"); } virtual ~B() = default; };
struct D  : B { void f(int) {} };            // 隐藏 B::f()；D::f(int) 不是虚函数
struct D2 : D { void f() override { std::puts("D2::f"); } };   // 覆盖 B::f()，尽管它在 D2 中不可见

int main() {
    D2 d2;
    B& b = d2;
    b.f();        // D2::f
}
```

### 最终覆盖者

¶2 继续定义：为方便起见，规定**任何虚函数都覆盖它自己**。对类对象 S 的虚成员函数 V，若 S 是某个最派生类的基类子对象，而该最派生类中**没有**另一个覆盖 V 的成员函数，则 V 是 S 的**最终覆盖者**（final overrider）。

更直观的说法：从 S 所在的完整对象的动态类型出发，沿着子对象格向下（向派生方向）看，"最派生的那个覆盖 V 的函数"就是最终覆盖者。虚函数调用就是调用它。

**唯一性规则**：派生类中，若某个基类子对象的虚成员函数有**多于一个**最终覆盖者，程序 ill-formed。

注意这条规则是**以子对象为单位**的：

- 非虚继承形成两个独立的 `A` 子对象时，**每个子对象**各自有一个最终覆盖者，互不冲突（例 2、例 7）；
- 虚继承使两条路径**共享同一个** `A` 子对象时，两条路径上的覆盖者都在争夺这一个子对象的 `f`，就可能出现两个最终覆盖者（例 8）。

```cpp run title="final-overrider-nonvirtual.cpp" ok
#include <cstdio>

struct A  { virtual void f() { std::puts("A::f"); } virtual ~A() = default; };
struct B1 : A { void f() override { std::puts("B1::f"); } };
struct B2 : A { void f() override { std::puts("B2::f"); } };
struct D  : B1, B2 {};          // 两个 A 子对象：B1::A 的最终覆盖者是 B1::f，B2::A 的是 B2::f

int main() {
    D d;
    // A* ap = &d;              // error: 二义（哪个 A？）
    A* ap1 = static_cast<B1*>(&d);
    A* ap2 = static_cast<B2*>(&d);
    ap1->f();                   // B1::f
    ap2->f();                   // B2::f
    // d.f();                   // error: 名字查找二义
}
```

```cpp title="final-overrider-virtual.cpp" error
struct A   { virtual void f(); };
struct VB1 : virtual A { void f(); };
struct VB2 : virtual A { void f(); };

struct Error : VB1, VB2 {};             // error: A::f 在 Error 中有两个最终覆盖者
struct Okay  : VB1, VB2 { void f(); };  // OK: Okay::f 覆盖二者，是唯一的最终覆盖者
```

例 9 展示了一个反直觉的后果——"跨分支"的虚调用：

```cpp run title="cross-delegation.cpp" ok
#include <cstdio>

struct A    { virtual void f() { std::puts("A::f"); } virtual ~A() = default; };
struct VB2  : virtual A { void f() override { std::puts("VB2::f"); } };
struct VB1a : virtual A {};             // 不声明 f
struct Da   : VB1a, VB2 {};

int main() {
    VB1a* p = new Da;
    p->f();     // VB2::f —— 通过 VB1a 的指针，调用了"兄弟"分支 VB2 的函数
    delete p;
}
```

`VB1a` 与 `VB2` 共享同一个虚基类 `A`，`A::f` 在 `Da` 中的最终覆盖者是 `VB2::f`。于是通过 `VB1a*` 调用 `f` 会进入一个 `VB1a` 根本不知道的类。这种"跨分支委托"（有时被称为 dominance / sibling dispatch）是虚继承"共享子对象"语义的直接结果。

例 1 展示 using 声明与覆盖的关系：

```cpp run title="using-and-override.cpp" ok
#include <cstdio>

struct A { virtual void f() { std::puts("A::f"); } virtual ~A() = default; };
struct B : virtual A { void f() override { std::puts("B::f"); } };
struct C : B, virtual A { using A::f; };

int main() {
    C c;
    c.f();        // B::f —— 名字查找找到 A::f（经 using），但这是虚调用，调用最终覆盖者
    c.C::f();     // A::f —— 限定名调用抑制虚机制（¶16），而 C::f 查到的是 using 引入的 A::f
}
```

using 声明**不**参与覆盖：它只是把名字引入作用域，影响**名字查找**；最终覆盖者仍按类层次结构计算。

## `final` 与 `override`（¶4–¶5）

两个 *virt-specifier*（C++11），都是**上下文关键字**，只在成员函数声明符末尾有特殊含义：

- ¶4 **`final`**：若基类 `B` 的虚函数 `f` 标了 `final`，派生类中任何覆盖 `B::f` 的函数都使程序 ill-formed。
- ¶5 **`override`**：标了 `override` 的虚函数如果**没有**覆盖任何基类成员函数，程序 ill-formed。

`override` 是一个**编译期断言**：它把"我以为我在覆盖"变成可检查的事实，抓住签名写错（`long` vs `int`、漏了 `const`、基类函数被改名）这一整类 bug。

```cpp title="final-override.cpp" error
struct B {
    virtual void f() const final;
    virtual void g(int);
};
struct D : B {
    void f() const;               // error: 覆盖了 final 的 B::f
    void g(long) override;        // error: 标了 override 但没有覆盖任何函数
    void g(int) override;         // OK
};
```

细节：

- 一个函数可以同时 `override final`；`final` 可以标在**首次引入**的虚函数上（`virtual void f() final;`），这样它在派生类中不能被覆盖——用处不大，但合法。
- `final` 标在**非虚**函数上是 ill-formed（[[class.mem]]：*virt-specifier-seq* 只能出现在虚成员函数的声明中）。
- *virt-specifier-seq* 只能出现在**首次声明**中，不能出现在类外定义上（[class.mem.general]/19）。
- 类级别的 `final`（`struct D final : B`）在 [[class.pre#6]]，它禁止派生，因此 `D` 的所有虚函数实际上都不会再被覆盖——编译器可借此去虚化。

## 不能有约束（¶6）

¶6：虚函数不能有尾随 *requires-clause*。理由：约束决定一个函数"是否存在"，而 vtable 的槽位必须在类定义时就固定下来。类模板的虚成员函数如果带约束，就会出现"某些特化有这个槽、某些没有"的情况，而覆盖关系也会变得依赖于约束的满足性。注意 ¶2 判断覆盖时"忽略尾随 requires 子句"：派生类中带约束的同签名函数仍然被认定为覆盖者——然后因 ¶6 而 ill-formed（它是虚函数）。

## 引用限定符必须一致（¶7）

¶7：覆盖函数的引用限定符（或没有引用限定符）必须与被覆盖函数**相同**。

什么时候会触发？对象形参"对应"规则（[basic.scope.scope]/3.1）允许"**恰好一个**是无引用限定符的隐式对象成员函数"时，去掉引用后比较——所以 `virtual void g();` 与 `void g() &;` 是**对应**的，于是后者覆盖前者，再因 ¶7 而 ill-formed。而 `void g() &` 与 `void g() &&` 根本不对应（不覆盖，只是隐藏）。

```cpp title="ref-qualifier.cpp" error
struct B {
    virtual void g();
    virtual void k() &;
};
struct D : B {
    void g() &;      // error: 覆盖 B::g 但引用限定符不同
    void k() &&;     // 不对应 B::k() &，因此不覆盖：它是新函数，隐藏 B::k
};
```

（对 `g`，Clang 报告的是"带引用限定符与不带的成员函数不能重载"——同一规则在 [[over.load]] 中的另一面；对 `k` 则只给出隐藏虚函数的警告。）

## 协变返回类型（¶8–¶9）

¶8：覆盖函数的返回类型必须**与被覆盖函数相同**，或与之**协变**（covariant）。若 `D::f` 覆盖 `B::f`，二者返回类型协变当且仅当：

- ¶8.1 都是**指向类的指针**，或都是**指向类的左值引用**，或都是**指向类的右值引用**（脚注 88：多级指针、指向多级指针的引用都不行）；
- ¶8.2 `B::f` 返回类型中的类与 `D::f` 的**相同**，或者是后者的**无二义且可访问**的（直接或间接）基类；
- ¶8.3 两个指针/引用本身的 cv 限定相同，且 `D::f` 返回类型中的类类型的 cv 限定**相同或更少**。

¶9 补充两条：

- 若协变返回类型中的类类型与 `B::f` 的不同，那么 `D::f` 返回类型中的类类型必须在覆盖声明的**声明点**处**完整**，或者就是 `D` 本身（这样 `D* clone()` 在 `D` 内部也能写）。
- 当覆盖函数作为最终覆盖者被调用时，其结果被**转换**为（静态选中的）被覆盖函数的返回类型（[[expr.call]]）。

为什么这么多条件？因为调用者是按 `B::f` 的签名编译的：它期望拿到一个 `B*`。被调用的 `D::f` 返回 `X*`，必须能够在**不知道 `X` 的动态情况**下转换成 `B*`：

- 必须是指针/引用（值类型的"协变"需要切片，而且大小不同，ABI 无法统一）；
- 必须是可访问、无二义的基类（否则转换本身就不合法）；
- 必须完整（编译器要生成调整指针的代码，需要知道基类的偏移）；
- cv 不能增加（`const X*` 不能悄悄变成 `X*`）。

```cpp title="covariance.cpp" error
struct A1 {};
struct A2 : A1 {};
struct A3 : A1 {};
struct Amb : A2, A3 {};          // 两个 A1
class Priv : private A1 {};
struct Inc;

struct B {
    virtual A1*  p1();
    virtual A1*  p2();
    virtual A1*  p3();
    virtual A1&  r1();
    virtual A1*  p4();
    virtual A1** pp();
    virtual A1*  p5();
    virtual A1   v();
    virtual const A1* c();
    virtual B*   self();
};

struct D : B {
    A2*  p1() override;          // OK: A1 是 A2 的可访问无二义基类
    Amb* p2() override;          // error: A1 是 Amb 的二义基类
    Priv* p3() override;         // error: A1 是 Priv 的私有基类（在 D 中不可访问）
    A2&& r1() override;          // error: 左值引用 vs 右值引用
    const A2* p4() override;     // error: 类类型的 cv 比 B::p4 的多
    A2** pp() override;          // error: 多级指针不能协变
    Inc* p5() override;          // error: Inc 不完整
    A2   v() override;           // error: 按值返回不能协变
    A2*  c() override;           // OK: cv 更少是允许的
    D*   self() override;        // OK: D 在此处不完整，但它就是 D 本身
};
```

¶8.2 的"可访问"是在**覆盖函数所在的类**的语境中判断的。标准例 6 中 `class D : private B { friend class Derived; }`：`No_good::vf4` 返回 `D*` 不行（`B` 不可访问），而 `Derived` 是 `D` 的友元，`Derived::vf4` 返回 `D*` 就可以。

### 协变调用的结果转换

```cpp run title="covariant-call.cpp" ok
#include <cassert>

struct X { virtual ~X() = default; int x = 1; };
struct Y { virtual ~Y() = default; int y = 2; };
struct Z : X, Y { int z = 3; };      // Y 子对象不在 Z 的偏移 0

struct B { virtual Y* get() { return nullptr; } virtual ~B() = default; };
struct D : B {
    Z obj;
    Z* get() override { return &obj; }
};

int main() {
    D d;
    B& b = d;
    Y* py = b.get();                 // 调用 D::get，结果 Z* 被转换为 Y*（需要调整指针）
    assert(py == static_cast<Y*>(&d.obj));
    assert(py->y == 2);
    Z* pz = d.get();                 // 静态选中的就是 D::get：不转换
    assert(pz == &d.obj);
}
```

这个转换**不是免费的**：`Z*` 到 `Y*` 需要加一个偏移。实现视角一节说明编译器如何用"返回值调整 thunk"实现它。

## 动态类型与静态类型（¶10）

¶10（注 3）是对 [[expr.call]] 的提醒：虚函数调用的解释取决于对象的**动态类型**，非虚函数调用只取决于指针/引用的**静态类型**。

重要推论：**只有"调用哪个函数体"是动态的**。其余一切——名字查找、重载决议、访问检查（[[class.access.virt]]）、默认实参（[[dcl.fct.default#10]]）、返回类型（[[expr.call#4]]）——都按**静态选中的函数**决定。

### 默认实参取自静态类型

[[dcl.fct.default#10]]：虚函数调用使用的默认实参来自**由指针/引用的静态类型确定**的那个虚函数声明；覆盖函数**不继承**被覆盖函数的默认实参。

```cpp run title="default-args.cpp" ok
#include <cstdio>

struct A {
    virtual void f(int a = 7) { std::printf("A::f(%d)\n", a); }
    virtual ~A() = default;
};
struct B : A {
    void f(int a = 42) override { std::printf("B::f(%d)\n", a); }
};

int main() {
    B b;
    A& ra = b;
    ra.f();     // 打印 B::f(7)：调用 B::f，但默认实参来自 A::f
    b.f();      // 打印 B::f(42)
}
```

为什么这样设计？默认实参是在**调用点**由编译器补上的，编译器在调用点只知道静态类型；如果要按动态类型选默认实参，就需要把默认实参也放进 vtable，开销与复杂度都不值得。实践建议：**覆盖函数不要重新指定默认实参**（clang-tidy 有专门的检查）。

### 合约断言 {{c++26}}

C++26 的合约在虚调用中同样体现了"静态 + 动态"的双重性（[[expr.call#5]]）：一次虚函数调用依次检查**静态选中的函数**的前置条件、**实际被调用的函数**的前置条件；返回后依次检查实际被调用函数的后置条件、静态选中函数的后置条件。标准例子中，`x1ref.f()` 断言 a、g、h、b——`a`/`b` 来自 `X1::f`（静态），`g`/`h` 来自 `Z::f`（动态）。用限定名调用 `x1ref.X1::f()` 则不是虚调用，只断言 a、b。

## 不能是非成员或静态成员（¶11）

¶11（注 4）：`virtual` 意味着成员身份，所以虚函数不能是非成员函数；也不能是静态成员，因为虚调用依赖一个具体对象来决定调用哪个函数。虚函数可以被另一个类声明为**友元**（[[class.friend]]）——友元关系授予的是访问权，与虚性无关。

## 必须定义或声明为纯虚（¶12）

¶12：在类中声明的虚函数必须被**定义**、或被声明为**纯虚**（[[class.abstract]]），或者两者兼有；**不要求诊断**（{{ifndr}}）。

为什么是 IFNDR？因为虚函数的地址要放进 vtable，即使程序从不调用它，只要创建了该类的对象，vtable 就需要它的定义——这比普通函数的"odr-use 才需要定义"更严格（[[basic.def.odr#8]] 规定非纯虚的虚成员函数**总是**被 odr-use）。定义可能在别的 TU 中，编译器无法在编译时检查，只能留给链接器。

```cpp title="missing-virtual-def.cpp" ifndr
struct W {
    virtual void f();          // 只声明，从未定义
    virtual void g() {}
};

int main() { W w; }            // IFNDR：实践中表现为链接错误
```

!!! impl "缺失的 vtable"
    在 Itanium ABI 中，vtable 被放在定义了**关键函数**（key function，类中第一个非内联、非纯虚的虚函数）的那个 TU 里。上例的关键函数是 `W::f`，它没有定义，所以**整个 vtable 都没有被生成**，链接器报告的是"找不到 W 的 vtable"，而不是"找不到 W::f"——这是 C++ 新手最困惑的链接错误之一。本机链接器（macOS ld）甚至会附带提示：缺失的 vtable 通常意味着第一个非内联虚函数没有定义。

## 限定名调用抑制虚机制（¶16）

¶16：用作用域运算符显式限定（`B::f()`）会**抑制**虚调用机制。这是派生类"在覆盖中调用基类版本"的标准写法：

```cpp run title="qualified-call.cpp" ok
#include <cstdio>

struct B { virtual void f() { std::puts("B::f"); } virtual ~B() = default; };
struct D : B {
    void f() override {
        B::f();                 // 静态绑定到 B::f，不会无限递归
        std::puts("D::f");
    }
};

int main() {
    D d;
    B& b = d;
    b.f();       // D::f → B::f
    b.B::f();    // 只调用 B::f
}
```

!!! lawyer "splice 不抑制虚调用"
    [[expr.call#2]] 说：选中的函数是非虚的，**或者**类成员访问中的 *id-expression* 是 *qualified-id*，才调用该函数本身；否则调用最终覆盖者。C++26 的 *splice-expression* `x.[: ^^X1::f :]()` 不是 *qualified-id*，因此**仍然是虚调用**——标准在 [expr.call] 的例子中明确写出了这一点。同一个例子还表明，经成员指针的调用 `(x1ref.*pmf)()` 也是虚调用（只断言 g、h）。

## deleted 与 consteval 必须配对（¶17–¶18）

¶17：deleted 函数不能覆盖非 deleted 函数；非 deleted 函数也不能覆盖 deleted 函数。

¶18：非立即（非 consteval）虚函数不能被立即虚函数覆盖；立即虚函数也不能被非立即虚函数覆盖。

两条规则的道理相同：**通过基类调用时，调用者只看到基类的声明**。如果基类函数可调用，而最终覆盖者是 deleted 的，那么 `b.f()` 能通过编译却无函数可调；反之，基类 deleted 而派生类可调，则 deleted 失去意义。consteval 同理：consteval 的调用必须在编译期完成，若基类版本不是 consteval 而覆盖者是，运行期的虚调用就会落到一个只能在编译期调用的函数上。

```cpp title="deleted-consteval.cpp" error
struct B {
    virtual void del() = delete;
    virtual void ok();
    virtual consteval int ce() const { return 1; }
    virtual int rt() const { return 1; }
};
struct D : B {
    void del() override;                              // error: 非 deleted 覆盖 deleted
    void ok() override = delete;                      // error: deleted 覆盖非 deleted
    int ce() const override { return 2; }             // error: 非立即函数覆盖立即函数
    consteval int rt() const override { return 2; }   // error: 立即函数覆盖非立即函数
};
```

与之配套，[[except.spec#5]] 规定：若虚函数有**不抛出**的异常说明，覆盖它的函数也必须不抛出（除非覆盖者是 deleted 的）——同样是为了让基于基类声明所做的假设对最终覆盖者也成立。反方向（基类可能抛出、覆盖者 `noexcept`）是允许的，因为覆盖者的承诺更强。

## 常量求值中的虚函数

C++20（[[P1064R0]]）起，`constexpr` 函数可以是虚函数，常量求值中可以进行虚调用——常量求值器总是知道对象的动态类型。consteval 虚函数也只能在常量求值中被调用：

```cpp run title="constexpr-virtual.cpp" ok
struct Shape {
    constexpr virtual int sides() const { return 0; }
    constexpr virtual ~Shape() = default;
};
struct Tri : Shape { constexpr int sides() const override { return 3; } };

constexpr int count() {
    Shape* p = new Tri;          // C++20：常量求值中的动态分配
    int n = p->sides();          // 常量求值中的虚调用
    delete p;                    // 虚析构
    return n;
}
static_assert(count() == 3);

struct CB { virtual consteval int id() const { return 1; } };
struct CD : CB { consteval int id() const override { return 2; } };
consteval int cid() { CD d; const CB& b = d; return b.id(); }
static_assert(cid() == 2);

int main() { }
```

限制：对一个**动态类型为 constexpr-unknown** 的对象（例如函数形参引用所指的、生命周期不在本次求值内开始的对象）做虚调用，不是常量表达式（[[expr.const.core]]/2.6）。

---

## 构造与析构期间的虚调用

详细规则在 [[class.cdtor#4]]，这里给出要点：构造函数（或析构函数）中，直接或间接地对正在构造/析构的对象调用虚函数时，调用的是**构造函数/析构函数所属类**中的最终覆盖者，而不是更派生类中的覆盖者。

直觉：构造 `Der` 时先构造 `Base` 子对象，此时 `Der` 的成员还没有初始化；如果 `Base()` 里调用 `who()` 进入 `Der::who()`，后者访问的就是未初始化的成员。所以 C++ 规定：对象在 `Base` 构造期间"表现为"一个 `Base`。

```cpp run title="cdtor-virtual.cpp" ok
#include <cstdio>

struct Base {
    Base()  { who(); }
    virtual void who() { std::puts("Base::who"); }
    virtual ~Base() { who(); }
};
struct Der : Base {
    Der()   { who(); }
    void who() override { std::puts("Der::who"); }
    ~Der() override { who(); }
};

int main() { Der d; }
// 输出：Base::who / Der::who / Der::who / Base::who
```

若此时对象所属类中的最终覆盖者是**纯虚函数**，行为未定义（[[class.abstract#6]]）——这就是著名的"pure virtual function called"运行期错误的来源。

---

## 实现视角

!!! impl "vptr 与 vtable"
    所有主流实现都用**虚函数表**（vtable）实现虚函数：每个多态类有一张（或一组）静态的函数指针表；每个多态对象（或子对象）里存一个指向表的**虚表指针**（vptr）。虚调用 = 读 vptr → 按固定槽位取函数指针 → 间接调用。标准中没有出现 vtable 一词，但几乎每条规则都可以从这个模型推出来：
    
    - 成员函数模板不能是虚函数：表的大小必须固定；
    - 构造期间调用基类版本：构造函数在进入时把 vptr 设置为**本类**的 vtable，逐层更新；
    - 默认实参按静态类型：默认实参不在表里；
    - [[basic.life]] 中"生命周期外不能做虚调用/`dynamic_cast`/转换到虚基类"：这些操作都要读 vptr。

!!! impl "Itanium C++ ABI 的 vtable 布局"
    Itanium ABI（GCC、Clang 在非 Windows 平台上使用）的 vtable 中，**地址点**（address point，vptr 指向的位置）之前依次是：vcall offsets、vbase offsets、**offset-to-top**（从该子对象到完整对象顶部的偏移）、**RTTI 指针**（`typeid` 用）；地址点之后是虚函数指针。析构函数占**两个**槽：complete object destructor 与 deleting destructor（后者在析构后调用 `operator delete`，使 `delete p` 能找到正确的释放函数，对应 [[expr.delete]] 的规则）。
    
    本机 Clang 用 `-Xclang -fdump-vtable-layouts` 打印 `struct C : A, B`（`A`、`B` 各有一个虚函数，`C` 覆盖二者）的 vtable：
    
    ```text
    Vtable for 'C' (9 entries).
       0 | offset_to_top (0)
       1 | C RTTI
           -- (A, 0) vtable address --
           -- (C, 0) vtable address --
       2 | void C::f()
       3 | C::~C() [complete]
       4 | C::~C() [deleting]
       5 | void C::g()
       6 | offset_to_top (-16)
       7 | C RTTI
           -- (B, 16) vtable address --
       8 | void C::g()
           [this adjustment: -16 non-virtual] method: void B::g()
    ```
    
    要点：`A` 是**主基类**，与 `C` 共享一个 vptr 和表的前半部分；`B` 子对象位于偏移 16，有自己的 vptr，指向**次表**（secondary vtable）。

!!! impl "thunk：多重继承下的 this 调整"
    通过 `B*` 调用 `g()` 时，`this` 指向的是 `B` 子对象（偏移 16），而 `C::g` 期望的 `this` 是整个 `C`。于是次表中的槽位不直接指向 `C::g`，而是指向一个 **this 调整 thunk**：先把 `this` 减 16，再跳转到 `C::g`（上面的 `[this adjustment: -16 non-virtual]`）。若基类是**虚基类**，偏移在编译期未知，thunk 需要从 vtable 中读取 **vcall offset** 再调整——这就是"virtual thunk"。
    
    **协变返回**需要反方向的 **return 调整 thunk**：先调用真正的函数，再调整返回的指针。本机对"`D::get` 返回 `Z*`、覆盖 `B::get` 返回 `Y*`、`Y` 位于 `Z` 的偏移 16"的 dump：
    
    ```text
       2 | Z *D::get()
           [return adjustment: 16 non-virtual] method: Y *B::get()
       3 | Z *D::get()
    ```
    
    `D` 的表中有**两个**槽：继承自 `B` 的槽（经 thunk 返回 `Y*`）和 `D` 新增的槽（直接返回 `Z*`，供通过 `D*` 的虚调用使用）。这解释了 ¶9 为什么要求返回类型中的类在此处完整：生成 thunk 需要知道偏移量。

!!! impl "MSVC 的不同之处"
    MSVC 的 vtable 没有 offset-to-top 字段（RTTI 通过表前一个槽中的"完整对象定位器"获得），虚基类的偏移放在单独的 **vbtable** 中并有单独的 vbptr；析构函数在表中只占一个"标量删除析构函数"槽，以一个标志参数区分是否释放内存。协变返回与 this 调整同样通过 thunk 实现。

!!! impl "去虚化（devirtualization）"
    当编译器能证明对象的动态类型时，虚调用可以变成直接调用（进而内联）。常见依据：
    
    - 类或函数被标为 `final`；
    - 对象是局部变量或刚由 `new` 创建（动态类型已知）；
    - 整个程序分析（LTO + `-fwhole-program-vtables` 等）证明某个虚函数只有一个覆盖者；
    - GCC 的推测去虚化（speculative devirtualization）：先比较 vptr 是否等于预期的表，相等则直接调用。
    
    本机 Clang `-O2`（x86-64 目标）对 `struct D final : B` 的对比：
    
    ```text
    call_b(B const&):          # 通过 B&：读 vptr，间接跳转
        movq    (%rdi), %rax
        jmpq    *(%rax)
    call_d(D const&):          # 通过 final 类 D&：直接尾调用 D::f
        jmp     D::f() const
    ```
    
    [[basic.life]] 的规则（对象的动态类型在生命周期内不变、`std::launder` 的必要性）正是为这类优化提供法律依据。

## 历史与演进

!!! history
    - **C++98**：虚函数、纯虚函数、协变返回类型（ARM 时代末期加入）都已存在。
    - **C++11**：`override` 与 `final`（以上下文关键字形式引入，避免破坏使用这些名字作标识符的代码）；deleted 函数及 ¶17 的配对规则；引用限定符及 ¶7。
    - **C++20**：[[P1064R0]] 允许常量求值中的虚函数调用，`constexpr` 虚函数；立即函数（`consteval`）引入后加入 ¶18 的配对规则；概念引入后加入 ¶6（虚函数不能有约束）；`constexpr` 虚析构函数使常量求值中的 `delete` 多态对象成为可能。
    - **C++23**：[[P0847R7]]（deducing this）引入显式对象成员函数，并规定它们不能是虚函数。
    - **C++26** {{c++26}}：合约断言在虚调用中按"静态选中函数 + 实际调用函数"双重检查（[expr.call]/5）；*splice-expression* 进行的成员调用仍是虚调用。

## 陷阱

!!! pitfall
    1. **签名差一点就不是覆盖**：`const`、引用限定符、形参类型（`int` vs `long`、`T&` vs `const T&`）任何一处不同，结果都是"隐藏"而非"覆盖"，且没有任何错误。**总是写 `override`。**
    2. **覆盖函数里重新写默认实参**：通过基类调用时用的是基类的默认实参。
    3. **基类没有虚析构函数却通过基类指针 `delete`**：UB（[[expr.delete#3]]）。多态基类的析构函数应当是 public 且 virtual，或者 protected 且非 virtual。
    4. **在构造/析构函数中调用虚函数期望得到派生类行为**：得到的是当前类的版本；若是纯虚，则是 UB。
    5. **虚函数声明了却没定义**：IFNDR，实践中是"找不到 vtable"的链接错误。
    6. **以为 using 声明会改变最终覆盖者**：using 只影响名字查找，`c.f()` 仍然调用最终覆盖者，只有 `c.C::f()` 这种限定调用才会落到 using 引入的函数。
    7. **成员函数模板"覆盖"虚函数**：[[temp.mem#4]]：成员函数模板的特化**不会**覆盖基类虚函数。

## 思考题

!!! question "思考题 1"
    ```cpp
    struct B { virtual void f(int = 1); };
    struct D : B { void f(int = 2) override; };
    struct E : D { void f(int) override; };
    void t(E& e) { D& d = e; B& b = e; e.f(); d.f(); b.f(); }
    ```
    `t` 中哪些调用合法？合法的调用了哪个函数、实参是几？

<details markdown="1">
<summary>答案</summary>

`e.f()` ill-formed：静态类型 `E` 的 `E::f` 没有默认实参（覆盖函数不继承默认实参），实参个数不对。`d.f()` 合法，调用 `E::f(2)`——函数由动态类型决定，默认实参来自静态类型 `D` 的声明。`b.f()` 合法，调用 `E::f(1)`。由于 `e.f()` 使整个函数 ill-formed，删掉它之后另外两个调用才能编译。
</details>

!!! question "思考题 2"
    下面的程序合法吗？若合法，`p->f()` 调用谁？
    ```cpp
    struct A { virtual void f(); };
    struct B : virtual A { void f() override; };
    struct C : virtual A { };
    struct D : B, C { };
    void g(C* p) { p->f(); }   // 调用时 p 指向 D 对象中的 C 子对象
    ```

<details markdown="1">
<summary>答案</summary>

合法。`A` 是虚基类，`D` 中只有一个 `A` 子对象，它的 `f` 在 `D` 中只有一个最终覆盖者 `B::f`（`C` 没有覆盖），满足唯一性。`p->f()` 静态上选中 `A::f`（经 `C` 继承），动态上调用最终覆盖者 `B::f`——即使 `C` 与 `B` 毫无关系。实现上，`D` 的 vtable 中对应 `C` 子对象的次表里，`f` 的槽位指向一个 thunk，它把 `this` 从 `C` 子对象调整到 `B` 子对象再调用 `B::f`。
</details>

!!! question "思考题 3"
    为什么 ¶9 允许 `struct D : B { D* clone() override; };`（此时 `D` 尚不完整），却不允许返回一个不完整的、与 `D` 无关的派生类指针？

<details markdown="1">
<summary>答案</summary>

协变返回需要把 `X*` 转换为 `B*`，编译器必须知道 `B` 在 `X` 中的偏移（以及转换是否可访问、无二义）。对一个与 `D` 无关的不完整类 `X`，这一信息在覆盖声明处不可得，而 vtable 的槽位布局（是否需要新槽、是否需要 return thunk）恰恰需要在此时确定。对 `D` 自身，虽然在类体中它还不完整，但它的基类列表已经确定（基类子对象在 *base-clause* 处就已知道），偏移与可访问性都可以计算，所以标准特别允许。
</details>

## 小结

!!! summary
    | 主题 | 规则 |
    |---|---|
    | 虚函数 | 首次声明带 `virtual`，或覆盖了基类虚函数；含虚函数的类是多态类 |
    | 覆盖 | 派生类中与之**对应**的声明（同名、同非对象形参列表、同 cv/引用限定，忽略 requires 子句）；不看访问权；不需可见 |
    | 最终覆盖者 | 每个子对象的每个虚函数必须有唯一的最终覆盖者，否则 ill-formed |
    | `final` / `override` | 覆盖 final ⇒ ill-formed；override 但没覆盖 ⇒ ill-formed |
    | 约束 / 引用限定 | 虚函数不能有尾随 requires 子句；引用限定符必须一致 |
    | 协变返回 | 同为类指针/左值引用/右值引用；基类可访问无二义；cv 不增加；类须完整或为 D 本身 |
    | 静态 vs 动态 | 只有被调用的函数体是动态的；默认实参、访问、返回类型都按静态类型 |
    | 定义 | 虚函数必须定义或为纯虚（IFNDR） |
    | 限定调用 | `B::f()` 抑制虚调用；splice 不抑制 |
    | 配对 | deleted ↔ deleted；consteval ↔ consteval；noexcept 基类 ⇒ noexcept 覆盖者 |
    | 不能是虚函数 | 静态成员、构造函数、成员函数模板、带约束的函数、显式对象成员函数 |
