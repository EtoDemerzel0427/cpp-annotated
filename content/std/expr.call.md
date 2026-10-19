---
title: 函数调用
summary: 函数调用表达式在选定函数之后的全部语义：什么能被调用、虚调用、结果的类型与值类别、形参的初始化与销毁、C++17 的求值顺序、可变实参与默认实参提升、经错误函数类型调用的 UB，以及 C++26 契约断言的求值次序。
status: done
papers: P0145R3, P0847R7, P2900R14, P0012R1, P0593R6
related: intro.execution, over.match.call, over.call.func, dcl.fct, dcl.fct.default, dcl.contract.func, class.temporary, stmt.return, conv.fctptr, class.cdtor, support.runtime, basic.lval
tags: 表达式, 函数调用, 求值顺序, 可变实参, 契约, UB
updated: 2026-10-19
---

!!! tldr
    - 返回左值引用的调用是左值，返回对象右值引用的是亡值，其余是 prvalue；`std::move` 正是靠这条规则产生亡值。
    - C++17 起，被调表达式先于所有实参求值；各形参的初始化彼此不交错，但谁先谁后不规定。
    - 形参在函数返回时销毁，还是在调用所在的完整表达式结束时销毁，由实现定义；GCC 和 Clang 在常见平台上是后者。
    - 经 `...` 传递的实参要做默认实参提升：`float` 变 `double`，`char`、`short` 变 `int`。
    - 用类型不匹配的函数指针调用函数是 UB，唯一允许的不匹配是去掉 `noexcept`。

```cpp run title="chained-replace.cpp" ok
#include <cassert>
#include <string>

int main() {
    std::string s = "but I have heard it works even if you don't believe in it";
    s.replace(0, 4, "").replace(s.find("even"), 4, "only").replace(s.find(" don't"), 6, "");
    assert(s == "I have heard it works only if you believe in it");   // C++17 起保证成立
}
```

