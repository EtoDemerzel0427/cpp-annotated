---
title: 初始化基类与成员
summary: 构造函数的成员初始化列表能写什么、没写的子对象怎样初始化、初始化按什么顺序进行，以及委托构造函数和构造期间调用成员函数的限制。
status: done
papers: N1986, N2756, CWG1696
related: class.init, class.inhctor.init, class.cdtor, class.mem, class.dtor, except.ctor, basic.life, dcl.init, class.copy.ctor, dcl.contract.func, topics/special-members-and-elision
tags: 构造函数, 初始化顺序, 委托构造, 虚基类, UB
updated: 2026-10-19
---

!!! tldr
    - 初始化顺序只由类定义决定：虚基类（只由最派生类初始化）、直接基类（按声明顺序）、成员（按声明顺序）、最后是函数体。成员初始化列表的书写顺序不起作用。
    - 列表里没写的成员，有默认成员初始化器就用它，否则默认初始化；写了的成员会忽略默认成员初始化器。
    - 中间类为虚基类写的初始化器在构造更派生的对象时被忽略，实参也不求值。
    - 委托构造函数的初始化列表只能有委托这一项；目标构造函数返回时对象就算构造完成，委托构造函数体再抛异常会调用析构函数。
    - 所有基类初始化完成之前调用本对象的成员函数是 UB；引用成员绑定到临时量是非良构的。

## 构造函数体之前发生了什么

```cpp run title="init-order.cpp" ok
#include <cstdio>

struct M {
    M(const char* s) { std::printf("%s ", s); }
};
struct A { A() { std::printf("A "); } };
struct B { B() { std::printf("B "); } };

struct C : A, B {
    M m1, m2;
    C() : m2("m2"), m1("m1"), B(), A() {
        std::puts("body");
    }
};

int main() { C c; }   // A B m1 m2 body
```

构造函数定义里冒号后面那一段叫 *ctor-initializer*，俗称成员初始化列表。其中每一项是一个 *mem-initializer*，形如 `名字(实参)` 或 `名字{实参}`。进入函数体之前，所有基类子对象和非静态数据成员都已经初始化好了。初始化列表决定它们怎样初始化，但不决定按什么顺序初始化：上例写的是 `m2, m1, B, A`，实际顺序是 `A B m1 m2`。

¶1 *ctor-initializer* 只能出现在构造函数的定义里（它是 *function-body* 的一部分，[[dcl.fct.def.general]]），可以为直接基类、虚基类和非静态数据成员指定初始化器：

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

*mem-initializer-id* 可以是类名或 `decltype`（指名基类或本类），也可以是标识符（通常指名成员）。每项后面可以跟 `...`，表示包展开（¶20）。

## 初始化顺序（¶15–¶16）

¶15 在非委托构造函数中，初始化按下面的顺序进行：

1. ¶15.1 虚基类，只在最派生类（[[g:most-derived-object|最派生对象]]的类，[[intro.object]]）的构造函数中初始化。顺序是对基类有向无环图做深度优先、从左到右遍历时它们出现的顺序，从左到右指基类在 *base-specifier-list* 中的顺序；
2. ¶15.2 直接基类，按 *base-specifier-list* 中的声明顺序；
3. ¶15.3 非静态数据成员，按它们在类定义中的声明顺序；
4. ¶15.4 最后执行构造函数的函数体。

后三步都与 *mem-initializer* 的书写顺序无关。注 7 说明了原因：析构必须按初始化的相反顺序进行，而析构函数只有一个，构造函数可以有很多个。如果初始化顺序随每个构造函数的初始化列表而变，析构函数就得知道对象是由哪个构造函数构造的。采用类定义里唯一的声明顺序，这个问题就不存在了。

Clang 对书写顺序与实际顺序不一致的列表给出 `-Wreorder-ctor` 警告，GCC 叫 `-Wreorder`，两者都在 `-Wall` 中。

### 顺序不一致的危害

只要各个初始化器之间没有依赖，书写顺序只是风格问题。危险来自依赖：

