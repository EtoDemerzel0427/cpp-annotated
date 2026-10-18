---
title: 初始化基类与成员
summary: ctor-initializer 的全部规则：mem-initializer-id 怎么查找、能指名什么；委托构造函数；未被指名的子对象如何初始化；初始化顺序只看声明顺序（虚基类最先、只由最派生类初始化）；引用成员不得绑定临时量；构造期间调用成员函数何时是 UB
status: done
papers: N1986, N2756
related: class.init, class.inhctor.init, class.cdtor, class.mem, class.dtor, except.ctor, basic.life, dcl.init, class.copy.ctor, dcl.contract.func, topics/special-members-and-elision
tags: 构造函数, 初始化顺序, 委托构造, 虚基类, UB
updated: 2026-10-17
---

一个类对象的构造，在构造函数**函数体**开始执行之前，就已经完成了大部分工作：所有基类子对象和非静态数据成员都已经被初始化。决定它们**怎么**初始化的，是构造函数定义里冒号后面那一段 *ctor-initializer*（俗称"成员初始化列表"）；决定它们**以什么顺序**初始化的，却**不是**这一段——而是类定义本身。

本节回答构造函数的所有"前半场"问题：

1. *mem-initializer* 里的名字怎么查找、能指名谁（¶2–¶5）；
2. 委托构造函数（¶6、¶11）；
3. 实参怎么初始化子对象，哪些写法非良构（¶7–¶8、¶10、¶13）；
4. 没写 *mem-initializer* 的子对象怎么办（¶9、¶12）；
5. 初始化顺序（¶15–¶16），以及为什么它与列表的书写顺序无关；
6. 初始化期间能不能用 `this`、能不能调用成员函数（¶17–¶19）。

前置知识：**潜在构造的子对象**（potentially constructed subobject：非静态数据成员、直接非虚基类，以及非抽象类的虚基类）的定义见 [[special]]；对象生命周期见 [[basic.life]]；初始化的形式见 [[dcl.init]]；默认成员初始化器见 [[class.mem]]。

## 语法（¶1）

¶1 在构造函数的**定义**中，可以用 *ctor-initializer* 为直接基类、虚基类和非静态数据成员指定初始化器：

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

- *ctor-initializer* 只能出现在构造函数**定义**里（它是 *function-body* 的一部分，[[dcl.fct.def.general]]），声明里不能写。
- 每个 *mem-initializer* 后面可以跟 `...`，表示包展开（¶20）。
- *mem-initializer-id* 要么是一个类名或 `decltype`（指名基类或本类），要么是一个标识符（指名成员，也可能指名基类）。

## mem-initializer-id 的查找与限制（¶2–¶5）

### 查找忽略形参作用域（¶2）

¶2 *mem-initializer-id* 中的无限定名查找**忽略构造函数的形参作用域**。这条规则让下面这个极其常见的写法成立：

```cpp run title="same-name-param.cpp" ok
struct P {
    int x;
    P(int x) : x(x) {}   // 括号外的 x：查找忽略形参，找到成员 P::x
                         // 括号内的 x：普通表达式，在形参作用域中，找到形参 x
};

int main() { return P(0).x; }
```

括号外和括号内用的是**两套**查找：*mem-initializer-id* 跳过形参；*expression-list* 是普通表达式，处在构造函数的形参作用域中（¶17 注 8），所以形参会遮蔽成员。

### 成员与基类同名（¶2 注 1）

注 1：如果类有一个成员与某个直接或虚基类同名，那么由单个标识符组成的 *mem-initializer-id* 指的是**成员**；要初始化被遮蔽的基类，得用限定名。

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

¶2 最后一句是硬性限制：*mem-initializer-id* 必须指名以下之一，否则非良构：

- 构造函数所属的类本身（→ 委托构造，¶6）；
- 该类的**直接**非静态数据成员；
- 该类的**直接基类**或**虚基类**（虚基类可以是间接的）。

不能初始化"成员的成员"、"间接非虚基类"或静态成员。

¶3 初始化基类时，可以用**任何**指代该基类类型的 *class-or-decltype*：typedef、别名、注入类名、`decltype`，都行。

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

