---
title: 初始化基类与成员
summary: ctor-initializer 的全部规则：mem-initializer-id 怎么查找、能指名什么；委托构造函数；未被指名的子对象如何初始化；初始化顺序只看声明顺序（虚基类最先、只由最派生类初始化）；引用成员不得绑定临时量；构造期间调用成员函数何时是 UB
status: done
papers: N1986, N2756
related: class.init, class.inhctor.init, class.cdtor, class.mem, class.dtor, except.ctor, basic.life, dcl.init, class.copy.ctor, dcl.contract.func, topics/special-members-and-elision
tags: 构造函数, 初始化顺序, 委托构造, 虚基类, UB
updated: 2026-10-17
---

构造一个类对象时，在构造函数的函数体开始执行之前，大部分工作就已经完成了：所有基类子对象和非静态数据成员都已初始化。它们怎样初始化，由构造函数定义中冒号后面的那一段 *ctor-initializer*（俗称成员初始化列表）决定；**它们按什么顺序初始化，却不由这一段决定，而由类定义本身决定**。

本节回答构造函数在进入函数体之前的所有问题：

1. *mem-initializer* 里的名字怎么查找、能指名谁（¶2–¶5）；
2. 委托构造函数（¶6、¶11）；
3. 实参怎么初始化子对象，哪些写法非良构（¶7–¶8、¶10、¶13）；
4. 没写 *mem-initializer* 的子对象怎么办（¶9、¶12）；
5. 初始化顺序（¶15–¶16），以及为什么它与列表的书写顺序无关；
6. 初始化期间能不能用 `this`、能不能调用成员函数（¶17–¶19）。

前置知识：潜在构造的子对象（potentially constructed subobject，指非静态数据成员、直接非虚基类，以及非抽象类的虚基类）的定义见 [[special]]；对象生命周期见 [[basic.life]]；初始化的形式见 [[dcl.init]]；默认成员初始化器见 [[class.mem]]。

## 语法（¶1）

¶1：在构造函数的定义中，可以用 *ctor-initializer* 为直接基类、虚基类和非静态数据成员指定初始化器：

```text
ctor-initializer:
    : mem-initializer-list
mem-initializer:
    mem-initializer-id ( expression-list(opt) )
    mem-initializer-id braced-init-list
mem-initializer-id:
    class-or-decltype
    identifier
```

几个要点：

- *ctor-initializer* 只能出现在构造函数的定义里（它是 *function-body* 的一部分，[[dcl.fct.def.general]]），不能写在声明里。
- 每个 *mem-initializer* 后面可以跟 `...`，表示包展开（¶20）。
- *mem-initializer-id* 要么是一个类名或 `decltype`（指名基类或本类），要么是一个标识符（指名成员，也可能指名基类）。

## mem-initializer-id 的查找与限制（¶2–¶5）

### 查找忽略形参作用域（¶2）

¶2：*mem-initializer-id* 中的无限定名查找**忽略构造函数的形参作用域**。正因为有这条规则，下面这种极其常见的写法才能成立：

```cpp run title="same-name-param.cpp" ok
struct P {
    int x;
    P(int x) : x(x) {}   // 括号外的 x：查找忽略形参，找到成员 P::x
                         // 括号内的 x：普通表达式，在形参作用域中，找到形参 x
};

int main() { return P(0).x; }
```

括号外和括号内用的是两套查找：*mem-initializer-id* 跳过形参；*expression-list* 是普通表达式，位于构造函数的形参作用域中（¶17 注 8），所以形参会遮蔽成员。

### 成员与基类同名（¶2 注 1）

注 1：如果类的某个成员与某个直接基类或虚基类同名，那么由单个标识符组成的 *mem-initializer-id* 指的是成员；要初始化被遮蔽的基类，得用限定名。

```cpp title="member-hides-base.cpp" error
struct Base { Base(int) {} };

struct S1 : Base {
    int Base;
    S1() : Base(1) {}       // error: Base 指的是成员 int Base；
                            //        基类 Base 没有 mem-initializer，又没有默认构造函数
};

struct S2 : ::Base {
    int Base;
    S2() : ::Base(1), Base(2) {}   // OK: ::Base 是基类，Base 是成员
};
```

### 能指名什么（¶2 末、¶3）

¶2 最后一句是一条硬性限制：*mem-initializer-id* 必须指名以下之一，否则非良构：

- 构造函数所属的类本身（即委托构造，¶6）；
- 该类的直接非静态数据成员；
- 该类的直接基类或虚基类（虚基类可以是间接的）。