```cpp run title="reorder-bug.cpp" eb
struct S {
    int a, b;
    S(int x) : b(x), a(b + 1) {}   // 先初始化的是 a，此时 b 还没有值
};

int main() {
    S s(1);
    return s.a;
}
```

`a` 先声明，所以先初始化，读到的 `b` 还没有初始化。`s` 是自动存储期对象，C++26 中读到的是错误值，属于错误行为（[[basic.indet]]）；C++23 及之前读不确定值是 UB。本机 Clang 23 对这段代码同时给出 `-Wreorder-ctor` 和 `-Wuninitialized`。修复方法是让声明顺序与依赖一致，或者让各初始化器都只从形参计算。

### 虚基类的顺序（¶16）

虚基类在整个对象里只有一份，却可能有多个中间类都想初始化它。标准的选择是只由最派生类初始化，中间类的初始化器一律忽略（见下文“虚基类只由最派生类初始化”）。标准例 9 加上输出：

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
    A a(2);   // V(2)：A 是最派生类
    B b(3);   // V()：B(int) 没有为 V 写初始化器
    C c(4);   // V()：C(int) 没写；A、B 的初始化器被忽略
}
```

有多个虚基类时，深度优先、从左到右的遍历保证所有派生类都用同一个顺序。例如 `struct Q : virtual R {}; struct X : virtual P, Q {};`，遍历 `X` 时先遇到 `P`，再进入 `Q` 遇到 `R`，所以先初始化 `P`、`R` 两个虚基类，然后才是非虚直接基类 `Q`。

## 初始化列表里能写什么（¶2–¶5）

### 名字的查找（¶2）

```cpp run title="same-name-param.cpp" ok
struct P {
    int x;
    P(int x) : x(x) {}   // 括号外是成员，括号内是形参
};

int main() { return P(0).x; }
```

¶2 *mem-initializer-id* 中的无限定名查找忽略构造函数的形参作用域，所以括号外的 `x` 找到成员 `P::x`。括号里的实参是普通表达式，位于形参作用域中（¶17），形参 `x` 遮蔽了成员。

注 1：如果类有一个成员与某个直接基类或虚基类同名，单个标识符的 *mem-initializer-id* 指的是成员；要初始化被遮蔽的基类，得用限定名。

<div class="compare" markdown="1">

```cpp error
struct Base { Base(int) {} };
struct S1 : Base {
    int Base;
    S1() : Base(1) {}
    // error: Base 是成员 int Base，
    // 基类 Base 没有默认构造函数
};
```

```cpp ok
struct Base { Base(int) {} };
struct S2 : ::Base {
    int Base;
    S2() : ::Base(1), Base(2) {}
    // ::Base 是基类，Base 是成员
};
```

</div>

¶2 最后一句：*mem-initializer-id* 只能指名构造函数所属的类本身（委托，¶6）、该类的直接非静态数据成员，或者该类的直接基类或虚基类，否则非良构。成员的成员、间接的非虚基类、静态成员都不能在这里初始化。

### 基类的写法（¶3）

¶3 初始化基类时，可以用任何表示这个基类类型的 *class-or-decltype*：typedef、别名、注入类名、`decltype` 都可以。

```cpp run title="base-alias.cpp" ok
template<class T> struct TB { TB(T) {} };

struct S3 : TB<int> {
    using Alias = TB<int>;
    S3() : Alias(1) {}
};
struct S4 : TB<int> {
    S4() : TB(1) {}   // 基类的注入类名
};