`S4` 的写法在模板代码里尤其方便：基类 `TB<int>` 的注入类名 `TB` 被继承到 `S4` 的作用域中，查找能直接找到它（[[class.pre]]）。但如果基类是**依赖**的（如 `template<class T> struct D : TB<T>`），注入类名不会被无限定查找找到，必须写全 `TB<T>`。

### 直接基类与间接虚基类的二义性（¶4）

¶4 如果 *mem-initializer-id* 同时指代一个**直接非虚基类**和一个**间接虚基类**，非良构：

```cpp title="ambiguous-base.cpp" error
struct A { A() {} };
struct B : virtual A {};
struct C : A, B {      // A 既是 C 的直接基类，又是（经 B 的）虚基类
    C();
};
C::C() : A() {}        // error: 哪个 A？
```

这种层次本身就会让 Clang 发出"直接基类 A 因二义性而不可访问"的警告。实践中避免这样设计类层次。

### 同一子对象不能有两个 mem-initializer（¶5）

¶5 *ctor-initializer* 可以初始化本类的**变体成员**（variant member，即匿名联合体成员或联合体本身的成员）。同一个成员或同一个基类出现两个 *mem-initializer*，非良构。

```cpp title="duplicate.cpp" error
struct D {
    int x;
    D(int v) : x(v), x(1) {}   // error: x 被初始化两次
};
```

## 委托构造函数（¶6、¶11）

### 定义（¶6）

¶6 *mem-initializer-list* 可以用指代**本类自身**的 *class-or-decltype* 把初始化**委托**给本类的另一个构造函数。这时：

- 这个 *mem-initializer* 必须是**唯一**的一个——不能再初始化任何基类或成员；
- 该构造函数称为 [[g:delegating-constructor]]，被选中的那个称为**目标构造函数**（target constructor），由重载决议选出；
- 目标构造函数**返回之后**，再执行委托构造函数的函数体；
- 构造函数直接或间接委托给自己：{{ifndr}}。

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

为什么必须单独出现？因为目标构造函数会**完整地**初始化所有基类与成员；如果委托构造函数还能再初始化成员 `m`，`m` 就会被初始化两次。

为什么循环只是 IFNDR？因为目标构造函数可以定义在别的翻译单元里，编译器一般无法看到整个委托链。不过，当整个循环在同一个 TU 中可见时，Clang 会报错（诊断开关是 `-Wdelegating-ctor-cycles`，默认即为错误）。

### 对象何时"初始化完成"（¶11）

¶11 对象的初始化在**一个非委托构造函数返回时**视为完成。注 5 点出推论：对象的生命周期（[[basic.life]]）可以在所有委托构造函数完成**之前**就开始。

这条规则的实际后果在异常处理：