成员的成员、间接非虚基类和静态成员都不能在这里初始化。

¶3：初始化基类时，可以用任何指代该基类类型的 *class-or-decltype*，typedef、别名、注入类名、`decltype` 都可以。

```cpp run title="base-alias.cpp" ok
template<class T> struct TB { TB(T) {} };

struct S3 : TB<int> {
    using Alias = TB<int>;
    S3() : Alias(1) {}                   // 通过别名
};
struct S4 : TB<int> { S4() : TB(1) {} }; // 通过基类的注入类名，不必写模板实参

struct A { A() {} };
typedef A global_A;
struct C : A { C() : global_A() {} };    // 标准例 1

int main() { S3 a; S4 b; C c; }
```

`S4` 的写法在模板代码里尤其方便：基类 `TB<int>` 的注入类名 `TB` 继承到了 `S4` 的作用域中，查找能直接找到它（[[class.pre]]）。但如果基类是依赖的（如 `template<class T> struct D : TB<T>`），无限定查找找不到注入类名，必须写全 `TB<T>`。

### 直接基类与间接虚基类的二义性（¶4）

¶4：如果 *mem-initializer-id* 同时指代一个直接非虚基类和一个间接虚基类，程序非良构：

```cpp title="ambiguous-base.cpp" error
struct A { A() {} };
struct B : virtual A {};
struct C : A, B {      // A 既是 C 的直接基类，又是（经 B 的）虚基类
    C();
};
C::C() : A() {}        // error: 哪个 A？
```

这种层次本身就会让 Clang 发出"直接基类 A 因二义性而不可访问"的警告。实践中应避免这样设计类层次。

### 同一子对象不能有两个 mem-initializer（¶5）

¶5：*ctor-initializer* 可以初始化本类的变体成员（variant member，即匿名联合体的成员或联合体本身的成员）。如果同一个成员或同一个基类有两个 *mem-initializer*，程序非良构。

```cpp title="duplicate.cpp" error
struct D {
    int x;
    D(int v) : x(v), x(1) {}   // error: x 被初始化两次
};
```

## 委托构造函数（¶6、¶11）

### 定义（¶6）

¶6：*mem-initializer-list* 可以用指代本类自身的 *class-or-decltype*，把初始化**委托**给本类的另一个构造函数。这时：

- 这个 *mem-initializer* 必须是唯一的一个，不能再初始化任何基类或成员；
- 该构造函数称为 [[g:delegating-constructor]]，被选中的那个称为**目标构造函数**（target constructor），由重载决议选出；
- 目标构造函数返回之后，再执行委托构造函数的函数体；
- 构造函数如果直接或间接委托给自己：{{ifndr}}。

```cpp title="delegating.cpp" error
struct C {
    C(int) {}                  // #1 非委托构造
    C() : C(42) {}             // #2 委托给 #1
    C(char) : C(42.0) {}       // #3 与 #4 形成循环：IFNDR
    C(double) : C('a') {}      // #4
};

struct E {
    E() : E(1), m(2) {}        // error: 委托的 mem-initializer 必须单独出现
    E(int);
    int m;
};
```

为什么必须单独出现？因为目标构造函数会完整地初始化所有基类与成员；如果委托构造函数还能再初始化成员 `m`，`m` 就会初始化两次。

为什么循环只是 IFNDR？因为目标构造函数可以定义在别的翻译单元里，编译器一般看不到整个委托链。不过，如果整个循环在同一个 TU 中可见，Clang 会报错（诊断开关是 `-Wdelegating-ctor-cycles`，默认就是错误）。

### 对象何时算初始化完成（¶11）

¶11：**一个非委托构造函数返回时，对象的初始化即视为完成**。注 5 指出了推论：对象的生命周期（[[basic.life]]）可以在所有委托构造函数完成之前就开始。

这条规则的实际影响体现在异常处理上：