int main() { S3 a; S4 b; }
```

`S4` 的写法在模板里很方便：基类 `TB<int>` 的注入类名 `TB` 被继承到 `S4` 的作用域里（[[class.pre]]）。如果基类依赖于模板参数，比如 `template<class T> struct D : TB<T>`，无限定查找看不到依赖基类里的名字，必须写全 `TB<T>`。

### 两种非良构（¶4–¶5）

```cpp title="ambiguous-base.cpp" error
struct A { A() {} };
struct B : virtual A {};
struct C : A, B { C(); };
C::C() : A() {}   // error: 是直接基类 A 还是虚基类 A？
```

¶4 如果 *mem-initializer-id* 同时指代一个直接非虚基类和一个间接虚基类，非良构。这种类层次本身就会让 Clang 警告直接基类 `A` 因二义性不可访问，实践中应当避免。

¶5 *ctor-initializer* 可以初始化本类的变体成员（[[g:variant-member]]，即联合体或匿名联合体的成员）。同一个成员或同一个基类出现两次，非良构：`D(int v) : x(v), x(1) {}` 会被拒绝。

## 没写的子对象怎样初始化（¶9、¶12、¶10）

```cpp title="unmentioned.cpp" error
struct A { A(); };
struct B { B(int); };

struct C {
    C() {}
    A a;          // OK：调用 A::A()
    const B b;    // error: B 没有默认构造函数
    int i;        // OK：i 没有初始化
    int j = 5;    // OK：j 的值是 5
};
```

¶9 在非委托构造函数中（隐式定义的复制、移动构造函数除外，它们的规则在 [[class.copy.ctor]]），一个[[g:potentially-constructed-subobjects|潜在构造的子对象]]（非静态数据成员、直接基类，以及非抽象类的虚基类）如果没有被任何 *mem-initializer* 指名：

- ¶9.1 它是带默认成员初始化器（[[g:default-member-initializer]]）的非静态数据成员时，用默认成员初始化器初始化。条件是：如果它属于联合体（或匿名联合体），同一联合体的其他成员都没有被 *mem-initializer* 指名（¶9.1.1、¶9.1.2）；
- ¶9.2 否则，如果它是匿名联合体或变体成员，不初始化；
- ¶9.3 否则，默认初始化。

注 4：对于自动或动态存储期的对象，构造函数返回之后（且不是值初始化的一部分），一个既没有初始化、也没有在函数体里赋值的成员，具有不确定值或错误值（[[basic.indet]]）。上例中的 `i` 就是这样。

### 初始化列表优先于默认成员初始化器（¶12）

```cpp run title="dmi-ignored.cpp" ok
#include <cstdio>

int side_effect() { std::puts("side effect"); return 1; }

struct A {
    int i = side_effect();
    A() {}                  // 用默认成员初始化器
    A(int arg) : i(arg) {}  // 不求值默认成员初始化器
};

int main() {
    A a1;      // side effect
    A a2(5);   // 没有输出
    return a2.i;
}
```

¶12 同时有默认成员初始化器和 *mem-initializer* 的成员，按 *mem-initializer* 初始化，默认成员初始化器被忽略，其中的副作用也不会发生。这正是 C++11 引入默认成员初始化器（[[N2756]]）的用法：给大多数构造函数共用的值写一个默认值，个别构造函数再覆盖它。

¶10 试图初始化联合体的多个非静态数据成员是非良构的，例如 `union U { int a; float b; U() : a(1), b(2) {} };`。

## 实参怎样初始化子对象（¶7、¶8、¶13）

¶7 *mem-initializer* 中的实参按 [[dcl.init]] 的直接初始化规则初始化所指名的子对象，委托时则初始化整个对象。所以 `explicit` 构造函数也可以被选中，`m{...}` 是直接列表初始化，禁止窄化。

注 2：每个 *mem-initializer* 执行的初始化是一个完整表达式（[[intro.execution]]）。其中创建的临时对象在这一项初始化结束时就销毁，而不是等到构造函数结束。

### 引用成员不能绑定临时量

<div class="compare" markdown="1">

```cpp error
struct A {
    A() : v(42) {}  // error
    const int& v;
};
```

```cpp error
struct A {
    A() = default;
    const int& v = 42;
};
A a1;  // error: 用到了这个
       // 默认成员初始化器