这是标准例 4。它出自一本流行的 C++ 教材，后来有人发现它在 C++14 下并不保证正确：第二个 `s.find("even")` 可能在第一个 `replace` 之前求值，得到错误的位置。C++17 起它一定成立，依据是 [[expr.call#8]] 的求值顺序。

运算符重载、构造函数、lambda、`std::invoke` 最终都归结为一次函数调用。名字指向重载集时选哪个函数，由重载决议（[[over.match.call]]）决定；[expr.call] 规定的是选定函数之后的事。

## 什么能被调用（¶1–¶3）

¶1 函数调用是后缀表达式后跟圆括号，括号里是可能为空、逗号分隔的 *initializer-clause* 列表，它们是函数的**实参**（arguments）。实参可以是花括号列表 `f({1, 2})` 或包展开 `f(xs...)`。

括号前的后缀表达式（下称被调表达式）必须是函数类型或函数指针类型。调用非成员函数或静态成员函数时，被调表达式要么是指代函数的左值，这时不做函数到指针转换（[[conv.func]]）；要么是函数指针类型的 prvalue。

```cpp run title="callee-forms.cpp" ok
int f(int x) { return x + 1; }

int main() {
    int (&rf)(int) = f;
    int (*pf)(int) = f;
    int a = f(1);        // 指代函数的左值
    int b = rf(1);       // 函数左值（经引用）
    int c = pf(1);       // 函数指针 prvalue（pf 先做左值到右值转换）
    int d = (*pf)(1);    // *pf 是函数左值
    int e = (**********pf)(1);   // 每个 * 得到函数左值，再退化为指针，仍然合法
    return (a + b + c + d + e == 10) ? 0 : 1;
}
```

调用非静态成员函数时，被调表达式是类成员访问 `E1.E2`，或者隐式的 `(*this).E2`。按 [[expr.ref#8]]，这时的 `E1.E2` 是只能立即调用的 prvalue；成员指针形式 `(obj.*pmf)(args)` 同理（[[expr.mptr.oper]]）。

¶2 如果选中的函数不是虚函数，或者成员访问里写的是限定名（`p->Base::f()`），调用的就是这个函数。否则调用对象表达式[[g:dynamic-type|动态类型]]中该函数的[[g:final-overrider|最终覆盖函数]]（[[class.virtual]]），这叫做[[g:virtual-function-call|虚函数调用]]。注 2 补充，对正在构造或析构的对象，虚调用的行为由 [[class.cdtor]] 规定。

```cpp run title="virtual-call.cpp" ok
struct B { virtual int f() { return 1; } };
struct D : B { int f() override { return 2; } };

int main() {
    D d;
    B& b = d;
    int x = b.f();        // 虚调用：D::f，得到 2
    int y = b.B::f();     // 限定名：不是虚调用，B::f，得到 1
    int (B::*pmf)() = &B::f;
    int z = (b.*pmf)();   // 经成员指针调用虚函数：仍然分派到 D::f
    return (x == 2 && y == 1 && z == 2) ? 0 : 1;
}
```

¶3 是注：使用函数名而名字查找找不到声明时，程序非良构，调用不会隐式声明函数。C89 则会把未声明的 `foo()` 当作 `int foo()`。

## 调用的结果（¶4、¶9、¶15）

### 值类别（¶15）

¶15 调用表达式的值类别由返回类型决定：

| 返回类型 | 值类别 | 例子 |
|---|---|---|
| 左值引用 `T&` | 左值 | `v.front()`、`std::cout << x` |
| 函数的右值引用 `F&&` | 左值 | 很少见 |
| 对象的右值引用 `T&&` | 亡值 | `std::move(x)`、`std::forward<T>(t)` |
| 非引用类型 | prvalue | `f()`、`std::string()` |

`std::move` 只是一个返回 `T&&` 的函数，按这张表它的调用是亡值，它本身不移动任何东西。详见 [[topics/value-categories]]。

如果调用是非 `void` 的 prvalue，它的类型必须完整，[[dcl.type.decltype]] 规定的情形除外：作为 `decltype` 操作数的函数调用不要求返回类型完整，也不引入临时量。元编程因此可以对返回不完整类型的函数做类型推导。

```cpp title="incomplete-return.cpp" error
struct I;
I make();
I& make_ref();

using T = decltype(make());   // OK：decltype 的例外
void h() {
    make_ref();               // OK：返回引用，结果是左值
    make();                   // error: prvalue 的类型 I 不完整
}
```

### 类型取静态选中的函数（¶4、¶9）

¶4 调用表达式的类型是静态选中的函数（不考虑 `virtual`）的返回类型，即使实际调用的函数返回类型不同。这对应协变返回类型。¶9 补充，调用的结果是让控制离开被调函数的 `return` 语句的操作数（可能经过转换，[[stmt.return]]）；虚调用中最终覆盖函数的返回类型不同时，返回值再转换为静态选中函数的返回类型，包括必要的指针调整。

```cpp run title="covariant.cpp" ok
#include <type_traits>

struct B { virtual B* clone() const { return new B(*this); } virtual ~B() = default; };
struct D : B { D* clone() const override { return new D(*this); } };

int main() {
    D d;
    const B& b = d;
    static_assert(std::is_same_v<decltype(b.clone()), B*>);   // 静态选中 B::clone
    static_assert(std::is_same_v<decltype(d.clone()), D*>);   // 静态选中 D::clone
    B* p = b.clone();     // 实际调用 D::clone，返回的 D* 转换为 B*（¶9）
    delete p;
}
```

### 析构函数与伪析构函数（¶4）

被调表达式指代析构函数或伪析构函数（[[expr.prim.id.dtor]]）时，调用的类型是 `void`。伪析构函数是标量类型的析构函数写法，例如 `T` 为 `int` 时的 `p->~T()`。调用它会销毁对象表达式所指的标量对象，也就是结束它的生命周期（[[basic.life]]）。这条规定是 C++20 由 [[P0593R6]] 加入的，此前伪析构函数调用没有任何效果。

```cpp run title="pseudo-dtor.cpp" ok
#include <new>

template<class T> void destroy(T* p) { p->~T(); }   // T 为 int 时是伪析构函数调用

int main() {
    int x = 1;
    destroy(&x);          // C++20 起：x 的生命周期结束
    ::new (&x) int(2);    // 在原存储上重新创建一个 int，之后仍可用名字 x
    return x == 2 ? 0 : 1;
}
```

## 形参的初始化（¶7）

### 实参与形参的对应

¶7 调用时，每个形参用对应的实参初始化（[[dcl.init]]、[[class.copy.ctor]]）。这是复制初始化，所以 `explicit` 构造函数不能用来隐式转换实参。没有对应实参的形参使用默认实参（[[dcl.fct.default]]）。

标准例 2 是一个容易掉进去的情形：

```cpp title="default-arg-pack.cpp" error
template<typename... T> int f(int n = 0, T... t);
int x = f<int>();   // error: 第二个形参没有实参
```

显式指定 `T` 为 `int` 后，第二个形参 `int t` 既没有实参，也没有默认实参。

C++23 的显式对象成员函数（[[P0847R7]]）有一个显式的对象形参。如果调用时有隐含的对象实参，也就是 `obj.f(args)` 中的 `obj`（[[over.call.func]]），就把它放在实参列表最前面，与显式对象形参对应。

```cpp run title="explicit-object.cpp" ok
struct S {
    int v = 1;
    int get(this const S& self) { return self.v; }
    int add(this S self, int k) { return self.v + k; }    // 按值：self 是副本
};

int main() {
    S s;
    int a = s.get();               // 隐含对象实参 s 对应 self
    int b = s.add(2);              // s 复制初始化 self，2 初始化 k
    auto pf = &S::add;             // 显式对象成员函数的地址是普通函数指针
    int c = pf(s, 3);              // 像普通函数一样调用
    return (a == 1 && b == 3 && c == 4) ? 0 : 1;
}
```

传统的非静态成员函数有一个隐式对象形参（[[over.match.funcs]]）。调用时，成员访问的对象表达式必须是 glvalue，隐式对象形参用这个 glvalue 初始化，如同经过显式类型转换。注 5 解释了这样写的原因：派生类到基类的这次转换不再做访问检查和二义性检查，因为成员访问时已经检查过了（[[class.member.lookup]]、[[class.access.base]]、[[expr.ref]]）。

### 形参类型必须完整且不是抽象类

调用时，形参类型不能是不完整的或抽象的类类型。注 6 说明，形参是这些类型的指针或引用仍然可以。检查发生在调用处，声明 `void f(Incomplete);` 本身是合法的。

```cpp title="incomplete-param.cpp" error
struct Inc;
struct Abs { virtual void g() = 0; };
void f(Inc);          // OK：声明时可以不完整
void a(Abs);          // OK：声明本身合法，只是不能定义或调用
void k(Inc* p) {
    f(*p);            // error: 调用时形参类型 Inc 不完整
}
```

## 求值顺序（¶8）

¶8 C++17 的求值顺序提案 [[P0145R3]] 确立了下面几条：

1. 被调表达式先序于每个实参和每个默认实参。
2. 每个形参的初始化，连同其中全部的值计算和副作用，与其他形参的初始化[[g:indeterminately-sequenced|非决定性先序]]：有先后，但不规定谁先。如果实现引入临时量来保存形参的值，说的就是这些临时量的初始化。
3. 以上全部先序于前置断言的求值，前置断言依次求值 {{c++26}}。
4. 如果引入了保存形参值的临时量，用临时量初始化形参对象，与各前置断言之间非决定性先序 {{c++26}}。

注 7 补充，实参求值的所有副作用都在进入函数之前完成。

开头的 `replace` 链用的是第 1 条。每个 `.replace(...)` 的被调表达式是"前一次调用 `.replace`"，它包含前一次调用本身，所以先于本次的实参 `s.find(...)`。于是每个 `find` 都在前一个 `replace` 之后执行。

第 2 条里"连同全部值计算和副作用"的意思是，一个实参的求值作为整体进行，不会和另一个实参的求值交错。C++17 之前没有这个保证，`f(std::unique_ptr<A>(new A), g())` 可能先执行 `new A`，再调用 `g()`，最后才构造 `unique_ptr`；`g()` 抛出异常时内存就泄漏了。

```cpp run title="unique-ptr-leak.cpp" ok
#include <memory>
#include <stdexcept>

struct A {};
int g() { throw std::runtime_error("boom"); }
void f(std::unique_ptr<A>, int) {}

int main() {
    try {
        f(std::unique_ptr<A>(new A), g());   // C++17 起不会泄漏
    } catch (...) {}
}
```

实参之间的先后仍然不规定。各实现也不一致：在 x86-64 上 GCC 通常从右往左求值实参，Clang 通常从左往右。P0145 的早期版本曾提议规定从左往右，最后只采纳了"不交错、不定序"。

### 运算符写法与函数写法

注 8 指出，用运算符写法调用重载运算符时，实参按内置运算符的顺序求值（[[over.match.oper]]）；用函数调用写法时，按本节的规则。标准例 5：

```cpp run title="operator-order.cpp" unspecified
struct S { S(int) {} };
int operator<<(S, int) { return 0; }

int main() {
    int i, j;
    int x = S(i = 1) << (i = 2);          // 运算符写法：按内置 <<，左先于右，i 为 2
    int y = operator<<(S(j = 1), j = 2);  // 函数写法：j 为 1 还是 2 未指定
    return x + y + i + j;
}
```

本机 Clang 23 对第二行报 `-Wunsequenced`。这个措辞在 C++17 下不准确，两个实参是非决定性先序，不是无序，结果未指定而不是 UB。

!!! lawyer "常量求值中的顺序"
    [[intro.execution#16]] 规定，作为核心常量表达式求值时，原本无序或非决定性先序的子表达式按词法顺序求值，默认实参也按它们出现在实参位置时的顺序求值。所以常量求值的结果不依赖于实现。

## 形参何时销毁（¶7）

!!! std
    It is implementation-defined whether a parameter is destroyed when the function in which it is defined exits or at the end of the enclosing full-expression; parameters are always destroyed in the reverse order of their construction.

¶7 形参在函数退出时销毁，还是在调用所在的完整表达式结束时销毁，由实现定义；无论哪种，都按构造的逆序销毁。

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
// 本机 Clang 23（arm64，Itanium ABI）输出：
// ctor a / ctor b / in f / in g / dtor temp / dtor b / dtor a / next statement
// f 的形参直到整个完整表达式结束才销毁，在 g 返回之后。
```

这件事由实现定义，是因为它属于调用约定。Itanium C++ ABI（Linux、macOS 上的 GCC 和 Clang）中，按值传递的非平凡类对象由调用方构造在自己的栈上，把地址传给被调函数，也由调用方在完整表达式结束时销毁。MSVC 的 ABI 则由被调函数在返回前销毁形参，上例的 `dtor b`、`dtor a` 会出现在 `in f` 之后、`in g` 之前。

¶7 还规定，形参的初始化和销毁都发生在调用所在的完整表达式的上下文中（[[intro.execution]]）。例 3 给出两个推论：

1. 形参的构造函数、转换函数、析构函数的访问检查在调用处进行，按调用方的权限。
2. 形参的构造或析构抛出的异常不会被被调函数的 *function-try-block* 捕获，因为那时还不在被调函数里。

!!! impl "Itanium ABI 中非平凡对象的按值传递"
    如果一个类有非平凡的复制构造函数、移动构造函数或析构函数，Itanium ABI 按值传递它时，实参在调用方的临时存储中构造，传递的是地址，被调函数的形参直接就是那块存储。所以按值传递 `std::unique_ptr<T>` 比传裸指针多一次内存读写：它的析构函数非平凡，不能放在寄存器里传。Clang 的 `[[clang::trivial_abi]]` 属性可以改变这一点，代价是形参改由被调函数销毁。

## 可变实参（¶12–¶13）

¶12 函数可以声明成接受比形参少的实参（默认实参），或者比形参多的实参（省略号 `...` 或函数形参包）。

```cpp run title="varargs.cpp" ok
#include <cstdarg>
#include <cstdio>

void show(int n, ...) {
    std::va_list ap;
    va_start(ap, n);
    double d = va_arg(ap, double);   // float 被提升为 double，不能写 va_arg(ap, float)
    int c = va_arg(ap, int);         // char 被提升为 int
    void* p = va_arg(ap, void*);     // nullptr 被转换为 void*
    std::printf("%g %c %p\n", d, c, p);
    va_end(ap);
}

int main() { show(3, 1.5f, 'x', nullptr); }
```

¶13 没有对应形参的实参，也就是匹配 `...` 的实参，以接收方能用 `va_arg`（[[support.runtime]]）取出的方式传递。注 11 说明这不涉及函数形参包：包在实例化时展开，每个实参都有对应的形参。对 `...` 实参依次做下面这些处理：

1. 做左值到右值、数组到指针、函数到指针转换；`std::nullptr_t` 转换为 `void*`。
2. 转换后不是算术、枚举、指针、成员指针或类类型的，程序非良构。
3. 传递潜在求值的、有作用域枚举类型的实参，或者有非平凡复制、移动构造函数或非平凡析构函数的类类型实参，是[[g:conditionally-supported|有条件支持]]的，语义由实现定义。
4. 可以做整型提升的整型和枚举做整型提升（[[conv.prom]]），`float` 提升为 `double`（[[conv.fpprom]]）。这叫做[[g:default-argument-promotions|默认实参提升]]。

默认实参提升来自 K&R C。没有原型时被调方不知道实参的类型，于是约定较窄的类型一律按 `int` 或 `double` 传递。这就是 `printf("%f", 1.0f)` 能工作、而 `va_arg(ap, float)` 是 UB 的原因：`va_arg` 的类型必须与提升后的类型兼容。

非平凡类对象经 `...` 传递只是有条件支持，因为 `va_arg` 只能按字节搬运，而非平凡对象需要调用复制构造函数和析构函数，标准无法规定由谁、在什么时候调用。

```cpp title="varargs-nontrivial.cpp" error
#include <string>
void v(int, ...);

void f() {
    std::string s;
    v(1, s);                      // error（Clang）：Clang 不支持这种用法
    using R = decltype(v(1, s));  // OK：不求值操作数，不受限制
    v(1, f);                      // OK：函数到指针转换后是函数指针
}
```

本机 Clang 23 对 `v(1, s)` 报错 cannot pass object of non-trivial type through variadic function（由 `-Wnon-pod-varargs` 控制，默认是错误级别）。GCC 接受并传递一个副本，加 `-Wconditionally-supported` 可以得到警告。有作用域枚举经 `...` 传递时，本机 Clang 不给任何诊断。

限定在潜在求值是有意的：在 `sizeof`、`decltype` 这类不求值操作数里经 `...` 传递非平凡对象没有问题，所以 `decltype(check(std::declval<T>()))` 这类以 `check(...)` 兜底的 SFINAE 写法不受影响。

## 经不兼容的函数类型调用：UB（¶6）

¶6 先定义一个词：如果函数类型 `Tcall` 与 `Tfunc` 相同，或者"指向 `Tfunc` 的指针"能经函数指针转换（[[conv.fctptr]]，即去掉 `noexcept`）变成"指向 `Tcall` 的指针"，就说 `Tcall` 与 `Tfunc` [[g:call-compatible|调用兼容]]。

!!! std
    Calling a function through an expression whose function type is not call-compatible with the type of the called function's definition results in undefined behavior.

换句话说，唯一允许的不匹配是表达式的类型可能抛异常、而被调函数实际是 `noexcept`（注 4）。反过来，经 `noexcept` 函数类型调用一个可能抛异常的函数是 UB，因为编译器可以假定这次调用不抛异常，省掉异常处理的代码。

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
    s(1);                            // OK：转换回原类型再调用
}
```

用 `reinterpret_cast` 转换函数指针本身合法（[[expr.reinterpret.cast#6]]），用错误的类型调用才是 UB。本机 Clang 23 的 `-fsanitize=function` 在运行时报告了 `r()`，没有报告 `noexcept` 不匹配的 `q()`。

C 同样规定以不兼容类型调用是 UB，只是 C 的兼容类型概念更宽。现实中最常见的违例是把 `int cmp(const Foo*, const Foo*)` 强转为 `int (*)(const void*, const void*)` 传给 `qsort`。它在常见 ABI 上碰巧能工作，但它是 UB，启用控制流完整性（CFI）检查的构建会拦下它。

## 契约断言的次序（¶5、¶10）{{c++26}}

C++26 允许在函数声明上写前置断言 `pre` 和后置断言 `post`（[[dcl.contract.func]]，[[P2900R14]]）。¶5 规定一次调用要检查哪些断言、按什么顺序：

| 列表项 | 断言 |
|---|---|
| ¶5.1 | 如果被调表达式是类成员访问且这是虚调用：静态选中函数的前置断言 |
| ¶5.2 | 实际调用的函数的前置断言 |
| ¶5.3 | 实际调用的函数的后置断言 |
| ¶5.4 | 如果被调表达式是类成员访问且这是虚调用：静态选中函数的后置断言 |

调用方看到的是静态类型的接口，它的契约要检查；覆盖函数自己的契约也要检查。前置断言从接口到实现，后置断言从实现回到接口，形成对称的嵌套。标准例 1 的要点：

```cpp title="contracts-virtual.cpp"
struct X1 { virtual void f() pre(a) post(b) {} };
struct Y : X1 { void f() override pre(e) post(f) {} };

void t(Y& y) {
    X1& x = y;
    x.f();          // 虚调用：a, e, f, b
    x.X1::f();      // 限定名，不是虚调用：a, b
    y.f();          // 静态选中的就是 Y::f：e, f
    void (X1::*pmf)() = &X1::f;
    (x.*pmf)();     // 经成员指针调用：只有 e, f
}
```

最后一行容易看错。¶5.1 和 ¶5.4 只在被调表达式是类成员访问时才加上静态选中函数的断言，`.*` 不是类成员访问，所以只检查实际调用的函数的断言。本机 Clang 23 还不支持契约语法，这个例子没有经过编译验证。

¶10 被调函数正常返回时，依次求值全部后置断言。如果实现引入了保存返回值的临时量（[[class.temporary]]），后置断言与这些临时量或结果对象的初始化之间非决定性先序。所有后置断言都先序于形参的销毁，所以后置条件可以引用形参。

## 其余条文

¶11 是注：函数可以修改它的非 `const` 形参，但除非形参是引用，实参不受影响；`const T&` 形参在需要时会绑定到一个临时量。

¶14 允许递归调用，`main` 除外。[[basic.start.main]] 更进一步，规定程序中不得使用 `main`。本机 Clang 23 把 `return main();` 作为扩展接受，给出 `-Wmain` 警告。

## 历史与演进

!!! history
    - C++11：非平凡类经 `...` 传递从 UB 改为有条件支持；有了右值引用，¶15 增加了亡值一栏；`std::nullptr_t` 经 `...` 传递时转换为 `void*`。
    - C++17：被调表达式先于实参、实参之间不交错（[[P0145R3]]）；`noexcept` 成为函数类型的一部分（[[P0012R1]]），由此出现了经 `noexcept` 类型调用可能抛异常的函数的问题，¶6 处理的就是它。
    - C++20：伪析构函数调用结束标量对象的生命周期（[[P0593R6]]）。
    - C++23：显式对象形参（[[P0847R7]]）。
    - C++26：契约断言的求值次序（¶5、¶8、¶10，[[P2900R14]]）。

## 常见误解

!!! pitfall "`f(i++, i++)` 是 UB"
    C++17 起两次修改非决定性先序，结果未指定，是 `f(0, 1)` 或 `f(1, 0)`，不是 UB。Clang 的 `-Wunsequenced` 和 GCC 的 `-Wsequence-point` 仍会警告，这类代码也确实不该写。

!!! pitfall "按值传递的 RAII 对象在函数返回时析构"
    在 Itanium ABI 上，按值传递的守卫对象要到整个完整表达式结束才析构。依赖形参析构时机的代码不可移植。

!!! pitfall "成员函数指针可以直接调用"
    `pmf(obj)` 非良构，成员函数指针不是函数指针，要写 `(obj.*pmf)()` 或 `(ptr->*pmf)()`。括号不能省，`obj.*pmf()` 会被解析为 `obj.*(pmf())`。`std::invoke(pmf, obj)` 统一了这些写法。显式对象成员函数是例外，它的地址就是普通函数指针。

## 思考题

!!! question "思考题 1"
    C++17 下，`std::cout << f() << g();` 与 `operator<<(operator<<(std::cout, f()), g());` 有什么区别？

<details markdown="1">
<summary>答案</summary>

运算符写法按内置 `<<` 的顺序规则，左操作数先序于右操作数（[[expr.shift]]），所以 `f()` 一定先于 `g()`。函数调用写法中，外层 `operator<<` 的两个实参 `operator<<(std::cout, f())` 和 `g()` 非决定性先序，`g()` 可能先执行。注 8 说的就是这个区别。
</details>

!!! question "思考题 2"
    `void (*p)() noexcept = nullptr; void (*q)() = p;` 合法吗？反过来 `void (*r)() noexcept = q;` 呢？用 `reinterpret_cast` 强行转换再调用，什么时候是 UB？

<details markdown="1">
<summary>答案</summary>

`q = p` 合法，函数指针转换可以去掉 `noexcept`（[[conv.fctptr]]）。`r = q` 非良构，没有加上 `noexcept` 的隐式转换。`reinterpret_cast` 可以完成这个转换（[[expr.reinterpret.cast#6]]）。之后经 `r` 调用时，如果被调函数的定义不是 `noexcept`，"指向 `void()` 的指针"不能经函数指针转换变成"指向 `void() noexcept` 的指针"，两者不调用兼容，按 ¶6 是 UB；如果被调函数恰好是 `noexcept` 的，类型相同，没有问题。
</details>

!!! question "思考题 3"
    `struct S { void f() &&; }; S s;` 下，`std::move(s).f()` 中的隐式对象形参是怎样初始化的？`S().f()` 呢？

<details markdown="1">
<summary>答案</summary>

按 ¶7，对象表达式必须是 glvalue，用它初始化类型为 `S&&` 的隐式对象形参。`std::move(s)` 本身是亡值，直接绑定。`S()` 是 prvalue，而 ¶7 要求 glvalue，于是先做临时量实质化（[[conv.rval]]），得到亡值后绑定到 `S&&`。
</details>
