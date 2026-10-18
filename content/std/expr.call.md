---
title: 函数调用
summary: 函数调用表达式的完整语义：被调表达式的要求、虚调用、结果类型与值类别、C++17 的求值顺序（前缀先序于实参、实参之间非决定性先序）、形参的初始化与（实现定义时机的）销毁、经错误函数类型调用的 UB、可变实参与默认实参提升、显式对象形参、C++26 契约断言的求值次序
status: draft
papers: P0145R3, P0847R7, P2900R14, P0012R1
related: intro.execution, over.match.call, over.call.func, dcl.fct, dcl.fct.default, dcl.contract.func, class.temporary, stmt.return, conv.fctptr, class.cdtor, support.runtime, basic.lval
tags: 表达式, 函数调用, 求值顺序, 可变实参, 契约, UB
updated: 2026-10-17
---

函数调用是 C++ 中最常见、规则也最多的表达式：运算符重载、构造函数、转换函数、lambda、`std::invoke` 最终都归结为"调用一个函数"。本节回答的问题是：

- 什么样的表达式可以被调用？调用的是哪个函数——静态选中的那个，还是动态类型中的最终覆盖者？
- 实参和形参如何对应？形参何时被初始化、何时被销毁、在谁的上下文里？
- 前缀表达式、各个实参、契约断言之间按什么顺序求值？
- 调用表达式的类型和值类别是什么？
- 什么时候是 UB（经错误类型的指针调用）、什么时候是有条件支持（经 `...` 传递非平凡类对象）？

**选哪个函数**不归本节管：名字指向重载集时，由重载决议（[[over.match.call]]）决定；本节处理的是"已经知道调用哪个函数之后"的事。

## 调用表达式的形式（¶1）

¶1：函数调用是后缀表达式后跟圆括号，括号里是可能为空、逗号分隔的 *initializer-clause* 列表——**实参**（arguments）。实参可以是花括号初始化列表（`f({1, 2})`）或包展开（`f(xs...)`）。

被调用的后缀表达式（下称**被调表达式**）必须具有**函数类型或函数指针类型**。对**非成员函数或静态成员函数**的调用，被调表达式必须是：

- 指代函数的**左值**——此时**抑制**函数到指针转换（[[conv.func]]），即直接调用，不先退化为指针；或
- 函数指针类型的 **prvalue**。

```cpp run title="callee-forms.cpp" ok
int f(int x) { return x + 1; }

int main() {
    int (&rf)(int) = f;
    int (*pf)(int) = f;
    int a = f(1);        // 左值 f，指代函数
    int b = rf(1);       // 函数左值（引用）
    int c = pf(1);       // 函数指针 prvalue（pf 先经左值到右值转换）
    int d = (*pf)(1);    // *pf 是函数左值
    int e = (**********pf)(1);   // 每个 * 产生函数左值，又退化为指针……仍然合法
    return (a + b + c + d + e == 10) ? 0 : 1;
}
```