```

</div>

¶8 在 *mem-initializer* 中把临时量绑定到引用成员是非良构的。¶13 对默认成员初始化器作同样的规定，错误在用到这个默认成员初始化器的地方报告。

这样的绑定没有任何合法用途：临时量最多活到构造函数结束，对象一构造完，引用就悬垂了。C++98 的规则是让临时量存活到构造函数退出；[[CWG1696]] 把两种写法都改为非良构。

规则只能拦住绑定临时量这一种能静态判定的情形。标准例 8 里还有一行 `A(int v) : v(v) {}` 后跟 `A a2(1);`，注释是 OK, unfortunately：引用绑定到形参，同样在构造函数返回后悬垂，但它是良构的。本机 Clang 23 对这种写法给出 `-Wdangling-field` 警告。

## 虚基类只由最派生类初始化（¶7 末、注 3）

```cpp run title="vbase-ignored.cpp" ok
#include <cstdio>

int g() { std::puts("g()"); return 1; }

struct V { V(int i = 0) { std::printf("V(%d)\n", i); } };
struct A : virtual V { A() : V(g()) { std::puts("A()"); } };
struct B : A {};

int main() {
    A a;   // g() / V(1) / A()
    B b;   // V(0) / A()：没有调用 g()
}
```

¶7 最后一句：构造非最派生类的对象时，指名虚基类的 *mem-initializer* 被忽略，实参也不求值。构造 `B` 时 `A` 不是最派生类，`A` 的 `V(g())` 作废；`B` 自己没有为 `V` 写初始化器，于是按 ¶9.3 默认初始化 `V`。

所以如果虚基类没有默认构造函数，每个最派生类都必须为它写初始化器。注 3 指出一个例外：抽象类永远不会是最派生类，它的构造函数从不初始化虚基类，相应的初始化器可以省略。

```cpp run title="abstract-vbase.cpp" ok
struct V { V(int) {} };            // 没有默认构造函数
struct Abs : virtual V {
    Abs() {}                       // OK：抽象类不初始化 V
    virtual void f() = 0;
};
struct Impl : Abs {
    Impl() : V(1) {}               // 最派生类必须初始化 V
    void f() override {}
};

int main() { Impl i; }
```

!!! impl "Itanium ABI 的两个构造函数变体"
    为了让虚基类只由最派生类初始化，Itanium ABI（GCC、Clang 在 Linux 和 macOS 上使用）为每个构造函数生成两个变体：完整对象构造函数（修饰名里是 `C1`）会初始化虚基类；基类子对象构造函数（`C2`）供派生类构造函数调用，跳过虚基类。没有虚基类时两者相同，通常共用一份代码。析构函数同样有 `D1`、`D2`，另有负责释放内存的 `D0`。

    有虚基类时，`C2` 还需要知道虚基类在当前最派生对象中的位置、构造期间用哪张虚表，这些信息通过一个叫 VTT 的表作为隐藏参数传入。MSVC 的方案不同：构造函数多接收一个隐藏的整数参数，表示自己是否在构造最派生对象。

## 委托构造函数（¶6、¶11）

```cpp title="delegating.cpp" error
struct C {
    C(int) {}              // #1
    C() : C(42) {}         // #2：委托给 #1
    C(char) : C(42.0) {}   // #3 与 #4 互相委托：IFNDR
    C(double) : C('a') {}  // #4
};

struct E {
    E() : E(1), m(2) {}    // error: 委托必须单独出现
    E(int);
    int m;
};
```

¶6 *mem-initializer-id* 指名构造函数所属的类本身时，这个构造函数是[[g:delegating-constructor|委托构造函数]]，被选中的那个构造函数（由重载决议选出）是[[g:target-constructor|目标构造函数]]。规则有三条：

- 委托的 *mem-initializer* 必须是唯一的一项。目标构造函数会完整初始化所有基类和成员，如果还能再初始化 `m`，`m` 就会初始化两次；
- 目标构造函数返回之后，才执行委托构造函数的函数体；
- 构造函数直接或间接委托给自己，是非良构、不要求诊断（IFNDR）的：编译器不必报告，程序的行为没有任何保证。不要求诊断是因为目标构造函数可以定义在别的翻译单元里。整个循环在同一个翻译单元中可见时，本机 Clang 23 直接报错（`-Wdelegating-ctor-cycles`，默认是错误）。

### 对象何时构造完成（¶11）

¶11 一个非委托构造函数返回时，对象的初始化就算完成。注 5 指出，所以对象的生命周期（[[basic.life]]）可以在委托构造函数全部完成之前就开始。

这条规则决定了异常时是否调用析构函数：

```cpp run title="delegating-throw.cpp" ok
#include <cstdio>
#include <stdexcept>

