---
title: 虚函数
summary: 哪些成员函数是虚函数，派生类的函数何时覆盖基类的虚函数，虚调用最终执行哪个函数，以及覆盖两端在返回类型、限定符、deleted、consteval 上必须满足的约束。
status: done
papers: P1064R0, P0847R7
related: class.derived, class.abstract, class.access, class.cdtor, expr.call, dcl.fct.default, basic.scope.scope, class.dtor, except.spec, expr.dynamic.cast, expr.typeid
tags: 类, 虚函数, 多态, 覆盖, ABI
updated: 2026-10-19
---

!!! tldr
    - 成员函数首次声明时带 `virtual`，或者覆盖了基类的虚函数，它就是虚函数；派生类里写不写 `virtual` 都一样。
    - 派生类的函数与基类虚函数在名字、形参类型、cv 限定符和引用限定符上都对应，才算覆盖；返回类型和访问权不参与判断，差一点就变成隐藏，所以要写 `override`。
    - 通过基类指针或引用调用虚函数，执行的是对象动态类型中的最终覆盖者；每个基类子对象的每个虚函数必须只有一个最终覆盖者。
    - 只有执行哪个函数体是在运行时决定的。名字查找、重载决议、访问检查、默认实参、调用表达式的类型都按静态类型确定。
    - 用限定名 `B::f()` 调用会关闭虚调用；声明了的虚函数必须定义（或为纯虚），否则通常表现为找不到 vtable 的链接错误。

```cpp run ok
#include <cstdio>
struct Shape {
    virtual void draw() const { std::puts("Shape"); }
    virtual ~Shape() = default;
};
struct Circle : Shape {
    void draw() const override { std::puts("Circle"); }
};
int main() {
    Circle c;
    const Shape& s = c;
    s.draw();     // 打印 Circle
}
```

`s` 的静态类型是 `Shape`，它引用的对象却是一个 `Circle`。一个 glvalue 所指对象的最派生类型叫它的**动态类型**（[[defns.dynamic.type]]）。`draw` 是虚函数，所以 `s.draw()` 按动态类型选择函数体，执行 `Circle::draw`。