- 如果非委托构造函数（或其 *ctor-initializer*）抛出异常，对象从未完成初始化，不会调用它的析构函数，只析构已经构造好的子对象（[[except.ctor#3]]）。
- 如果目标构造函数已经返回，而委托构造函数的函数体抛出异常，对象就已经完整构造过了，于是会调用对象的析构函数（[[except.ctor#4]]）。

```cpp run title="delegating-throw.cpp" ok
#include <cstdio>
#include <stdexcept>

struct Res {
    Res()  { std::puts("Res()"); }
    ~Res() { std::puts("~Res()"); }
};

struct A {
    Res r;
    A(int) { std::puts("A(int) body"); }
    A() : A(0) { std::puts("A() body, throwing"); throw std::runtime_error("x"); }
    ~A() { std::puts("~A()"); }
};

struct B {
    Res r;
    B(int) { std::puts("B(int) body, throwing"); throw 1; }
    ~B() { std::puts("~B()"); }
};

int main() {
    try { A a; } catch (...) { std::puts("caught A"); }
    // Res() / A(int) body / A() body, throwing / ~A() / ~Res() / caught A
    try { B b(1); } catch (...) { std::puts("caught B"); }
    // Res() / B(int) body, throwing / ~Res() / caught B     —— 没有 ~B()
}
```

因此，委托构造函数可以用作一种惯用法：先建立不变式，再做可能失败的工作。把资源获取放进目标构造函数，把后续可能抛出异常的步骤放进委托构造函数体，出现异常时由析构函数负责清理。

!!! note "委托与构造期间的多态行为"
    委托构造函数体执行时，对象已经构造完成（生命周期已经开始）。但 [[class.cdtor]] 的虚调用规则针对的是从构造函数中发起的调用：在委托构造函数体里调用虚函数时，构造函数所属的类就是本类，结果与在普通构造函数体里调用相同。

## 实参如何初始化子对象（¶7）

¶7：*mem-initializer* 中的 *expression-list* 或 *braced-init-list* 按 [[dcl.init]] 的直接初始化规则初始化所指名的子对象（委托时则是整个对象）。

```cpp run title="direct-init.cpp" ok
struct B1 { B1(int) {} };
struct B2 { B2(int) {} };
struct D : B1, B2 {
    D(int);
    B1 b;
    const int c;
};

D::D(int a) : B2(a + 1), B1(a + 2), c(a + 3), b(a + 4) {}
// 实际初始化顺序：B1(a+2), B2(a+1), b(a+4), c(a+3)——见 ¶15

int main() { D d(10); (void)d; }
```

由于是直接初始化，`explicit` 构造函数也可以被选中；`m{...}` 形式则是直接列表初始化，禁止窄化。

注 2：每个 *mem-initializer* 执行的初始化构成一个完整表达式（[[intro.execution]]）。这意味着 *mem-initializer* 中创建的临时对象在该初始化完成时就销毁，而不是等到构造函数结束。

### 虚基类的 mem-initializer 只在最派生类中生效（¶7 末）

¶7 最后一句规定：**执行非最派生类的构造函数时，指名虚基类的 *mem-initializer* 会被忽略**，其中的实参表达式也不求值：

```cpp run title="vbase-ignored.cpp" ok
#include <cstdio>

int g() { std::puts("g() called"); return 1; }

struct V { V(int i = 0) { std::printf("V(%d)\n", i); } };
struct A : virtual V { A() : V(g()) { std::puts("A()"); } };
struct B : A {};

int main() {
    std::puts("A a:"); A a;   // g() called / V(1) / A()
    std::puts("B b:"); B b;   // V(0) / A()        —— g() 没有被调用
}
```

原因很简单：虚基类子对象在整个对象中只有一份，多条继承路径上的多个中间类却都可能试图初始化它。标准的选择是只采用最派生类的初始化器（¶15.1），中间类的一律作废。对应的 ABI 实现见下文的实现视角一节。

## 引用成员不能绑定临时量（¶8、¶13）

¶8：在 *mem-initializer* 中把临时量绑定到引用成员，是非良构的。

```cpp title="ref-member-temp.cpp" error
struct A {
    A() : v(42) {}   // error: 42 物化出的临时 int 会在完整表达式结束时销毁
    const int& v;
};
```

在 C++11/14 的规则下，这样绑定的临时量会一直存活到构造函数退出，构造函数一返回 `v` 就悬垂了，没有任何合法用途。所以后来干脆规定为非良构（[[class.temporary]] 列出了生命周期延长的各种例外，这一条从例外变成了错误）。

¶13：同理，在默认成员初始化器中把临时量绑定到引用成员也是非良构的，但要到使用该默认成员初始化器时才出错：

```cpp title="ref-member-dmi.cpp" error
struct A {
    A() = default;         // OK（声明本身没问题）
    A(int v) : v(v) {}     // OK：绑定到形参 v，不是临时量
    const int& v = 42;     // OK（声明本身没问题）
};

A a1;      // error: 预置的默认构造函数使用了默认成员初始化器，把 42 的临时量绑定到 v
A a2(1);   // OK，"不幸地"——v 绑定到形参，构造函数返回后悬垂
```

标准例子在 `a2` 处的注释是意味深长的 "OK, unfortunately"：它良构，但构造函数一返回，`a2.v` 就悬垂了。规则只能拦住绑定到临时量这一种可以静态判定的情形；绑定到形参、局部变量这类同样必然悬垂的写法，只能靠编译器警告（如 Clang 的 `-Wdangling-field`）。

## 没有 mem-initializer 的子对象（¶9、¶12）

¶9：在非委托构造函数中（隐式定义的复制/移动构造函数除外，它们有自己的规则，见 [[class.copy.ctor]]），如果一个潜在构造的子对象没有被任何 *mem-initializer-id* 指名（包括构造函数根本没有 *ctor-initializer* 的情形），那么：

- ¶9.1 如果它是有默认成员初始化器的非静态数据成员，并且
    - ¶9.1.1 构造函数所属的类是联合体，且该联合体的其他变体成员都没有被 *mem-initializer* 指名；或
    - ¶9.1.2 构造函数所属的类不是联合体，且（如果该成员属于匿名联合体）该匿名联合体的其他成员都没有被指名，

    那么用默认成员初始化器初始化它；
- ¶9.2 否则，如果它是匿名联合体或变体成员，就不初始化；
- ¶9.3 否则，默认初始化它。

标准例 6：

```cpp title="unmentioned.cpp" error
struct A { A(); };
struct B { B(int); };

struct C {
    C() {}          // 按如下方式初始化成员：
    A a;            // OK：调用 A::A()
    const B b;      // error: B 没有默认构造函数
    int i;          // OK：i 的值是不确定的或错误的（[basic.indet]）
    int j = 5;      // OK：j 的值为 5（默认成员初始化器）
};
```

注 3：抽象类永远不是最派生类，所以它的构造函数永远不会初始化虚基类，即使虚基类没有默认构造函数，相应的 *mem-initializer* 也可以省略。

```cpp run title="abstract-vbase.cpp" ok
struct V { V(int) {} };                         // 没有默认构造函数
struct Abs : virtual V {
    Abs() {}                                     // OK：Abs 是抽象类，不负责初始化 V
    virtual void f() = 0;
};
struct Impl : Abs {
    Impl() : V(1) {}                             // 最派生类必须初始化 V
    void f() override {}
};

int main() { Impl i; }
```

注 4：对于自动或动态存储期的对象，如果构造函数调用完成后（且这次调用不是值初始化的一部分），某个成员既没有初始化，也没有在构造函数体中赋值，它的值就是不确定的或错误的（erroneous，{{c++26}}，[[basic.indet]]）。在 C++23 及之前，这样的值一律是不确定值，读取它是 UB；在 C++26 中，对自动存储期对象而言，读取它通常是错误行为（erroneous behavior），而不是 UB。

### 默认成员初始化器被覆盖（¶12）

¶12：如果一个非静态数据成员同时有默认成员初始化器和 *mem-initializer*，就执行后者，忽略默认成员初始化器，其中的副作用也不会发生：

```cpp run title="dmi-ignored.cpp" ok
#include <cstdio>

int side_effect() { std::puts("side effect!"); return 1; }

struct A {
    int i = side_effect();
    A() {}                // 使用默认成员初始化器：打印 side effect!
    A(int arg) : i(arg) {}// 不求值默认成员初始化器：不打印
};

int main() {
    A a1;      // side effect!
    A a2(5);   // （无输出）
    return a2.i;
}
```

这正是默认成员初始化器（C++11，[[N2756]]）的设计意图：为大多数构造函数都会用到的值提供一个默认值，个别构造函数可以覆盖它，不必在每个构造函数里重复。

### 联合体只能初始化一个成员（¶10）

¶10：试图初始化联合体的多个非静态数据成员是非良构的。这一条同时约束 *mem-initializer* 与默认成员初始化器（[[class.union.anon]] 另外规定，匿名联合体至多一个成员有默认成员初始化器）。

```cpp title="union-two.cpp" error
union U {
    int a;
    float b;
    U() : a(1), b(2) {}   // error: 初始化了联合体的两个成员
};
```

## 子对象的析构函数被潜在调用（¶14）

¶14：在非委托构造函数中，每个类类型的潜在构造子对象的析构函数都是**潜在调用**的（potentially invoked，[[class.dtor]]）。注 6 给出了理由：如果构造中途抛出异常，需要析构那些已经构造完成的子对象（[[except.ctor]]）。

潜在调用意味着析构函数必须可访问且未被删除，否则构造函数非良构，即使构造函数本身声明为 `noexcept`，即使实际上不可能抛出异常。

```cpp title="dtor-potentially-invoked.cpp" error
struct NoDtor { ~NoDtor() = delete; };

struct H {
    NoDtor n;
    H() {}            // error: 构造函数潜在调用 NoDtor::~NoDtor()，它被删除了
};
```

委托构造函数不受这一条约束，因为它不直接初始化任何子对象，析构由目标构造函数负责。但 [[except.ctor#4]] 要求委托构造函数体抛出异常时调用整个对象的析构函数，所以在那里本类的析构函数同样必须可用。

## 初始化顺序（¶15–¶16）

¶15：在非委托构造函数中，初始化按以下顺序进行：

1. ¶15.1 **虚基类**，只在最派生类（[[intro.object]]）的构造函数中初始化，顺序是它们在基类有向无环图的深度优先、从左到右遍历中出现的顺序，其中从左到右指基类在 *base-specifier-list* 中的出现顺序；
2. ¶15.2 **直接基类**，按 *base-specifier-list* 中的声明顺序（与 mem-initializer 的书写顺序无关）；
3. ¶15.3 **非静态数据成员**，按它们在类定义中的声明顺序（同样与 mem-initializer 的顺序无关）；
4. ¶15.4 最后执行构造函数的函数体（*compound-statement*）。

注 7 说明了动机：**强制采用声明顺序，是为了保证基类与成员子对象按初始化的逆序析构**。析构函数只有一个，构造函数却可以有很多个。如果初始化顺序随每个构造函数的 *mem-initializer* 列表而定，不同构造函数构造出的对象就需要不同的析构顺序，而析构函数无从得知对象是由哪个构造函数构造的（除非为每个对象额外存储信息）。采用类定义中唯一的声明顺序，这个问题就彻底解决了。

```cpp run title="init-order.cpp" ok
#include <cstdio>

struct V { V(const char* s = "default") { std::printf("V(%s)\n", s); } };
struct M { M(const char* s) { std::printf("M(%s)\n", s); } };
struct A : virtual V { A() : V("from A") { std::puts("A"); } };
struct B : virtual V { B() : V("from B") { std::puts("B"); } };

struct C : A, B {
    M m1, m2;
    C() : m2("m2"), m1("m1"), B(), A() { std::puts("C body"); }   // 书写顺序被无视
};
struct D : A, B {
    D() : V("from D") { std::puts("D body"); }   // 最派生类初始化虚基类
};

int main() {
    C c;   // V(default) A B M(m1) M(m2) C body
    D d;   // V(from D) A B D body
}
```

`C` 的输出说明了两件事。其一，`A`、`B` 构造函数里的 `V("from A")`、`V("from B")` 都被忽略了（¶7），而 `C` 自己也没有为 `V` 写 *mem-initializer*，于是 `V` 按 ¶9.3 默认初始化。其二，`m2`、`m1`、`B`、`A` 的书写顺序完全不起作用。Clang 对此给出 `-Wreorder-ctor` 警告（GCC 中称为 `-Wreorder`，两者都包含在 `-Wall` 中），并附带按真实顺序重排的修复建议。

### 顺序不一致的真实危害

只要 *mem-initializer* 之间没有依赖，书写顺序与声明顺序不一致就只是风格问题。危险来自依赖：

```cpp run title="reorder-bug.cpp" ub
struct S {
    int a, b;
    S(int x) : b(x), a(b + 1) {}   // 看上去先 b 后 a；实际先初始化 a，此时 b 尚未初始化
};

int main() {
    S s(1);
    return s.a;   // UB（C++23 及之前，读不确定值）；C++26 中按 [basic.indet] 是错误行为
}
```

Clang 对这段代码会同时给出 `-Wreorder-ctor` 和 `-Wuninitialized` 两条警告。修复方法是让声明顺序与依赖关系一致，或者干脆不让成员初始化器互相依赖（例如都从形参计算）。

### 虚基类的顺序（¶16）

¶16：标准例 9（这里加上了输出，便于观察）：

```cpp run title="vbase-order.cpp" ok
#include <cstdio>

struct V {
    V()      { std::puts("V()"); }
    V(int i) { std::printf("V(%d)\n", i); }
};
struct A : virtual V { A() {} A(int i) : V(i) {} };
struct B : virtual V { B() {} B(int) {} };
struct C : A, B, virtual V { C() {} C(int) {} };

int main() {
    V v(1);   // V(1)
    A a(2);   // V(2)：A 是最派生类，它的 mem-initializer 生效
    B b(3);   // V()：B(int) 没有为 V 写 mem-initializer
    C c(4);   // V()：C 是最派生类，C(int) 没有为 V 写 mem-initializer；A、B 的意见被忽略
}
```

有多个虚基类时，深度优先、从左到右的遍历保证所有派生类都采用同一个顺序。例如在 `struct X : virtual P, Q {}; struct Q : virtual R {};` 中，对 `X` 的遍历先到 `P`，再进入 `Q` 找到 `R`，所以虚基类的初始化顺序是 `P`、`R`，然后才是非虚直接基类 `Q`。

## `this` 与初始化器中的名字（¶17）

¶17（注 8）：*mem-initializer* 的 *expression-list* / *braced-init-list* 位于构造函数的形参作用域中，可以用 `this` 指代正在初始化的对象。

```cpp run title="this-in-init.cpp" ok
class X {
    int a;
    int b;
    int i;
    int j;
public:
    const int& r;
    X(int i) : r(a), b(i), i(i), j(this->i) {}
    // r 绑定到 X::a（只是取引用，不读值，即使 a 尚未初始化也没问题）
    // b 用形参 i 初始化；i 用形参 i 初始化（括号外是成员，括号内是形参）
    // j 用成员 X::i 的值初始化——必须写 this->i，因为 i 被形参遮蔽了
};

int main() { X x(3); (void)x; }   // 注意：a 从未被初始化，读 x.r 会读到不确定/错误值
```

（Clang 会对这个标准例子给出 `-Wreorder-ctor` 警告：`r` 最后声明却写在最前。这里无害，因为各初始化器之间唯一的依赖 `j(this->i)` 恰好符合声明顺序。）

注意，`j(this->i)` 之所以良构，是因为成员 `i` 在 `j` 之前声明，因此先于 `j` 初始化。如果把 `j` 的声明移到 `i` 前面，`this->i` 读取的就是尚未初始化的值。

`r(a)` 的绑定合法，是因为它只需要 `a` 的地址，不需要 `a` 的值；按 [[class.cdtor#3]]，形成指向直接成员的指针，只要求包含它的对象已经开始构造。

## 构造期间调用成员函数（¶18–¶19）

¶18：可以对正在构造或析构的对象调用成员函数（包括虚函数），正在构造/析构的对象也可以作为 `typeid` 或 `dynamic_cast` 的操作数。但是，如果这些操作在以下时刻进行，行为未定义：

- ¶18.1 在 *ctor-initializer* 的求值过程中（或在它直接、间接调用的函数中），所有基类的 mem-initializer 完成之前；
- ¶18.2 在构造函数的前置条件断言求值时 {{c++26}}；
- ¶18.3 在析构函数的后置条件断言求值时 {{c++26}}（[[dcl.contract.func]]）。

```cpp run title="call-before-bases.cpp" ub
struct A { A(int) {} };

class B : public A {
    int j;
public:
    int f() { return 0; }
    B() : A(f()),   // UB: 调用成员函数时基类 A 尚未初始化
          j(f()) {} // OK：此时所有基类都已初始化
};

class C { public: C(int) {} };

class D : public B, C {
    int i;
public:
    D() : C(f()),   // UB: 调用成员函数时基类 C 尚未初始化（B 已经构造好也不行）
          i(f()) {} // OK
};

int main() { D d; }
```

为什么以所有基类初始化完成为界？因为成员函数可以访问基类的成员，也可以经由基类调用虚函数；在基类构造之前，基类子对象的状态（包括 vptr）都还没有建立。一旦所有基类构造完成，对象的基类部分就都可用了，剩下尚未初始化的只是本类的数据成员，访问它们得到不确定值，那是另一个层面的问题。

¶18.2/¶18.3 是 C++26 引入契约（[[dcl.contract.func]]）后添加的：构造函数的前置条件在任何子对象初始化之前求值，析构函数的后置条件在所有子对象析构之后求值，这两个时刻对象完全不可用。截至写作时，Clang 尚未实现契约语法。

¶19（注 9）：构造期间的虚函数调用、`typeid`、`dynamic_cast` 在良定义情形下的结果由 [[class.cdtor]] 规定（按当前正在构造的类分派）。

## 包展开（¶20）

¶20：后跟省略号的 *mem-initializer* 是一个包展开（[[temp.variadic]]），它初始化 *base-specifier-list* 中由包展开指定的基类：

```cpp run title="mixins.cpp" ok
#include <cstdio>

template<class... Mixins>
class X : public Mixins... {
public:
    X(const Mixins&... mixins) : Mixins(mixins)... {}
};

struct Loud  { Loud() = default; Loud(const Loud&) { std::puts("Loud copied"); } };
struct Quiet {};

int main() {
    X<Loud, Quiet> x(Loud{}, Quiet{});   // Loud copied
}
```

这是 mixin / 策略类组合的标准写法，也是 `std::tuple`、`std::variant` 等库实现的常用技巧。

## 实现视角

!!! impl "Itanium C++ ABI：完整对象构造函数与基类子对象构造函数"
    为了实现虚基类只由最派生类初始化（¶7、¶15.1），Itanium ABI（GCC、Clang 在 Linux/macOS 上使用）为每个构造函数生成两个变体：

    - **完整对象构造函数**（complete object constructor，修饰名中为 `C1`）：用于构造完整对象，会初始化虚基类；
    - **基类子对象构造函数**（base object constructor，`C2`）：派生类构造函数调用基类构造函数时使用，跳过虚基类的初始化。

    对没有虚基类的类，两个变体完全相同，编译器通常让它们共用一份代码（别名）。析构函数同理有 `D1`/`D2`（另有 deleting destructor `D0`）。

    有虚基类时，基类子对象构造函数还需要知道在当前的最派生类里自己的虚基类位于何处、构造期间该用哪张虚表，这些信息通过 VTT（virtual table table）作为隐藏参数传入。

    MSVC 采用不同的方案：带虚基类的类的构造函数接收一个隐藏的整数参数，表示是否为最派生类，由它决定是否初始化虚基类。

!!! impl "诊断"
    - `-Wreorder-ctor`（Clang）/ `-Wreorder`（GCC）：*mem-initializer* 书写顺序与真实顺序不一致。
    - `-Wuninitialized`：在成员初始化器中读取尚未初始化的成员（Clang 能发现简单情形）。
    - `-Wdangling-field`（Clang）：引用或指针成员绑定到构造函数形参等即将销毁的对象。
    - 委托循环：Clang 在同一 TU 内可见时直接报错。

## 历史与演进

!!! history "历史与演进"
    - **C++98**：已有 *ctor-initializer*、按声明顺序初始化、虚基类只由最派生类初始化等规则。*mem-initializer* 中绑定到引用成员的临时量存活到构造函数退出。
    - **C++11**：
        - 委托构造函数（[[N1986]]）；
        - 非静态数据成员的默认成员初始化器（[[N2756]]），以及 ¶12 中被 mem-initializer 覆盖的规则；
        - *mem-initializer* 可以使用 *braced-init-list*、可以是包展开。
    - **C++14/17**：引用成员绑定临时量的规则经核心语言 issue 收紧：*mem-initializer* 中的绑定与默认成员初始化器中的绑定都改为非良构（¶8、¶13）。
    - **C++20**：未被初始化的成员读取规则与对象模型一同重写（[[basic.indet]]）。
    - **C++26**：¶18 增加了在构造函数前置条件、析构函数后置条件中调用成员函数为 UB 的条目（契约，[[dcl.contract.func]]）；注 4 中的不确定值扩展为不确定值或错误值（erroneous behavior，[[basic.indet]]）。

## 陷阱

!!! pitfall "以为 mem-initializer 的书写顺序就是初始化顺序"
    初始化顺序只由类定义决定：虚基类 → 直接基类（声明顺序）→ 成员（声明顺序）→ 函数体。打开 `-Wall`，让编译器帮你检查。

!!! pitfall "在中间类里初始化虚基类，以为它会生效"
    构造派生类对象时，中间类中针对虚基类的 *mem-initializer* 会被忽略，实参也不求值。如果虚基类没有默认构造函数，每个最派生类都要为它提供 *mem-initializer*。

!!! pitfall "在委托构造函数里顺便初始化一个成员"
    委托的 *mem-initializer* 必须单独出现。如果想在委托之后修改某个成员，只能在委托构造函数体里赋值。

!!! pitfall "引用成员绑定到形参会悬垂"
    `struct S { const std::string& s; S(const std::string& x) : s(x) {} }; S obj("hi");` 是良构的，但由 `"hi"` 物化出的临时 `std::string` 在 `obj` 的初始化结束时就销毁了，`obj.s` 随之悬垂。¶8 只禁止在 *mem-initializer* 中直接把临时量绑定到引用成员。

!!! pitfall "在基类 mem-initializer 中调用本类成员函数"
    在 `D() : Base(compute()) {}` 中，如果 `compute` 是 `D` 的非静态成员函数，就属于 ¶18.1 的 UB。应改用静态成员函数或自由函数。

## 思考题

!!! question "思考题 1"
    下面的输出是什么？

    ```cpp
    #include <cstdio>
    struct P { P(const char* s) { std::puts(s); } };
    struct Q { Q(const char* s) { std::puts(s); } };
    struct V { V(const char* s = "V()") { std::puts(s); } };
    struct L : virtual V { P p{"L::p"}; L() : V("V from L") { std::puts("L"); } };
    struct R : virtual V { R() { std::puts("R"); } };
    struct X : R, L {
        Q q;
        X() : L(), q("X::q"), V("V from X") { std::puts("X"); }
    };
    int main() { X x; }
    ```

<details markdown="1">
<summary>答案</summary>

```text
V from X
R
L::p
L
X::q
X
```

`X` 是最派生类，所以先初始化虚基类 `V`，使用的是 `X` 自己的 *mem-initializer*（`L` 里的 `V("V from L")` 被忽略）。然后按 *base-specifier-list* 的顺序，先 `R` 再 `L`（尽管 *mem-initializer* 里只写了 `L()`）；构造 `L` 时，先用默认成员初始化器初始化成员 `p`，再执行函数体。最后是 `X` 的成员 `q` 和 `X` 的函数体。
</details>

!!! question "思考题 2"
    `struct S { S() : S(0) {} S(int) noexcept(false); ~S() = delete; };` 良构吗？`S(int)` 定义为 `S::S(int) {}` 呢？

<details markdown="1">
<summary>答案</summary>

`S(int)` 是非委托构造函数：`S` 没有类类型的子对象，¶14 不涉及 `S` 自己的析构函数，所以 `S::S(int) {}` 本身良构。

`S()` 是委托构造函数，而 ¶14 明确只适用于非委托构造函数。但 [[except.ctor#4]] 规定，委托构造函数的函数体因异常退出时，要调用对象的析构函数，而这个析构函数被删除了。[[class.dtor]] 列举潜在调用的情形时只点名了 [[expr.new]]、[[stmt.return]]、[[dcl.init.aggr]]、[[class.base.init]]、[[except.throw]]，没有单独提到委托构造函数；不过 "is invoked" 本身就涵盖了实际可能发生的调用。实践中 Clang 拒绝 `S()` 的定义（报告使用了被删除的函数），这也是合理的理解：委托构造函数需要可用的析构函数。这里的措辞是一个值得 language lawyer 留意的灰色地带。
</details>

!!! question "思考题 3"
    下面的 `j(this->i)` 与标准例 10 有什么不同？是否有问题？

    ```cpp
    class X {
        int j;
        int i;
    public:
        X(int i) : i(i), j(this->i) {}
    };
    ```

<details markdown="1">
<summary>答案</summary>

`j` 在 `i` 之前声明，所以先初始化 `j`，此时 `this->i` 尚未初始化。读取它在 C++23 及之前是 UB（对不确定值做左值到右值转换）；在 C++26 中，对自动存储期的对象一般是错误行为（读到错误值），对静态存储期对象则读到零初始化得到的 0。无论哪种情况，都不是程序员想要的结果。*mem-initializer* 的书写顺序（先 `i` 后 `j`）改变不了这一点，`-Wreorder-ctor` 会给出提醒。
</details>

## 小结

| 规则 | 段落 |
|---|---|
| *mem-initializer-id* 查找忽略形参；同名时成员优先于基类 | ¶2 |
| 只能指名本类、直接成员、直接基类或虚基类；可用任何别名或 `decltype` | ¶2–¶3 |
| 同一子对象两个初始化器、联合体两个成员：非良构 | ¶5、¶10 |
| 委托构造：唯一的 *mem-initializer*；循环为 IFNDR；目标构造函数返回即初始化完成 | ¶6、¶11 |
| 直接初始化；每个 *mem-initializer* 是一个完整表达式 | ¶7 |
| 虚基类的 *mem-initializer* 在非最派生类中被忽略（实参不求值） | ¶7 |
| 引用成员绑定临时量：*mem-initializer* 中或默认成员初始化器中都非良构 | ¶8、¶13 |
| 未指名：默认成员初始化器 → 变体成员不初始化 → 默认初始化 | ¶9 |
| 默认成员初始化器被 *mem-initializer* 覆盖，副作用不发生 | ¶12 |
| 非委托构造函数潜在调用所有子对象的析构函数 | ¶14 |
| 顺序：虚基类（仅最派生类，DFS 左到右）→ 直接基类 → 成员 → 函数体 | ¶15 |
| 所有基类初始化完成前调用成员函数 / `typeid` / `dynamic_cast`：UB | ¶18 |