- 若**非委托**构造函数（或其 *ctor-initializer*）抛出异常，对象从未完成初始化，**不会**调用它的析构函数——只析构已经构造好的子对象（[[except.ctor#3]]）。
- 若目标构造函数已经返回、而**委托**构造函数的**函数体**抛出异常，对象已经完整构造过了，于是会调用对象的**析构函数**（[[except.ctor#4]]）。

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

这让委托构造函数成为一种"先建立不变式、再做可能失败的工作"的惯用法：把资源获取放进目标构造函数，后续可能抛出的步骤放进委托构造函数体，异常时析构函数会负责清理。

!!! note "委托与构造期间的多态行为"
    委托构造函数体执行时，对象已经"构造完成"（生命周期已开始）。但 [[class.cdtor]] 的虚调用规则说的是"从构造函数中调用"：在委托构造函数体里调用虚函数，"构造函数所属的类"就是本类，结果与在普通构造函数体里调用相同。

## 实参如何初始化子对象（¶7）

¶7 *mem-initializer* 中的 *expression-list* 或 *braced-init-list* 按 [[dcl.init]] 的**直接初始化**规则初始化所指名的子对象（委托时则是整个对象）。

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

因为是直接初始化，`explicit` 构造函数可以被选中；`m{...}` 形式则是直接列表初始化，禁止窄化。

注 2：每个 *mem-initializer* 执行的初始化构成一个**完整表达式**（[[intro.execution]]）。这意味着 *mem-initializer* 中创建的临时对象在该初始化完成时就被销毁，而不是等到构造函数结束。

### 虚基类的 mem-initializer 只在最派生类中生效（¶7 末）

¶7 最后一句：指名**虚基类**的 *mem-initializer*，在执行**非最派生类**的构造函数时被**忽略**。连同其中的实参表达式也不会求值：

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

原因很简单：虚基类子对象在整个对象中只有一份，却可能被多条继承路径上的多个中间类"想要"初始化。标准的选择是：**只听最派生类的**（¶15.1），中间类的意见一律作废。对应的 ABI 实现见下文"实现视角"。

## 引用成员不能绑定临时量（¶8、¶13）

¶8 在 *mem-initializer* 中把临时量绑定到引用成员，**非良构**。

```cpp title="ref-member-temp.cpp" error
struct A {
    A() : v(42) {}   // error: 42 物化出的临时 int 会在完整表达式结束时销毁
    const int& v;
};
```

在 C++11/14 的规则下，这种绑定是"临时量一直存活到构造函数退出"——构造函数一返回 `v` 就悬垂了，没有任何合法用途。所以后来干脆规定为非良构（[[class.temporary]] 列出了生命周期延长的各种例外，这一条从"例外"升级成了"错误"）。

¶13 同理，**默认成员初始化器**把临时量绑定到引用成员也是非良构的——但它是在**使用**该默认成员初始化器时才出错：

```cpp title="ref-member-dmi.cpp" error
struct A {
    A() = default;         // OK（声明本身没问题）
    A(int v) : v(v) {}     // OK：绑定到形参 v，不是临时量
    const int& v = 42;     // OK（声明本身没问题）
};

A a1;      // error: 预置的默认构造函数使用了默认成员初始化器，把 42 的临时量绑定到 v
A a2(1);   // OK，"不幸地"——v 绑定到形参，构造函数返回后悬垂
```

`a2` 是标准例子里一句意味深长的"OK, unfortunately"：它良构，但 `a2.v` 一出构造函数就悬垂。规则只能拦住"绑定到临时量"这一种可以静态判定的情形；绑定到形参、局部变量这类同样必然悬垂的写法，只能靠编译器警告（如 Clang 的 `-Wdangling-field`）。

## 没有 mem-initializer 的子对象（¶9、¶12）

¶9 在**非委托**构造函数中（隐式定义的复制/移动构造函数除外，它们有自己的规则，见 [[class.copy.ctor]]），一个潜在构造的子对象如果没有被任何 *mem-initializer-id* 指名（包括构造函数根本没有 *ctor-initializer* 的情形），则：

- ¶9.1 若它是有**默认成员初始化器**的非静态数据成员，并且
    - ¶9.1.1 构造函数所属的类是联合体，且该联合体的其他变体成员都没有被 *mem-initializer* 指名；或
    - ¶9.1.2 构造函数所属的类不是联合体，且（若该成员属于匿名联合体）该匿名联合体的其他成员都没有被指名，

    那么用默认成员初始化器初始化它；
- ¶9.2 否则，若它是匿名联合体或变体成员，**不进行初始化**；
- ¶9.3 否则，**默认初始化**它。

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

注 3：抽象类永远不是最派生类，所以它的构造函数永远不会初始化虚基类，相应的 *mem-initializer* 可以省略——即使虚基类没有默认构造函数。

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

注 4：对自动或动态存储期的对象，构造函数调用完成后（且不是作为值初始化的一部分调用的），如果某成员既没有被初始化、也没有在构造函数体中被赋值，它的值是不确定的或**错误的**（erroneous，{{c++26}}，[[basic.indet]]）。C++23 及之前，这样的值一律是"不确定值"，读取它是 UB；C++26 中对自动存储期对象而言，读取通常是错误行为（erroneous behavior）而非 UB。

### 默认成员初始化器被覆盖（¶12）

¶12 若一个非静态数据成员**同时**有默认成员初始化器和 *mem-initializer*，执行后者，默认成员初始化器被**忽略**——连同其中的副作用：

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

这正是默认成员初始化器（C++11，[[N2756]]）的设计意图：为"大多数构造函数都会用到的值"提供一个默认，个别构造函数可以覆盖，不必在每个构造函数里重复。

### 联合体只能初始化一个成员（¶10）

¶10 试图初始化联合体的多于一个非静态数据成员，非良构。这同时约束 *mem-initializer* 与默认成员初始化器（[[class.union.anon]] 另规定匿名联合体至多一个成员有默认成员初始化器）。

```cpp title="union-two.cpp" error
union U {
    int a;
    float b;
    U() : a(1), b(2) {}   // error: 初始化了联合体的两个成员
};
```

## 子对象的析构函数被潜在调用（¶14）

¶14 在**非委托**构造函数中，每个类类型的潜在构造子对象的析构函数都被**潜在调用**（potentially invoked，[[class.dtor]]）。注 6 给出理由：如果构造中途抛出异常，需要析构那些已经构造完成的子对象（[[except.ctor]]）。

"潜在调用"意味着：析构函数必须**可访问且未被删除**，否则构造函数非良构——即使构造函数本身声明为 `noexcept`、即使实际上不可能抛出异常。

```cpp title="dtor-potentially-invoked.cpp" error
struct NoDtor { ~NoDtor() = delete; };

struct H {
    NoDtor n;
    H() {}            // error: 构造函数潜在调用 NoDtor::~NoDtor()，它被删除了
};
```

委托构造函数不受此条约束——它不直接初始化任何子对象，析构由目标构造函数负责；但 [[except.ctor#4]] 要求委托构造函数体抛出异常时调用**整个对象**的析构函数，所以本类的析构函数在那里同样要可用。

## 初始化顺序（¶15–¶16）

¶15 在**非委托**构造函数中，初始化按以下顺序进行：

1. ¶15.1 **虚基类**——且**只在最派生类**（[[intro.object]]）的构造函数中——按"基类有向无环图的**深度优先、从左到右**遍历"中出现的顺序初始化，"从左到右"指基类在 *base-specifier-list* 中的出现顺序；
2. ¶15.2 **直接基类**，按 *base-specifier-list* 中的声明顺序（**与 mem-initializer 的书写顺序无关**）；
3. ¶15.3 **非静态数据成员**，按它们在类定义中的声明顺序（**同样与 mem-initializer 的顺序无关**）；
4. ¶15.4 最后执行构造函数的函数体（*compound-statement*）。

注 7 道出了动机：**声明顺序是强制的，是为了保证基类与成员子对象按初始化的逆序被析构**。析构函数只有一个，而构造函数可以有很多个；如果初始化顺序跟着每个构造函数的 *mem-initializer* 列表走，不同构造函数构造出的对象就需要不同的析构顺序——析构函数无从得知对象是被哪个构造函数构造的（除非为每个对象额外存储信息）。用类定义中唯一的声明顺序，就一劳永逸地解决了这个问题。

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

`C` 的输出说明了两件事：其一，`A`、`B` 构造函数里的 `V("from A")`、`V("from B")` 都被忽略了（¶7），而 `C` 自己也没有为 `V` 写 *mem-initializer*，于是 `V` 按 ¶9.3 被默认初始化；其二，`m2`、`m1`、`B`、`A` 的书写顺序完全不起作用。Clang 对此给出 `-Wreorder-ctor` 警告（GCC 中称为 `-Wreorder`，都包含在 `-Wall` 中），并贴心地给出"按真实顺序重排"的修复建议。

### 顺序不一致的真实危害

只要 *mem-initializer* 之间没有依赖，书写顺序与声明顺序不一致只是风格问题。危险在于**依赖**：

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

¶16 标准例 9（这里加上输出以便观察）：

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

当有多个虚基类时，"深度优先、从左到右"保证所有派生类都同意同一个顺序。例如 `struct X : virtual P, Q {}; struct Q : virtual R {};` 中，对 `X` 的遍历先到 `P`，再进入 `Q` 找到 `R`，所以虚基类初始化顺序是 `P`、`R`，然后才是非虚直接基类 `Q`。

## `this` 与初始化器中的名字（¶17）

¶17（注 8）*mem-initializer* 的 *expression-list* / *braced-init-list* 位于构造函数的**形参作用域**中，可以用 `this` 指代正在被初始化的对象。

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

注意 `j(this->i)` 之所以良构，是因为成员 `i` 在 `j` **之前**声明，因此先于 `j` 初始化。若把 `j` 的声明移到 `i` 前面，`this->i` 读取的就是尚未初始化的值。

`r(a)` 的绑定合法，是因为它只需要 `a` 的**地址**，不需要 `a` 的值；按 [[class.cdtor#3]]，形成指向直接成员的指针只要求包含它的对象已经**开始**构造。

## 构造期间调用成员函数（¶18–¶19）

¶18 成员函数（包括虚函数）**可以**对正在构造或析构的对象调用；正在构造/析构的对象也可以作为 `typeid` 或 `dynamic_cast` 的操作数。但是，若这些操作在以下时刻进行，行为未定义：

- ¶18.1 在 *ctor-initializer* 的求值过程中（或其直接、间接调用的函数中），**所有基类的 mem-initializer 完成之前**；
- ¶18.2 在构造函数的**前置条件断言**求值时 {{c++26}}；
- ¶18.3 在析构函数的**后置条件断言**求值时 {{c++26}}（[[dcl.contract.func]]）。

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

为什么以"所有基类初始化完成"为界？因为成员函数可以访问基类的成员、可以经过基类调用虚函数；在基类构造之前，基类子对象的状态（包括 vptr）都还没有建立。而一旦所有基类构造完成，对象的"基类部分"就都可用了——剩下尚未初始化的只是本类的数据成员，访问它们得到不确定值是另一个层面的问题。

¶18.2/¶18.3 是 C++26 引入契约（[[dcl.contract.func]]）后添加的：构造函数的前置条件在任何子对象初始化之前求值，析构函数的后置条件在所有子对象析构之后求值，此时对象完全不可用。截至写作时，Clang 尚未实现契约语法。

¶19（注 9）构造期间虚函数调用、`typeid`、`dynamic_cast` 在良定义情形下的**结果**，由 [[class.cdtor]] 规定（"按当前正在构造的类分派"）。

## 包展开（¶20）

¶20 后跟省略号的 *mem-initializer* 是一个包展开（[[temp.variadic]]），初始化 *base-specifier-list* 中由包展开指定的基类：

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
    为了实现"虚基类只由最派生类初始化"（¶7、¶15.1），Itanium ABI（GCC、Clang 在 Linux/macOS 上使用）为每个构造函数生成**两个变体**：

    - **完整对象构造函数**（complete object constructor，mangled 名中为 `C1`）：用于构造一个完整对象，**会**初始化虚基类；
    - **基类子对象构造函数**（base object constructor，`C2`）：派生类构造函数调用基类构造函数时使用，**跳过**虚基类的初始化。

    对没有虚基类的类，两个变体完全相同，编译器通常让它们共用一份代码（别名）。析构函数同理有 `D1`/`D2`（另有 deleting destructor `D0`）。

    有虚基类时，基类子对象构造函数还需要知道"在当前最派生类里，我的虚基类在哪、构造期间该用哪张虚表"，这些信息通过 **VTT**（virtual table table）作为隐藏参数传入。

    MSVC 采用不同方案：带虚基类的类的构造函数接收一个隐藏的整数参数，表示"是否为最派生类"，由它决定是否初始化虚基类。

!!! impl "诊断"
    - `-Wreorder-ctor`（Clang）/ `-Wreorder`（GCC）：*mem-initializer* 书写顺序与真实顺序不一致。
    - `-Wuninitialized`：在成员初始化器中读取尚未初始化的成员（Clang 能发现简单情形）。
    - `-Wdangling-field`（Clang）：引用或指针成员绑定到构造函数形参等即将销毁的对象。
    - 委托循环：Clang 在同一 TU 内可见时直接报错。

## 历史与演进

!!! history "历史与演进"
    - **C++98**：已有 *ctor-initializer*、声明顺序初始化、虚基类只由最派生类初始化的规则。*mem-initializer* 中绑定到引用成员的临时量"存活到构造函数退出"。
    - **C++11**：
        - 委托构造函数（[[N1986]]）；
        - 非静态数据成员的默认成员初始化器（[[N2756]]），以及 ¶12"被 mem-initializer 覆盖"的规则；
        - *mem-initializer* 可以使用 *braced-init-list*、可以是包展开。
    - **C++14/17**：引用成员绑定临时量的规则经核心语言 issue 收紧：*mem-initializer* 中的绑定与默认成员初始化器中的绑定都改为非良构（¶8、¶13）。
    - **C++20**：未被初始化的成员读取规则与对象模型一同重写（[[basic.indet]]）。
    - **C++26**：¶18 增加构造函数前置条件、析构函数后置条件中调用成员函数为 UB 的条目（契约，[[dcl.contract.func]]）；注 4 中"不确定值"扩展为"不确定或错误值"（erroneous behavior，[[basic.indet]]）。

## 陷阱

!!! pitfall "以为 mem-initializer 的书写顺序就是初始化顺序"
    初始化顺序只由类定义决定：虚基类 → 直接基类（声明顺序）→ 成员（声明顺序）→ 函数体。打开 `-Wall`，让编译器替你检查。

!!! pitfall "在中间类里初始化虚基类，以为它会生效"
    中间类的虚基类 *mem-initializer* 在构造派生类对象时被忽略，实参都不求值。每个最派生类都要为没有默认构造函数的虚基类提供 *mem-initializer*。

!!! pitfall "在委托构造函数里“顺便”初始化一个成员"
    委托的 *mem-initializer* 必须单独出现。想"在委托之后修改某个成员"，只能在委托构造函数体里赋值。

!!! pitfall "引用成员 + 形参 = 悬垂"
    `struct S { const std::string& s; S(const std::string& x) : s(x) {} }; S obj("hi");`——良构，但 `"hi"` 物化出的临时 `std::string` 在 `obj` 的初始化结束时就销毁了，`obj.s` 悬垂。¶8 只禁止**直接**在 *mem-initializer* 中把临时量绑定到引用成员。

!!! pitfall "在基类 mem-initializer 中调用本类成员函数"
    `D() : Base(compute()) {}`，若 `compute` 是 `D` 的非静态成员函数，就是 ¶18.1 的 UB。改用静态成员函数或自由函数。

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

`X` 是最派生类，先初始化虚基类 `V`，使用 `X` 自己的 *mem-initializer*（`L` 里的 `V("V from L")` 被忽略）。然后按 *base-specifier-list* 的顺序：先 `R`，再 `L`（虽然 *mem-initializer* 里只写了 `L()`）；`L` 构造时先初始化成员 `p`（默认成员初始化器），再执行函数体。最后是 `X` 的成员 `q` 和函数体。
</details>

!!! question "思考题 2"
    `struct S { S() : S(0) {} S(int) noexcept(false); ~S() = delete; };` 良构吗？`S(int)` 定义为 `S::S(int) {}` 呢？

<details markdown="1">
<summary>答案</summary>

`S(int)` 是非委托构造函数：`S` 没有类类型的子对象，¶14 不涉及 `S` 自己的析构函数，所以 `S::S(int) {}` 本身良构。

`S()` 是委托构造函数，¶14 明确只适用于**非委托**构造函数。但 [[except.ctor#4]] 规定：委托构造函数的函数体因异常退出时，要调用**对象的析构函数**——而析构函数被删除了。[[class.dtor]] 列举"潜在调用"的情形时只点名了 [[expr.new]]、[[stmt.return]]、[[dcl.init.aggr]]、[[class.base.init]]、[[except.throw]]，并没有单独点名委托构造函数；不过"is invoked"本身就涵盖实际可能发生的调用。实践中 Clang 拒绝 `S()` 的定义（报告使用了被删除的函数），这也是合理的读法：委托构造函数需要可用的析构函数。这里的措辞是一个值得 language lawyer 留意的灰色地带。
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

`j` 在 `i` 之前声明，所以先初始化 `j`；此时 `this->i` 尚未初始化，读取它在 C++23 及之前是 UB（不确定值的左值到右值转换），在 C++26 中对自动存储期的对象一般是错误行为（读到错误值），对静态存储期对象则读到零初始化的 0。无论如何都不是程序员想要的。*mem-initializer* 的书写顺序（先 `i` 后 `j`）不能改变这一点，`-Wreorder-ctor` 会提醒。
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