非静态成员函数的调用走另一条路：被调表达式是类成员访问 `E1.E2`（或隐式的 `(*this).E2`），按 [[expr.ref#8]]，指代非静态成员函数的 `E1.E2` 是一个**只能被立即调用的 prvalue**；成员指针形式 `(obj.*pmf)(args)` 同理（[[expr.mptr.oper]]）。

## 静态绑定与虚调用（¶2）

¶2：若选中的函数**不是虚函数**，或者类成员访问中的 *id-expression* 是**限定名**（`p->Base::f()`），就调用该函数本身。否则调用对象表达式**动态类型**中该函数的**最终覆盖者**（final overrider，[[class.virtual]]）——这称为**[[g:virtual-function-call|虚函数调用]]**（virtual function call）。

注 2 补充：动态类型由对象表达式**当前值**所指对象决定；对正在构造或析构的对象，虚调用的行为由 [[class.cdtor]] 规定（分派到当前构造/析构的类）。

```cpp run title="virtual-call.cpp" ok
struct B { virtual int f() { return 1; } };
struct D : B { int f() override { return 2; } };

int main() {
    D d;
    B& b = d;
    int x = b.f();        // 虚调用：D::f → 2
    int y = b.B::f();     // 限定名：非虚调用，B::f → 1
    int (B::*pmf)() = &B::f;
    int z = (b.*pmf)();   // 成员指针调用虚函数：仍然虚分派 → 2
    return (x == 2 && y == 1 && z == 2) ? 0 : 1;
}
```

¶3 是注：若使用函数名而名字查找**找不到声明**，程序非良构——**不会隐式声明函数**。这是与 C89 的"隐式函数声明"（调用未声明的 `foo()` 视为 `int foo()`）彻底划清界限。

## 调用表达式的类型（¶4）

¶4：调用的类型是**静态选中的函数**（忽略 `virtual`）的返回类型，**即使实际调用的函数的返回类型不同**。这里说的是**协变返回类型**：

```cpp run title="covariant.cpp" ok
#include <type_traits>

struct B { virtual B* clone() const { return new B(*this); } virtual ~B() = default; };
struct D : B { D* clone() const override { return new D(*this); } };

int main() {
    D d;
    const B& b = d;
    static_assert(std::is_same_v<decltype(b.clone()), B*>);   // 静态选中 B::clone
    static_assert(std::is_same_v<decltype(d.clone()), D*>);   // 静态选中 D::clone
    B* p = b.clone();     // 实际调用 D::clone，返回的 D* 被转换为 B*（¶9）
    delete p;
}
```

被调表达式若指代**析构函数或伪析构函数**（[[expr.prim.id.dtor]]），调用的类型是 `void`。对伪析构函数（标量类型的"析构函数"），¶4 规定调用会**销毁**对象表达式所指的标量对象——也就是结束其生命周期（[[basic.life]]）。这条规则在 C++20 由 [[P0593R6]] 引入；此前 `p->~int()` 被视为空操作。

```cpp run title="pseudo-dtor.cpp" ok
#include <memory>

template<class T> void destroy(T* p) { p->~T(); }   // 对 int 实例化时是伪析构函数调用

int main() {
    int x = 1;
    destroy(&x);          // C++20 起：x 的生命周期结束
    ::new (&x) int(2);    // 在原存储上重新创建一个 int；x 透明可替换，此后可以用名字 x
    return x == 2 ? 0 : 1;
}
```

## 契约断言的次序（¶5）{{c++26}}

C++26 引入函数契约断言（[[dcl.contract.func]]，[[P2900R14]]）。¶5 规定一次调用涉及的前置/后置断言及其顺序：

| 列表项 | 断言 |
|---|---|
| ¶5.1 | 若是经类成员访问的**虚函数调用**：先是**静态选中函数**的前置断言 |
| ¶5.2 | 然后是**实际调用函数**的前置断言 |
| ¶5.3 | 后置：先是**实际调用函数**的后置断言 |
| ¶5.4 | 若是虚调用：最后是**静态选中函数**的后置断言 |

设计意图：调用方看到的是**静态类型的接口**，它的契约必须被检查；实现方（覆盖者）的契约也必须被检查。前置条件"由外向内"（接口 → 实现），后置条件"由内向外"（实现 → 接口），形成对称的嵌套。

标准例 1 的要点（改写）：

```cpp title="contracts-virtual.cpp"
struct X1 { virtual void f() pre(a) post(b) {} };
struct Y : X1 { void f() override pre(e) post(f) {} };

void t(Y& y) {
    X1& x = y;
    x.f();          // 虚调用：断言 a, e, f, b（接口 pre、实现 pre、实现 post、接口 post）
    x.X1::f();      // 限定名，非虚：只有 a, b
    y.f();          // 静态选中的就是 Y::f：只有 e, f
    void (X1::*pmf)() = &X1::f;
    (x.*pmf)();     // 经成员指针调用：不是"类成员访问表达式"，只断言实际调用函数的 e, f
}
```

最后一行很微妙：¶5.1 只在被调表达式是**类成员访问表达式**时才加上静态选中函数的断言；成员指针调用经由 `.*`，不是类成员访问，所以只检查实际被调函数的断言。（截至写作时，本机 Clang 尚未实现契约，此例未经编译验证。）

## 经不兼容的函数类型调用：UB（¶6）

¶6 先定义一个术语：函数类型 `Tcall` 与 `Tfunc` **[[g:call-compatible|调用兼容]]**（call-compatible），若二者相同，或者"指向 `Tfunc` 的指针"能经**函数指针转换**（[[conv.fctptr]]，即去掉 `noexcept`）转换为"指向 `Tcall` 的指针"。

!!! std
    Calling a function through an expression whose function type is not call-compatible with the type of the called function's definition results in undefined behavior.

    经由函数类型与被调函数定义的类型不调用兼容的表达式调用函数，行为未定义。

换句话说：**唯一被容忍的不匹配**是"表达式类型可能抛异常，被调函数实际是 `noexcept`"（注 4）。反过来——经 `noexcept` 函数类型调用一个可能抛异常的函数——是 UB，因为编译器可以假定 `noexcept` 调用不抛，省略异常表。

```cpp run title="call-compatible.cpp" flags="-std=c++2c -fsanitize=function" ub
void may_throw() {}
void nothrow() noexcept {}
void takes_int(int) {}

int main() {
    void (*p)() = nothrow;           // OK：函数指针转换去掉 noexcept
    p();                             // OK：void() 与 void() noexcept 调用兼容
    auto q = reinterpret_cast<void (*)() noexcept>(&may_throw);
    q();                             // UB: void() noexcept 与 void() 不调用兼容
    auto r = reinterpret_cast<void (*)()>(&takes_int);
    r();                             // UB: 形参列表不同
    auto s = reinterpret_cast<void (*)(int)>(r);
    s(1);                            // OK：转换回原类型再调用（[expr.reinterpret.cast#6]）
}
```

`reinterpret_cast` 转换函数指针本身是合法的（[[expr.reinterpret.cast#6]]），只有**以错误的类型调用**才是 UB。Clang 的 `-fsanitize=function` 能在运行期抓到 `r()` 这类形参不匹配，但不会报告 `noexcept` 不匹配。

!!! note "为什么不像 C 那样宽松？"
    C 允许把函数指针转换为不同类型再转回来调用，也规定以不兼容类型调用是 UB——这一点 C++ 相同。差别在于 C 的"兼容类型"概念更宽（如无原型的 `int f()`），C++ 只有"相同"和"去掉 `noexcept`"两种。现实中最常见的违例是把 `int cmp(const Foo*, const Foo*)` 强转为 `int (*)(const void*, const void*)` 传给 `qsort`——在常见 ABI 上碰巧能工作，但它是 UB，而且在启用控制流完整性（CFI）检查的构建中会被拦截。

## 形参的初始化（¶7）

### 实参与形参的对应

¶7：调用时，每个**形参**用对应的**实参**初始化（[[dcl.init]]、[[class.copy.ctor]]）——是**复制初始化**语义（[[dcl.init]] 规定"函数实参传递"是复制初始化的语境），所以 `explicit` 构造函数不会被用于隐式转换实参。随后求值每个前置断言（[[dcl.contract.func]]）。

- **显式对象成员函数**（`this` 形参，C++23，[[P0847R7]]）：若存在**隐含对象实参**（[[over.call.func]]，即 `obj.f(args)` 中的 `obj`），把它放在实参列表最前面，与第一个形参（显式对象形参）对应。
- 没有对应实参的形参使用**默认实参**（[[dcl.fct.default]]）。标准例 2 展示了一个陷阱：`template<typename... T> int f(int n = 0, T... t);` 中 `f<int>()` 非良构——显式指定了 `T = int`，第二个形参 `int t` 没有实参，也没有默认实参。

```cpp run title="explicit-object.cpp" ok
struct S {
    int v = 1;
    int get(this const S& self) { return self.v; }        // C++23 显式对象形参
    int add(this S self, int k) { return self.v + k; }    // 按值：self 是 *this 的副本
};

int main() {
    S s;
    int a = s.get();               // 隐含对象实参 s 对应 self
    int b = s.add(2);              // s 复制初始化 self；2 初始化 k
    auto pf = &S::add;             // 显式对象成员函数的地址是普通函数指针！
    int c = pf(s, 3);              // 像普通函数一样调用：没有隐含对象实参
    return (a == 1 && b == 3 && c == 4) ? 0 : 1;
}
```

### 隐式对象形参

对**隐式对象成员函数**（传统的非静态成员函数），类成员访问的对象表达式必须是 **glvalue**，隐式对象形参（[[over.match.funcs]]）用该 glvalue 初始化，"如同经显式类型转换"。注 5 解释了"如同显式转换"的用意：这个派生类到基类的转换**不再做访问检查和二义性检查**——那些检查已经在类成员访问时（[[class.member.lookup]]、[[class.access.base]]、[[expr.ref]]）做过了。prvalue 对象表达式（`S{}.f()`）会先被实质化为亡值（[[conv.rval]]）。

### 形参类型必须完整且非抽象

调用时，任何形参的类型都不得是**不完整的或抽象的类类型**。注意时机：是"调用时"而不是"声明时"——声明 `void f(Incomplete);` 是合法的，定义和调用处才要求完整。

```cpp title="incomplete-param.cpp" error
struct Inc;
struct Abs { virtual void g() = 0; };
void f(Inc);          // OK：声明时可以不完整
void h(Abs&);         // OK：引用
void k(Inc* p) {
    f(*p);            // error: 调用时形参类型 Inc 不完整
}
```

（`void f(Abs);` 这样的声明本身是合法的，只是不能定义或调用。早期标准在声明处就拒绝抽象类型的形参，后来改为只在定义和调用处检查；本机 Clang 在 `-std=c++17` 下也接受该声明，即把这一修改当作缺陷修正追溯适用。）

### 形参的销毁：实现定义的时机

!!! std
    It is implementation-defined whether a parameter is destroyed when the function in which it is defined exits or at the end of the enclosing full-expression; parameters are always destroyed in the reverse order of their construction.

    形参是在函数退出时销毁，还是在调用所在的完整表达式结束时销毁，由实现定义；但总是按构造的逆序销毁。

为什么这件事由实现定义？因为它是**调用约定**的一部分：

- **Itanium C++ ABI**（GCC、Clang 在 Linux/macOS 上）：按值传递的非平凡类对象由**调用方**构造在调用方的栈上（把地址传给被调函数），也由**调用方**在完整表达式结束时销毁。
- **MSVC ABI**：由**被调方**在函数返回前销毁形参。

两种做法都被允许，标准只好把时机定为实现定义，并保证逆序。¶7 还规定：形参的初始化和销毁都发生在**调用所在的完整表达式的上下文中**（[[intro.execution]]）。例 3 给出两个推论：

1. 形参的构造函数、转换函数、析构函数的**访问检查在调用点进行**（以调用方的权限）；
2. 若形参的构造或析构抛异常，被调函数的 *function-try-block* **不会**捕获它——因为那时还没有"进入"被调函数。

```cpp run title="param-destroy.cpp" impl
#include <cstdio>

struct P {
    const char* n;
    P(const char* n) : n(n) { std::printf("ctor %s\n", n); }
    ~P() { std::printf("dtor %s\n", n); }
};
struct T { ~T() { std::puts("dtor temp"); } };

int f(P, P) { std::puts("in f"); return 0; }
int g(int, const T&) { std::puts("in g"); return 0; }

int main() {
    g(f(P("a"), P("b")), T{});
    std::puts("next statement");
}
// Itanium ABI（本机 Clang/arm64）输出：
// ctor a / ctor b / in f / in g / dtor temp / dtor b / dtor a / next statement
// —— f 的形参直到整个完整表达式结束才销毁（在 g 返回之后）。
// 在 MSVC 上，"dtor b / dtor a" 会出现在 "in f" 之后、"in g" 之前。
// 实参 a、b 的构造顺序本身也是未指定的（¶8）。
```

!!! impl "Itanium ABI 与\"非平凡对象按值传递\""
    Itanium ABI 规定：若类有非平凡的复制构造函数、移动构造函数或析构函数（"non-trivial for the purposes of calls"），按值传递时实参对象在调用方的临时存储中构造，传递的是它的地址；被调函数中的"形参"直接就是那块存储。这也是 `std::unique_ptr<T>` 按值传递比裸指针多一次内存往返的原因——它的析构函数非平凡，无法放在寄存器里传递。Clang 提供 `[[clang::trivial_abi]]` 属性来改变这一点，代价是形参的销毁移到了被调方。

## 求值顺序（¶8）

这是 C++17 最重要的改动之一（[[P0145R3]]）。¶8 的规定：

1. **被调表达式**先序于每个实参和每个默认实参；
2. 每个形参（或者实现为保存形参值而引入的临时量）的初始化——**连同其全部值计算和副作用**——与其他形参的初始化**非决定性先序**（indeterminately sequenced）；
3. 以上这些先序于前置断言的求值，前置断言按顺序求值 {{c++26}}；
4. 若引入了保存形参值的临时量，从临时量初始化形参对象，与各前置断言之间非决定性先序 {{c++26}}。

第 2 条的措辞"连同其全部值计算和副作用"是关键：一个实参的求值**整体**作为一个单位，不会与另一个实参的求值交错。C++17 之前，实参的子表达式之间是**无序**的，于是有了著名的 `f(std::unique_ptr<A>(new A), g())` 泄漏问题——编译器可以先 `new A`、再调 `g()`（抛异常）、最后才构造 `unique_ptr`。C++17 起这个交错不再允许。

```cpp run title="unique-ptr-leak.cpp" ok
#include <memory>
#include <stdexcept>

struct A {};
int g() { throw std::runtime_error("boom"); }
void f(std::unique_ptr<A>, int) {}

int main() {
    try {
        f(std::unique_ptr<A>(new A), g());   // C++17 起不会泄漏：new A 与 unique_ptr 的构造不会被 g() 隔开
    } catch (...) {}
}
```

但实参**之间**的顺序仍然未指定。标准例 4 是一个著名的例子（来自 Stroustrup 的 *The C++ Programming Language*，被发现在 C++14 下实际有 bug）：

```cpp run title="chained-replace.cpp" ok
#include <cassert>
#include <string>

int main() {
    std::string s = "but I have heard it works even if you don't believe in it";
    s.replace(0, 4, "").replace(s.find("even"), 4, "only").replace(s.find(" don't"), 6, "");
    assert(s == "I have heard it works only if you believe in it");   // C++17 起保证成立
}
```

为什么 C++17 起保证成立？每个 `.replace(...)` 的被调表达式是 `前一个调用.replace`，按第 1 条，它（包括前一个 `replace` 调用）**先序于**本次调用的实参 `s.find(...)`。于是第二个 `find` 一定在第一个 `replace` 之后执行。C++14 下 `s.find("even")` 可能在 `replace(0, 4, "")` 之前求值，得到错误的位置。

注 8 和标准例 5 指出：以**运算符写法**调用重载运算符时，按**内置运算符**的顺序规则；以**函数调用写法**调用时，按本节规则：

```cpp run title="operator-order.cpp" unspecified
struct S { S(int) {} };
int operator<<(S, int) { return 0; }

int main() {
    int i, j;
    int x = S(i = 1) << (i = 2);          // 运算符写法：按内置 <<，左先序于右 —— i == 2
    int y = operator<<(S(j = 1), j = 2);  // 函数调用写法：两个实参非决定性先序 —— j 为 1 或 2，未指定
    return x + y + i + j;
}
```

!!! note "实际的实参求值顺序"
    标准不规定实参的求值顺序，各实现也不一致：在 x86-64 上 GCC 通常从右到左求值实参，Clang 通常从左到右（本页 `param-destroy.cpp` 在 Clang 上先构造 `a`）。这是 ABI 和寄存器分配的历史产物。P0145 的早期版本曾提议规定从左到右，最终只采纳了"非决定性先序"——保证不交错，但不保证次序。

!!! lawyer "常量求值中的顺序"
    [[intro.execution#16]] 规定：作为核心常量表达式求值时，原本无序或非决定性先序的操作数与子表达式**按词法顺序**求值，默认实参也按"如同实参存在"的位置求值。这让常量求值的结果与实现无关。

## 调用的结果（¶9）与后置断言（¶10）

¶9：函数调用的结果，是使控制流离开被调函数的 `return` 语句的（可能经过转换的）操作数的结果（[[stmt.return]]）。唯一的额外转换：虚调用中若最终覆盖者的返回类型与静态选中函数不同（协变），返回值被转换为静态选中函数的返回类型——前面 `covariant.cpp` 中 `D*` 到 `B*` 的转换就发生在这里，包括必要的指针调整。

¶10 {{c++26}}：被调函数**正常退出**时，按顺序求值全部后置断言。若实现引入了保存返回值的临时量（[[class.temporary]]），后置断言与这些临时量（或结果对象）的初始化非决定性先序；所有后置断言**先序于形参的销毁**——所以后置条件可以引用（`const` 的）形参。

¶11 是注：函数可以修改它的非 `const` 形参，但除非形参是引用，这不影响实参；`const T&` 形参可能绑定到一个临时量。

## 可变实参（¶12–13）

¶12：函数可以声明为接受比形参**更少**的实参（默认实参）或**更多**的实参（省略号 `...` 或函数形参包）。

¶13：**没有对应形参的实参**（即匹配 `...` 的实参）以一种接收方能用 `va_arg`（[[support.runtime]]）取出的方式传递。注 11 说明函数形参包不受此影响：包在实例化时展开，每个实参都有对应的形参。对 `...` 实参：

1. 施行左值到右值、数组到指针、函数到指针转换；
2. `std::nullptr_t` 类型的实参转换为 `void*`；
3. 转换后若不是算术、枚举、指针、成员指针或类类型，**非良构**；
4. 传递**潜在求值**的、**有作用域枚举**类型的实参，或具有资格的非平凡复制/移动构造函数或非平凡析构函数的**类类型**实参，是**有条件支持**的（conditionally-supported），语义由实现定义；
5. **[[g:default-argument-promotions|默认实参提升]]**（default argument promotions）：可整型提升的整型/枚举做整型提升（[[conv.prom]]），`float` 提升为 `double`（[[conv.fpprom]]）。

```cpp run title="varargs.cpp" ok
#include <cstdarg>
#include <cstdio>

void show(int n, ...) {
    std::va_list ap;
    va_start(ap, n);
    double d = va_arg(ap, double);   // float 被提升为 double —— 不能写 va_arg(ap, float)
    int c = va_arg(ap, int);         // char 被提升为 int
    void* p = va_arg(ap, void*);     // nullptr 被转换为 void*
    std::printf("%g %c %p\n", d, c, p);
    va_end(ap);
}

int main() { show(3, 1.5f, 'x', nullptr); }
```

为什么要有默认实参提升？这是从 K&R C 继承的：没有原型时，被调方不知道实参类型，于是约定所有"小"类型都按 `int`/`double` 传递，接收方只需处理少数几种宽度。这也是 `printf("%f", 1.0f)` 能工作、而 `va_arg(ap, float)` 是 UB 的原因（[[support.runtime]] 要求 `va_arg` 的类型与提升后的类型兼容）。

为什么非平凡类对象经 `...` 传递是"有条件支持"？因为 `va_arg` 只能按字节搬运，而非平凡对象需要调用复制构造和析构函数，标准没有办法规定它们何时、由谁调用。实现可以拒绝，也可以给出某种语义：

- **Clang**：默认报错 `cannot pass object of non-trivial type ... through variadic function; call will abort at runtime`（这个诊断由 `-Wnon-pod-varargs` 控制，默认是错误级别）；
- **GCC**：接受（可用 `-Wconditionally-supported` 得到警告），按传递一个副本的语义实现；
- 有作用域枚举经 `...` 传递，本机 Clang 静默接受（按其底层类型传递）。

"潜在求值"这个限定很重要：在**未求值操作数**中（`sizeof`、`decltype`）经 `...` 传递非平凡对象完全没问题，所以经典的 SFINAE 技巧 `decltype(check(std::declval<T>()))`（`check(...)` 作为兜底重载）不受影响。

```cpp title="varargs-nontrivial.cpp" error
#include <string>
void v(int, ...);

void f() {
    std::string s;
    v(1, s);                    // error（Clang）：有条件支持，Clang 不支持
    using R = decltype(v(1, s));  // OK：未求值操作数，不受限制
    v(1, f);                    // OK：函数到指针转换后是函数指针
}
```

## 递归（¶14）与 `main`

¶14：允许递归调用，**但 `main` 除外**。[[basic.start.main]] 更进一步规定 `main` 不得在程序中被使用（不能调用、不能取地址）。Clang 把 `return main();` 作为扩展接受并给出 `-Wmain` 警告；GCC 在 `-pedantic` 下也会警告。

## 调用表达式的值类别（¶15）

| 返回类型 | 调用表达式的值类别 | 例 |
|---|---|---|
| 左值引用 `T&` | lvalue | `v.front()`、`std::cout << x` |
| 函数的右值引用 `F&&` | lvalue | 罕见 |
| 对象的右值引用 `T&&` | **xvalue** | `std::move(x)`、`std::forward<T>(t)` |
| 非引用类型 | prvalue | `f()`、`std::string()` |

这张表就是 `std::move` 的全部魔法：`std::move` 只是一个返回 `T&&` 的函数，按 ¶15 其调用是亡值；它本身什么都不移动。详见 [[topics/value-categories]]。

¶15 后半：若调用是**非 `void` 的 prvalue**，其类型必须**完整**——[[dcl.type.decltype]] 规定的情形除外。那个例外是：作为 `decltype` 的操作数（或其逗号右操作数）的函数调用，不要求返回类型完整，也不引入临时量（不检查析构函数）。这让元编程可以对返回不完整类型的函数做类型推导。

```cpp title="incomplete-return.cpp" error
struct I;
I make();
I& make_ref();

using T = decltype(make());   // OK：decltype 例外
void h() {
    make_ref();               // OK：返回引用，是左值，不要求完整
    make();                   // error: prvalue 的类型 I 不完整
}
```

## 历史与演进

!!! history
    - **C++98**：实参、被调表达式之间的求值无序；形参销毁时机实现定义；非 POD 类经 `...` 传递是 UB。
    - **C++11**：非平凡类经 `...` 改为"有条件支持、实现定义语义"；引入右值引用后 ¶15 增加 xvalue 一栏；`std::nullptr_t` 经 `...` 转为 `void*`。
    - **C++17**：[[P0145R3]] 规定被调表达式先序于实参、实参之间非决定性先序；`noexcept` 成为函数类型的一部分（[[P0012R1]]），随之出现"经 `noexcept` 类型调用潜在抛出函数"的问题和 ¶6 的处理。
    - **C++20**：伪析构函数调用结束标量对象的生命周期（[[P0593R6]]）。
    - **C++23**：显式对象形参（[[P0847R7]]）。
    - **C++26**：契约断言的求值顺序（¶5、¶8、¶10，[[P2900R14]]）；"调用兼容"一词的引入使 ¶6 更清晰。

## 陷阱

!!! pitfall "`f(i++, i++)` 不是 UB，但也别写"
    C++17 起两次修改非决定性先序，结果未指定（`f(0,1)` 或 `f(1,0)`），不再是 UB。编译器的 `-Wunsequenced`（Clang）或 `-Wsequence-point`（GCC）仍会警告，措辞沿用了旧标准的"unsequenced"。

!!! pitfall "形参析构时机影响 RAII 守卫"
    `lock(Guard{m}), work();` 这类依赖"形参在函数返回时析构"的代码在 Itanium ABI 上会把守卫的析构推迟到整个完整表达式结束。任何依赖形参析构时机的代码都不可移植。

!!! pitfall "成员函数指针不能直接调用"
    `pmf(obj)` 非良构：成员函数指针不是函数指针，被调表达式必须是 `(obj.*pmf)` 或 `(ptr->*pmf)`，注意括号——`obj.*pmf()` 会被解析为 `obj.*(pmf())`。`std::invoke(pmf, obj)` 统一了这些写法。显式对象成员函数例外：它的地址是普通函数指针。

!!! pitfall "`va_arg(ap, float)`、`va_arg(ap, char)`、`va_arg(ap, bool)` 都是错的"
    这些类型会被提升，`va_arg` 必须用提升后的类型（`double`、`int`）。

## 思考题

!!! question "思考题 1"
    下面的程序输出什么？`std::cout << f() << g();` 与 `operator<<(operator<<(std::cout, f()), g());` 在 C++17 下的区别是什么？

<details markdown="1">
<summary>答案</summary>

运算符写法按内置 `<<` 的顺序规则（[[expr.shift]]：左操作数先序于右操作数），且外层调用的被调表达式与左操作数 `std::cout << f()` 都先序于 `g()`，所以 `f()` 一定在 `g()` 之前。函数调用写法下，外层 `operator<<` 的两个实参——`operator<<(std::cout, f())` 与 `g()`——非决定性先序，`g()` 可能先于 `f()` 执行。注 8 正是为此而写。
</details>

!!! question "思考题 2"
    `void (*p)() noexcept = nullptr; void (*q)() = p;` 合法吗？反过来 `void (*r)() noexcept = q;` 呢？若用 `reinterpret_cast` 强行转换并调用，何时是 UB？

<details markdown="1">
<summary>答案</summary>

`q = p` 合法：函数指针转换（[[conv.fctptr]]）可以去掉 `noexcept`。`r = q` 非良构：不存在加上 `noexcept` 的隐式转换。`reinterpret_cast` 可以做这个转换（[[expr.reinterpret.cast#6]]），之后经 `r` 调用时，若被调函数的定义不是 `noexcept` 的，则 `void() noexcept` 与 `void()` 不调用兼容（"指向 `void()` 的指针"不能经函数指针转换变成"指向 `void() noexcept` 的指针"），按 ¶6 为 UB；若被调函数恰好是 `noexcept` 的，则类型相同，合法。
</details>

!!! question "思考题 3"
    `struct S { void f() &&; }; S s;` 下，`std::move(s).f()` 中隐式对象形参是如何初始化的？`S().f()` 呢？

<details markdown="1">
<summary>答案</summary>

¶7：隐式对象成员函数调用中，对象表达式必须是 glvalue，用它初始化隐式对象形参（类型为 `S&&`）。`std::move(s)` 本身是亡值 glvalue，直接绑定。`S()` 是 prvalue，作为类成员访问的对象表达式时先施行临时量实质化（[[expr.ref#2]] 要求访问非静态成员时对象表达式是 glvalue；[[basic.lval]] 规定期望 glvalue 处的 prvalue 被实质化），得到亡值后绑定到 `S&&`。
</details>

## 小结

!!! summary
    | 方面 | 规则 |
    |---|---|
    | 被调表达式 | 函数左值（不退化）或函数指针 prvalue；非静态成员函数经成员访问 |
    | 虚调用 | 非限定名、虚函数 ⇒ 调用动态类型的最终覆盖者；类型取静态选中函数的返回类型 |
    | 类型不符 | 只容许"表达式类型可能抛出、被调函数 `noexcept`"；其他不调用兼容 ⇒ UB |
    | 形参初始化 | 复制初始化；显式对象形参接收隐含对象实参；调用时形参类型须完整、非抽象 |
    | 形参销毁 | 函数退出时或完整表达式末尾，实现定义；总是逆序；在调用方上下文中检查访问 |
    | 求值顺序 | 被调表达式 → 各实参（彼此非决定性先序、不交错）→ 前置断言 → 函数体 → 后置断言 → 形参销毁 |
    | `...` 实参 | 左值到右值等转换 + 默认实参提升；非平凡类 / 有作用域枚举有条件支持 |
    | 值类别 | `T&` ⇒ lvalue；`T&&`（对象）⇒ xvalue；非引用 ⇒ prvalue（须完整，`decltype` 除外） |