这种调用叫做**虚函数调用**（virtual function call），定义在 [[expr.call#2]]：选中的函数是虚函数、且没有用限定名指名时，调用它在对象动态类型中的最终覆盖者。本节规定哪些函数是虚函数、什么叫覆盖、最终覆盖者是谁，以及覆盖时要满足的约束。构造和析构期间的虚调用另见 [[class.cdtor#4]]。

## 哪些函数是虚函数（¶1、¶11）

¶1 一个非静态成员函数在两种情况下是虚函数：首次声明时带关键字 `virtual`，或者它覆盖了某个基类中声明的虚函数。脚注 85 说明，在覆盖函数上再写 `virtual` 合法但多余。所以虚函数的性质是沿继承传下去的，派生类里签名对应的函数自动是虚函数。

含有虚函数（自己声明的或继承来的）的类叫做**多态类**（polymorphic class）。只有多态类才能用 `dynamic_cast` 向下转换（[[expr.dynamic.cast]]），`typeid` 也只对多态类的 glvalue 求值操作数、返回动态类型（[[expr.typeid]]）。脚注 86 补充，即使所有虚函数都是 `consteval` 的，运行时根本不需要 vtable，这个类仍然是多态类。

下面几类函数不能是虚函数：

| 函数 | 依据 |
|---|---|
| 非成员函数、静态成员函数 | ¶11：虚调用要靠一个具体的对象决定调用目标 |
| 构造函数 | [[class.ctor]] |
| 成员函数模板 | [[temp.mem#3]]：vtable 的大小在类定义时就要确定，模板的特化个数却没有上限 |
| 带尾随 *requires-clause* 的函数 | ¶6，见下文 |
| 显式对象成员函数（第一个形参带 `this`） | [[dcl.fct#7]] |

```cpp title="cannot-be-virtual.cpp" error
struct S {
    virtual static void a();              // error: 静态成员
    template<class T> virtual void b(T);  // error: 成员函数模板
    virtual void c(this S& self);         // error: 显式对象成员函数
};
template<class T> struct R {
    virtual void d() requires true;       // error: 带约束
};
```

¶11 的注还提到，一个类的虚函数可以被另一个类声明为友元（[[class.friend]]）。友元关系授予的是访问权，与虚函数无关。

## 覆盖（¶2–¶3）

### 差一点就不是覆盖

```cpp run title="overriding-basics.cpp" ok
#include <cstdio>
struct B {
    virtual void f(int)    { std::puts("B::f(int)"); }
    virtual void g() const { std::puts("B::g const"); }
    virtual ~B() = default;
    void call_h() { h(); }
private:
    virtual void h()       { std::puts("B::h"); }
};
struct D : B {
    void f(int) override   { std::puts("D::f(int)"); }
    void f(long)           { std::puts("D::f(long)"); }
    void g()               { std::puts("D::g"); }
    void h() override      { std::puts("D::h"); }
};
int main() {
    D d;
    B& b = d;
    b.f(1);       // D::f(int)：覆盖
    b.g();        // B::g const：D::g 少了 const，不覆盖
    b.call_h();   // D::h：覆盖不看访问权
}
```

`D::f(long)` 和 `D::g()` 都没有覆盖任何函数，它们只是同名的新函数，并且在 `D` 的作用域里隐藏了基类的同名函数。编译器不会报错。Clang 在 `-Wall` 下对 `D::g` 给出 `-Woverloaded-virtual` 警告（隐藏了重载的虚函数），这种警告几乎总是意味着 bug。

### 覆盖的定义

¶2 第一句给出定义：

!!! std
    If a virtual member function F is declared in a class B, and, in a class D derived (directly or indirectly) from B, a declaration of a member function G corresponds to a declaration of F, ignoring trailing requires-clauses, then G overrides F.

如果虚函数 F 声明在类 B 中，而在（直接或间接）派生自 B 的类 D 中，某个成员函数 G 的声明与 F 的声明[[g:correspond|对应]]（忽略尾随 *requires-clause*），就说 G **覆盖**（override）F。

对应是 [[basic.scope.scope#4]] 定义的术语，原本用来判断同一作用域里的两个声明是不是同一个函数。对两个非静态成员函数，它要求：

- 名字相同，或者都是析构函数。所以派生类的析构函数会覆盖基类的虚析构函数，虽然两者名字不同。
- 非对象形参类型列表相同，也就是除去 `this` 对应的那个形参以外的形参类型（顶层 cv 已被忽略）。
- 对象形参对应（[[basic.scope.scope#3]]），这一条比较 cv 限定符和引用限定符。`void g() const` 与 `void g()` 不对应，所以不覆盖。

不参与比较的有：返回类型（由 ¶8 另外约束）、异常说明（由 [[except.spec#5]] 另外约束）、访问权（脚注 87）、默认实参、`constexpr`。

!!! lawyer "跨类比较对象形参"
    隐式对象成员函数的对象形参类型带着所属的类：`B::f` 的是 `B&`，`D::f` 的是 `D&`。按 [[basic.scope.scope#3]] 的字面，这两个类型并不相同。¶2 的意图显然是比较所属类之外的部分，即 cv 限定和引用限定，所有实现都这样理解。

### 被覆盖的函数不必可见

¶3 注 2 说明，覆盖是在类层次上定义的，不经过名字查找。下例中 `D::f(int)` 隐藏了 `B::f()`，在 `D2` 里查找 `f` 根本找不到 `B::f()`，但 `D2::f()` 照样覆盖它：

```cpp run title="override-invisible.cpp" ok
#include <cstdio>
struct B  { virtual void f() { std::puts("B::f"); } virtual ~B() = default; };
struct D  : B { void f(int) {} };       // 隐藏 B::f()；D::f(int) 不是虚函数
struct D2 : D { void f() override { std::puts("D2::f"); } };
int main() {
    D2 d2;
    B& b = d2;
    b.f();        // D2::f
}
```

## 最终覆盖者（¶2、¶13–¶15）

¶2 接着规定，为了表述方便，任何虚函数都覆盖它自己。对类对象 S 的虚函数 V，如果 S 所在的最派生对象的类里没有另一个覆盖 V 的函数，V 就是 S 的**最终覆盖者**（final overrider）。

直观地说，从完整对象的类型往下看，对这个子对象的 V 覆盖得最晚的那个函数就是最终覆盖者，虚调用执行的正是它。

¶2 的最后一句要求唯一：派生类中，如果某个基类子对象的虚函数有不止一个最终覆盖者，程序非良构。这条规则以子对象为单位计算，所以普通继承和虚继承的结果不同。

### 普通继承：每个子对象各算各的

```cpp run title="final-overrider-nonvirtual.cpp" ok
#include <cstdio>
struct A  { virtual void f() { std::puts("A::f"); } virtual ~A() = default; };
struct B1 : A { void f() override { std::puts("B1::f"); } };
struct B2 : A { void f() override { std::puts("B2::f"); } };
struct D  : B1, B2 {};   // 两个 A 子对象
int main() {
    D d;
    // A* ap = &d;        // error: 哪个 A？二义
    A* ap1 = static_cast<B1*>(&d);
    A* ap2 = static_cast<B2*>(&d);
    ap1->f();             // B1::f
    ap2->f();             // B2::f
    // d.f();             // error: 名字查找二义
}
```

`D` 里有两个 `A` 子对象，各有一个 `f`。`B1` 那个的最终覆盖者是 `B1::f`，`B2` 那个的是 `B2::f`，互不冲突（标准例 7）。标准例 2 是同一个道理：一边覆盖、一边不覆盖，两个子对象分别以 `C::f` 和 `A::f` 为最终覆盖者。

### 虚继承：共享的子对象只能有一个

虚继承让两条路径共享同一个 `A` 子对象。两条路径上的覆盖者争的是同一个 `f`，就可能出现两个最终覆盖者（¶14，例 8）：

```cpp title="final-overrider-virtual.cpp" error
struct A   { virtual void f(); };
struct VB1 : virtual A { void f(); };
struct VB2 : virtual A { void f(); };
struct Error : VB1, VB2 {};             // error: A::f 有两个最终覆盖者
struct Okay  : VB1, VB2 { void f(); };  // OK: Okay::f 覆盖二者
```

如果只有一条路径覆盖了 `f`，结果可能出人意料（¶15，例 9）：

```cpp run title="cross-delegation.cpp" ok
#include <cstdio>
struct A    { virtual void f() { std::puts("A::f"); } virtual ~A() = default; };
struct VB2  : virtual A { void f() override { std::puts("VB2::f"); } };
struct VB1a : virtual A {};       // 不声明 f
struct Da   : VB1a, VB2 {};
int main() {
    VB1a* p = new Da;
    p->f();       // VB2::f
    delete p;
}
```

在 `Da` 中，共享的 `A` 子对象的 `f` 只有一个覆盖者 `VB2::f`，它就是最终覆盖者。于是通过 `VB1a*` 调用 `f`，进入的是兄弟分支 `VB2` 里的函数，而 `VB1a` 对 `VB2` 一无所知。这是虚继承共享子对象的直接结果。

### using 声明不参与覆盖

```cpp run title="using-and-override.cpp" ok
#include <cstdio>
struct A { virtual void f() { std::puts("A::f"); } virtual ~A() = default; };
struct B : virtual A { void f() override { std::puts("B::f"); } };
struct C : B, virtual A { using A::f; };
int main() {
    C c;
    c.f();        // B::f：查找经 using 找到 A::f，但这是虚调用
    c.C::f();     // A::f：限定名关闭虚调用（¶16）
}
```

这是标准例 1。using 声明只把名字引入 `C` 的作用域，影响名字查找；最终覆盖者仍按类层次计算，是 `B::f`。

## `override` 与 `final`（¶4–¶5）

```cpp title="final-override.cpp" error
struct B {
    virtual void f() const final;
    virtual void g(int);
};
struct D : B {
    void f() const;          // error: 覆盖了 final 的 B::f
    void g(long) override;   // error: 标了 override 却没有覆盖
    void g(int) override;    // OK
};
```

¶4 如果基类的虚函数标了 `final`，派生类中任何覆盖它的函数都使程序非良构。¶5 标了 `override` 的函数如果没有覆盖任何基类成员函数，程序非良构。

`override` 把我以为在覆盖变成了编译器检查的事实，能抓住整类签名错误：`int` 写成 `long`、漏了 `const`、基类函数改了名。两者都是上下文关键字，只在成员函数声明符的末尾有特殊含义，其他地方仍可当普通标识符用。

几个细节：

- `final` 可以标在首次引入的虚函数上（`virtual void f() final;`），这样派生类不能覆盖它。`final` 和 `override` 可以同时出现。
- 二者只能出现在虚函数的首次声明里，不能出现在类外定义上，每种最多出现一次（[[class.mem.general#19]]）。标在非虚函数上是非良构的。
- 类级别的 `final`（`struct D final : B`）禁止从 `D` 派生（[[class.pre]]），于是 `D` 的虚函数都不会再被覆盖，编译器可以据此去虚化。

## 覆盖两端必须相容

调用者只看到基类的声明，并按它来编译调用。所以覆盖函数不能违背基类声明给出的承诺。下面几条规则都出于这个考虑。

### 引用限定符相同（¶7）

¶7 覆盖函数的引用限定符（或没有引用限定符）必须与被覆盖函数相同。

```cpp title="ref-qualifier.cpp" error
struct B {
    virtual void g();
    virtual void k() &;
};
struct D : B {
    void g() &;    // error: 覆盖 B::g，但引用限定符不同
    void k() &&;   // 不对应 B::k() &：新函数，隐藏 B::k
};
```

这条规则只在对应规则放行时才起作用。按 [[basic.scope.scope#3]]，恰好一个是没有引用限定符的隐式对象成员函数时，去掉引用再比较，所以 `virtual void g();` 与 `void g() &;` 对应，后者覆盖前者，再因 ¶7 而非良构。`&` 与 `&&` 则根本不对应，只是隐藏。

对 `D::g`，Clang 报告的是带引用限定符和不带的同名函数不能重载，这是 [[over.load]] 中同一条规则的另一面；对 `D::k` 只给出隐藏虚函数的警告。

### 不能带约束（¶6）

¶6 虚函数不能有尾随 *requires-clause*。约束决定一个函数在某个特化里是否存在，而 vtable 的槽位在类定义时就必须固定。如果类模板的虚函数可以带约束，就会出现有的特化有这个槽、有的没有，覆盖关系也要随约束是否满足而变。

注意 ¶2 判断覆盖时忽略尾随 *requires-clause*。派生类中带约束、签名对应的函数照样被认定为覆盖者，于是它成了虚函数，再因 ¶6 而非良构。

### deleted、consteval 与 noexcept（¶17–¶18）

```cpp title="deleted-consteval.cpp" error
struct B {
    virtual void del() = delete;
    virtual void ok();
    virtual consteval int ce() const { return 1; }
    virtual int rt() const { return 1; }
};
struct D : B {
    void del() override;              // error: 非 deleted 覆盖 deleted
    void ok() override = delete;      // error: deleted 覆盖非 deleted
    int ce() const override { return 2; }   // error
    consteval int rt() const override { return 2; }  // error
};
```

¶17 deleted 函数不能覆盖非 deleted 函数，反过来也不行。如果允许前者，`b.ok()` 能通过编译，运行时却无函数可调；允许后者，基类的 `= delete` 就失去了意义。

¶18 立即函数（`consteval`）与非立即函数不能互相覆盖。立即函数只能在编译期调用，如果它覆盖了一个普通虚函数，运行时的虚调用就会落到它身上。

异常说明的规则在 [[except.spec#5]]：基类虚函数不抛出时，覆盖它的函数也必须不抛出，除非覆盖者是 deleted 的。反方向（基类可能抛出、覆盖者 `noexcept`）是允许的，承诺只能加强。

## 协变返回类型（¶8–¶9）

覆盖函数的返回类型一般必须与被覆盖函数相同。例外是 `clone` 这类函数：基类返回 `Base*`，派生类希望返回 `Derived*`，这样通过 `Derived` 调用时不必再转换。

¶8 覆盖函数的返回类型必须与被覆盖函数相同，或者与之**协变**（covariant）。`D::f` 覆盖 `B::f` 时，两者的返回类型协变，当且仅当：

- ¶8.1 两者都是指向类的指针，或都是类的左值引用，或都是类的右值引用。脚注 88 排除了多级指针和指向多级指针的引用。
- ¶8.2 `B::f` 返回类型中的类与 `D::f` 的相同，或者是后者无二义、可访问的（直接或间接）基类。
- ¶8.3 两个指针或引用本身的 cv 限定相同，并且 `D::f` 返回类型中的类类型的 cv 限定与 `B::f` 的相同或更少。

¶9 再加两条。第一，如果两边的类不同，`D::f` 返回类型中的类在覆盖声明的[[g:locus|声明点]]必须是完整类型，或者就是 `D` 本身，所以 `D* clone()` 可以写在 `D` 的类体里。第二，覆盖函数作为最终覆盖者被调用时，它的结果要转换成静态选中的那个被覆盖函数的返回类型（[[expr.call]]）。

这些条件都来自调用者的视角：调用点按 `B::f` 编译，期待拿到一个 `A1*`。`D::f` 返回的 `A2*` 必须能在调用处不知道内情的情况下转换过去。所以只能是指针或引用（按值返回大小可能不同），基类必须可访问且无二义（否则转换本身不合法），类必须完整（编译器要知道基类的偏移才能调整指针），cv 也不能增加。

```cpp title="covariance.cpp" error
struct A1 {};
struct A2 : A1 {};
struct A3 : A1 {};
struct Amb : A2, A3 {};      // 两个 A1
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
    A2*  p1() override;       // OK
    Amb* p2() override;       // error: A1 是二义基类
    Priv* p3() override;      // error: A1 是私有基类
    A2&& r1() override;       // error: 左值引用对右值引用
    const A2* p4() override;  // error: cv 增加了
    A2** pp() override;       // error: 多级指针
    Inc* p5() override;       // error: Inc 不完整
    A2   v() override;        // error: 按值返回
    A2*  c() override;        // OK: cv 减少
    D*   self() override;     // OK: 不完整，但就是 D
};
```

¶8.2 的可访问在覆盖函数所在类的语境中判断。标准例 6 中 `class D : private B { friend class Derived; };`，`No_good::vf4` 不能返回 `D*`，因为在 `No_good` 里 `B` 是 `D` 的不可访问基类；`Derived` 是 `D` 的友元，`Derived::vf4` 就可以。

### 协变调用要调整指针

```cpp run title="covariant-call.cpp" ok
#include <cassert>
struct X { virtual ~X() = default; int x = 1; };
struct Y { virtual ~Y() = default; int y = 2; };
struct Z : X, Y { int z = 3; };   // Y 子对象不在偏移 0

struct B { virtual Y* get() { return nullptr; } virtual ~B() = default; };
struct D : B {
    Z obj;
    Z* get() override { return &obj; }
};
int main() {
    D d;
    B& b = d;
    Y* py = b.get();    // 调用 D::get，Z* 转换为 Y*
    assert(py == static_cast<Y*>(&d.obj));
    assert(py->y == 2);
    Z* pz = d.get();    // 静态选中的就是 D::get，不转换
    assert(pz == &d.obj);
}
```

`Z*` 到 `Y*` 需要加上 `Y` 子对象的偏移，这次转换并不免费。实现视角一节说明编译器怎样用返回值调整 thunk 实现它。

## 只有函数体是动态选择的（¶10）

¶10 的注重申 [[expr.call]] 的规则：虚函数调用的含义取决于对象的动态类型，非虚函数调用只取决于指针或引用的静态类型。

反过来说，除了执行哪个函数体，其余一切都按静态选中的函数确定：名字查找、重载决议、访问检查（[[class.access.virt]]）、默认实参（[[dcl.fct.default#10]]）、调用表达式的类型（[[expr.call#4]]）。

### 默认实参取自静态类型

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
    ra.f();     // B::f(7)
    b.f();      // B::f(42)
}
```

[[dcl.fct.default#10]] 规定，虚函数调用使用的默认实参来自由静态类型确定的那个声明，覆盖函数也不会继承被覆盖函数的默认实参。默认实参是编译器在调用点补上的，调用点只知道静态类型；按动态类型选默认实参，就得把默认实参也放进 vtable，代价不值得。实践中不要在覆盖函数里重新指定默认实参，clang-tidy 有专门的检查。

### 契约断言 {{c++26}}

C++26 的契约断言在虚调用中同样分静态和动态两部分（[[expr.call#5]]）。一次虚函数调用先检查静态选中函数的前置条件，再检查实际被调用函数的前置条件；返回时先检查实际被调用函数的后置条件，再检查静态选中函数的后置条件。

```cpp
struct X1 { virtual void f() pre(a) post(b) {} };
struct Z : X1 { void f() override pre(g) post(h) {} };

void t(X1& x1ref) {      // x1ref 引用一个 Z
  x1ref.f();             // 检查 a, g, h, b
  x1ref.X1::f();         // 不是虚调用：只检查 a, b
}
```

这是 [[expr.call]] 例 1 的节选（`a`、`b` 等代表布尔条件）。截至写作时 Clang 23 还不支持契约语法，这段代码没有经过编译验证。

## 用限定名关闭虚调用（¶16）

```cpp run title="qualified-call.cpp" ok
#include <cstdio>
struct B { virtual void f() { std::puts("B::f"); } virtual ~B() = default; };
struct D : B {
    void f() override {
        B::f();       // 静态绑定到 B::f，不会无限递归
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

¶16 用作用域运算符显式限定会关闭虚调用机制。这是覆盖函数调用基类版本的标准写法。

!!! lawyer "splice 和成员指针不关闭虚调用"
    [[expr.call#2]] 的条件是成员访问中的 *id-expression* 是 *qualified-id*。C++26 的 *splice-expression* `x.[: ^^X1::f :]()` 不是 *qualified-id*，所以仍是虚调用，[[expr.call]] 例 1 明确写出了这一点。经成员指针的调用 `(x.*pmf)()` 也是虚调用。

## 声明了就必须定义（¶12）

¶12 类中声明的虚函数必须定义，或者声明为纯虚（[[class.abstract]]），或者两者兼有；不要求诊断。

```cpp title="missing-virtual-def.cpp" ifndr
struct W {
    virtual void f();   // 只声明，从未定义
    virtual void g() {}
};
int main() { W w; }     // IFNDR：实践中是链接错误
```

普通函数只有被 [[g:odr-use]] 时才需要定义。虚函数不同，按 [[basic.def.odr#8]]，非纯虚的虚函数总是被 odr-use，因为它的地址要填进 vtable，程序是否调用它都一样。定义可能在别的翻译单元里，编译器检查不了，所以规则不要求诊断。

!!! impl "找不到 vtable"
    在 Itanium C++ ABI 下，vtable 只生成在定义了**关键函数**（key function）的那个翻译单元里，关键函数是类中第一个非内联、非纯虚的虚函数。上例的关键函数是 `W::f`，它没有定义，于是整张 vtable 都没有生成。链接器报告的是找不到 `W` 的 vtable，而不是找不到 `W::f`。本机的链接器还会附带提示：缺少 vtable 通常意味着第一个非内联虚函数没有定义。

## 构造与析构期间的虚调用

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

在构造函数或析构函数里对正在构造或析构的对象做虚调用，执行的是这个构造函数或析构函数所属类中的最终覆盖者（[[class.cdtor#4]]）。构造 `Base` 子对象时 `Der` 的成员还没有初始化，如果此时进入 `Der::who`，读到的就是未初始化的成员。所以在 `Base` 构造期间，对象表现得就像一个 `Base`。

如果所属类中的最终覆盖者是纯虚函数，行为未定义（[[class.abstract#6]]），常见的 pure virtual function called 崩溃就来自这里。

## 常量求值中的虚函数

```cpp run title="constexpr-virtual.cpp" ok
struct Shape {
    constexpr virtual int sides() const { return 0; }
    constexpr virtual ~Shape() = default;
};
struct Tri : Shape {
    constexpr int sides() const override { return 3; }
};
constexpr int count() {
    Shape* p = new Tri;    // 常量求值中的动态分配
    int n = p->sides();    // 虚调用
    delete p;              // 虚析构
    return n;
}
static_assert(count() == 3);

struct CB { virtual consteval int id() const { return 1; } };
struct CD : CB { consteval int id() const override { return 2; } };
consteval int cid() { CD d; const CB& b = d; return b.id(); }
static_assert(cid() == 2);

int main() {}
```

C++20 起虚函数可以是 `constexpr` 的，常量求值中也可以做虚调用（[[P1064R0]]），因为常量求值器总是知道对象的动态类型。

例外是动态类型未知的对象。常量求值中引用了一个生命期不在本次求值内开始、又不能用于常量表达式的对象时，它的动态类型是 constexpr-unknown，对它做虚调用就不是常量表达式（[[expr.const.core#2.6]]）。比如 `constexpr int k = via(s);`，其中 `via` 对形参引用 `s` 调用 `s.sides()`，Clang 报告 `virtual function called on object 's' whose dynamic type is not constant`。

## 实现视角

!!! impl "vptr 与 vtable"
    主流实现都用**虚函数表**（vtable）实现虚函数。每个多态类有一张（或一组）静态的函数指针表，每个多态对象（或子对象）里存一个指向表的**虚表指针**（vptr）。一次虚调用就是读 vptr、按固定槽位取函数指针、间接调用。标准里没有 vtable 这个词，但很多规则都能从这个模型推出来：

    - 成员函数模板不能是虚函数：表的大小必须固定。
    - 构造期间调用当前类的版本：每一层构造函数进入时把 vptr 设为本类的 vtable。
    - 默认实参按静态类型：默认实参不在表里。
    - [[basic.life]] 禁止在生命期之外做虚调用、`dynamic_cast` 或转换到虚基类：这些操作都要读 vptr。

!!! impl "Itanium C++ ABI 的 vtable 布局"
    GCC 和 Clang 在非 Windows 平台上使用 Itanium ABI。vptr 指向表中的**地址点**（address point）；地址点之前依次是 vcall offset、vbase offset、offset-to-top（从该子对象到完整对象开头的偏移）和 RTTI 指针，之后是虚函数指针。析构函数占两个槽：complete object destructor 只析构，deleting destructor 析构后再调用 `operator delete`，`delete p` 由此找到正确的释放函数。

    本机 Clang 用 `-Xclang -fdump-vtable-layouts` 打印 `struct C : A, B` 的 vtable。其中 `A` 有虚函数 `f`、虚析构函数和一个 `int` 成员，`B` 有虚函数 `g`，`C` 覆盖了 `f` 和 `g`：

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

    `A` 是主基类，与 `C` 共用一个 vptr 和表的前半部分。`B` 子对象在偏移 16 处，有自己的 vptr，指向次表（secondary vtable）。

!!! impl "thunk"
    通过 `B*` 调用 `g()` 时，`this` 指向偏移 16 处的 `B` 子对象，而 `C::g` 期望的 `this` 指向整个 `C`。所以次表的槽位不直接指向 `C::g`，而是指向一段 **this 调整 thunk**：先把 `this` 减 16，再跳到 `C::g`，就是上面的 `[this adjustment: -16 non-virtual]`。如果基类是虚基类，偏移在编译期未知，thunk 要先从 vtable 里读出 vcall offset 再调整。

    协变返回需要方向相反的**返回值调整 thunk**：先调用真正的函数，再调整返回的指针。对前面 `covariant-call.cpp` 中的 `D`，本机的输出是：

    ```text
       2 | Z *D::get()
           [return adjustment: 16 non-virtual] method: Y *B::get()
       3 | Z *D::get()
    ```

    `D` 的表里有两个 `get` 槽：继承自 `B` 的那个经 thunk 返回 `Y*`，`D` 新增的那个直接返回 `Z*`，供通过 `D*` 的虚调用使用。¶9 要求返回类型中的类在覆盖声明处完整，正是因为生成 thunk 要知道偏移。

!!! impl "MSVC"
    MSVC 的 vtable 里没有 offset-to-top，RTTI 通过表前一个槽里的完整对象定位器取得。虚基类的偏移放在单独的 vbtable 里，由单独的 vbptr 指向。析构函数在表中只占一个标量删除析构函数槽，用一个标志参数区分是否释放内存。协变返回和 this 调整同样用 thunk 实现。

!!! impl "去虚化"
    编译器能确定对象的动态类型时，可以把虚调用变成直接调用，进而内联。常见的依据有：类或函数标了 `final`；对象是局部变量或刚由 `new` 创建；整个程序分析（LTO 加 `-fwhole-program-vtables` 等）证明某个虚函数只有一个覆盖者；GCC 的推测去虚化先比较 vptr 是否等于预期的表，相等就直接调用。

    本机 Clang `-O2`（x86-64 目标）对 `struct D final : B` 的对比：

    ```text
    call_b(B const&):          # 通过 B&：读 vptr，间接跳转
        movq    (%rdi), %rax
        jmpq    *(%rax)
    call_d(D const&):          # 通过 final 类 D&：直接尾调用
        jmp     D::f() const
    ```

    [[basic.life]] 中对象的动态类型在生命期内不变、需要 `std::launder` 的规则，为这类优化提供了依据。

## 历史与演进

!!! history
    - C++98 已有虚函数、纯虚函数和协变返回类型。
    - C++11 加入 `override` 和 `final`。它们是上下文关键字，没有占用新的保留字，用这两个名字作标识符的旧代码不受影响。同期加入的 deleted 函数和引用限定符带来了 ¶17 和 ¶7。
    - C++20 允许 `constexpr` 虚函数和常量求值中的虚调用（[[P1064R0]]）；`consteval` 带来 ¶18，概念带来 ¶6。
    - C++23 的 deducing this（[[P0847R7]]）引入显式对象成员函数，并规定它们不能是虚函数。
    - C++26 {{c++26}} 规定了虚调用中契约断言的检查顺序，*splice-expression* 发起的成员调用仍是虚调用。

## 常见误解

!!! pitfall "签名看起来一样就是覆盖"
    `const`、引用限定符、形参类型（`int` 对 `long`、`T&` 对 `const T&`）任何一处不同，结果都是隐藏而不是覆盖，而且没有错误。总是写 `override`。

!!! pitfall "覆盖函数可以换一个默认实参"
    可以写，但通过基类调用时用的仍是基类声明的默认实参，同一个函数体会因调用方式不同而拿到不同的实参。

!!! pitfall "通过基类指针 delete 总是安全的"
    基类没有虚析构函数时，通过基类指针 `delete` 派生类对象是 UB（[[expr.delete#3]]）。多态基类的析构函数应当是 public 且 virtual，或者 protected 且非 virtual。

!!! pitfall "using 声明能改变调用哪个函数"
    using 声明只影响名字查找。`c.f()` 仍调用最终覆盖者，只有 `c.C::f()` 这种限定调用才会落到 using 引入的函数上。

!!! pitfall "成员函数模板可以覆盖虚函数"
    成员函数模板的特化不会覆盖基类的虚函数（[[temp.mem#4]]），模板本身也不能是虚函数。

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

`e.f()` 非良构：静态类型 `E` 中的 `E::f` 没有默认实参，覆盖函数不继承默认实参，实参个数不够。Clang 报告 `too few arguments to function call`。

`d.f()` 合法，调用 `E::f(2)`：函数由动态类型决定，默认实参来自静态类型 `D` 的声明。`b.f()` 合法，调用 `E::f(1)`。
</details>

!!! question "思考题 2"
    下面的程序合法吗？若合法，`p->f()` 调用谁？
    ```cpp
    struct A { virtual void f(); };
    struct B : virtual A { void f() override; };
    struct C : virtual A { };
    struct D : B, C { };
    void g(C* p) { p->f(); }   // p 指向某个 D 对象中的 C 子对象
    ```

<details markdown="1">
<summary>答案</summary>

合法。`A` 是虚基类，`D` 中只有一个 `A` 子对象，它的 `f` 在 `D` 中只有一个最终覆盖者 `B::f`（`C` 没有覆盖），满足唯一性。

`p->f()` 静态上选中经 `C` 继承来的 `A::f`，运行时调用最终覆盖者 `B::f`，尽管 `C` 与 `B` 没有关系。实现上，`D` 的 vtable 中对应 `C` 子对象的那张次表里，`f` 的槽位指向一个 thunk，它把 `this` 从 `C` 子对象调整到 `B` 子对象，再调用 `B::f`。
</details>

!!! question "思考题 3"
    为什么 ¶9 允许 `struct D : B { D* clone() override; };`（此时 `D` 尚不完整），却不允许返回一个与 `D` 无关的不完整类的指针？

<details markdown="1">
<summary>答案</summary>

协变返回要把返回的指针转换成基类的返回类型，编译器必须知道基类在返回类型中的偏移，以及这个转换是否可访问、无二义。vtable 是否需要新槽、是否需要返回值调整 thunk，也要在这时决定。

对一个与 `D` 无关的不完整类，这些信息在覆盖声明处还不存在。`D` 自己在类体里虽然不完整，但它的基类列表在 *base-clause* 处已经确定，基类子对象的偏移和可访问性都能算出来，所以标准单独允许这种情况。
</details>