struct Res {
    Res()  { std::puts("Res()"); }
    ~Res() { std::puts("~Res()"); }
};

struct A {
    Res r;
    A(int) { std::puts("A(int)"); }
    A() : A(0) { throw std::runtime_error("x"); }
    ~A() { std::puts("~A()"); }
};

struct B {
    Res r;
    B(int) { std::puts("B(int)"); throw 1; }
    ~B() { std::puts("~B()"); }
};

int main() {
    try { A a; } catch (...) {}    // Res() A(int) ~A() ~Res()
    try { B b(1); } catch (...) {} // Res() B(int) ~Res()
}
```

`B(int)` 是非委托构造函数，抛出异常时对象从未构造完成，不调用 `~B()`，只析构已经构造好的成员（[[except.ctor#3]]）。`A()` 的目标构造函数已经返回，对象已经构造完成，委托构造函数体抛出异常时会调用 `~A()`（[[except.ctor#4]]）。

这给出一种惯用法：在目标构造函数里建立不变式，把后续可能失败的步骤放进委托构造函数体，出错时由析构函数负责清理。

## 子对象的析构函数（¶14）

```cpp title="dtor-potentially-invoked.cpp" error
struct NoDtor { ~NoDtor() = delete; };

struct H {
    NoDtor n;
    H() {}   // error: 需要 NoDtor::~NoDtor()
};
```

¶14 在非委托构造函数中，每个类类型的潜在构造子对象的析构函数都是潜在调用的（potentially invoked，[[class.dtor]]）。潜在调用的析构函数必须可访问且未被删除，否则程序非良构。注 6 给出理由：构造中途抛出异常时，要析构已经构造完成的子对象（[[except.ctor]]）。即使构造函数声明为 `noexcept`，这条要求也不变。

!!! lawyer "委托构造函数与被删除的析构函数"
    ¶14 只说非委托构造函数。但 [[except.ctor#4]] 规定委托构造函数体因异常退出时要调用对象的析构函数，而 [[class.dtor]] 把实际会调用的情形也算作潜在调用。所以 `struct S { S() : S(0) {} S(int); ~S() = delete; };` 中的 `S()` 需要一个可用的析构函数，本机 Clang 23 拒绝它（attempt to use a deleted function）。

## 初始化器里的 `this` 和成员函数（¶17–¶19）

```cpp run title="this-in-init.cpp" ok
class X {
    int a;
    int b;
    int i;
    int j;
public:
    const int& r;
    X(int i) : r(a), b(i), i(i), j(this->i) {}
};

int main() { X x(3); (void)x; }
```

¶17 是一条注：*mem-initializer* 的实参位于构造函数的形参作用域中，可以用 `this` 指代正在初始化的对象。标准例 10 里：

- `r(a)` 把引用绑定到成员 `a`。只用到 `a` 的地址，不读它的值，所以 `a` 还没初始化也没关系（[[class.cdtor#3]]）；
- `b(i)` 和 `i(i)` 用的是形参 `i`；
- `j(this->i)` 读成员 `i`。形参遮蔽了成员，必须写 `this->i`。它能读到正确的值，是因为 `i` 在 `j` 之前声明，先初始化。

本机 Clang 23 对这个例子给出 `-Wreorder-ctor`（`r` 最后声明却写在最前），这里无害。

### 基类初始化完成之前不能调用成员函数（¶18）

```cpp run title="call-before-bases.cpp" ub
struct A { A(int) {} };

class B : public A {
    int j;
public:
    int f() { return 0; }
    B() : A(f()),   // UB: 基类 A 还没有初始化
          j(f()) {} // OK：所有基类都已初始化
};

class C { public: C(int) {} };

class D : public B, C {
    int i;
public:
    D() : C(f()),   // UB: 基类 C 还没有初始化
          i(f()) {} // OK
};

int main() { D d; }
```

¶18 可以对正在构造或析构的对象调用成员函数（包括虚函数），它也可以作为 `typeid` 或 `dynamic_cast` 的操作数。但在下面三个时刻这样做是未定义行为：

- ¶18.1 在 *ctor-initializer* 中（包括从这里直接或间接调用的函数中），所有基类的 *mem-initializer* 完成之前；
- ¶18.2 在构造函数的前置条件断言中 {{c++26}}；
- ¶18.3 在析构函数的后置条件断言中 {{c++26}}（[[dcl.contract.func]]）。

以所有基类初始化完成为界，是因为成员函数可能访问基类的成员，也可能经由基类调用虚函数，而基类子对象（包括它的虚表指针）在那之前还没有建立。`D` 的例子说明，`B` 已经构造好也不够，必须等 `C` 也完成。构造函数的前置条件在任何子对象初始化之前求值，析构函数的后置条件在所有子对象析构之后求值，这两个时刻对象完全不可用。

想在基类初始化器里算一个值，可以改用静态成员函数或自由函数。

¶19 是一条注：在良定义的情形下，构造期间虚函数调用、`typeid`、`dynamic_cast` 的结果见 [[class.cdtor]]。

## 包展开（¶20）

```cpp run title="mixins.cpp" ok
#include <cstdio>

template<class... Mixins>
class X : public Mixins... {
public:
    X(const Mixins&... mixins) : Mixins(mixins)... {}
};

struct Loud {
    Loud() = default;
    Loud(const Loud&) { std::puts("Loud copied"); }
};
struct Quiet {};

int main() {
    X<Loud, Quiet> x(Loud{}, Quiet{});   // Loud copied
}
```

¶20 后面跟省略号的 *mem-initializer* 是一个包展开（[[temp.variadic]]），初始化 *base-specifier-list* 中由包展开给出的那些基类。这是 mixin 组合的标准写法。

## 历史与演进

!!! history
    - C++98 已有成员初始化列表、按声明顺序初始化、虚基类只由最派生类初始化等规则。
    - C++11 加入委托构造函数（[[N1986]]）、默认成员初始化器（[[N2756]]）、花括号形式的 *mem-initializer* 和包展开。
    - [[CWG1696]] 把引用成员绑定临时量（在 *mem-initializer* 或默认成员初始化器中）改为非良构。
    - C++26 在 ¶18 中加入契约断言的两项，注 4 中的不确定值扩展为不确定值或错误值。

## 思考题

!!! question "思考题 1"
    下面的程序输出什么？

    ```cpp
    #include <cstdio>
    struct P { P(const char* s) { std::puts(s); } };
    struct Q { Q(const char* s) { std::puts(s); } };
    struct V { V(const char* s = "V()") { std::puts(s); } };
    struct L : virtual V {
        P p{"L::p"};
        L() : V("V from L") { std::puts("L"); }
    };
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

`X` 是最派生类，先初始化虚基类 `V`，用的是 `X` 自己的初始化器，`L` 里的 `V("V from L")` 被忽略。然后按 *base-specifier-list* 的顺序先 `R` 后 `L`，尽管初始化列表里只写了 `L()`。构造 `L` 时先用默认成员初始化器初始化 `p`，再执行函数体。最后是成员 `q` 和 `X` 的函数体。
</details>

!!! question "思考题 2"
    把标准例 10 改成下面这样，`j` 的值是什么？

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

`j` 在 `i` 之前声明，所以先初始化 `j`，此时 `this->i` 还没有值，书写顺序改变不了这一点。对自动存储期的 `X` 对象，C++26 中读到的是错误值（错误行为），C++23 及之前是 UB；对静态存储期的对象，读到的是零初始化得到的 0。`-Wreorder-ctor` 会给出提醒。
</details>
