---
title: 析构函数
summary: 预期析构函数与析构函数的选择、隐式声明与定义、何时被删除、何时平凡、析构顺序、何时被隐式调用与"潜在调用"、虚析构函数与 operator delete 的查找（Itanium D0/D1/D2）、显式析构调用与伪析构、对已结束生命周期的对象再次析构是 UB、默认 noexcept
status: draft
papers: P0848R3
related: special, class.ctor, basic.life, class.free, expr.delete, expr.prim.id.dtor, class.cdtor, except.spec, class.virtual
tags: 析构函数, 虚析构, 预期析构函数, 显式析构调用, UB
updated: 2026-10-18
---

析构函数是对象生命周期的终点：对类类型而言，**析构函数调用一开始，生命周期就结束了**（[[basic.life#2]]）。本节规定析构函数如何声明、如何从多个预期析构函数中选出，编译器生成的析构函数做什么、何时隐式调用，以及虚析构函数如何与 `operator delete` 配合。RAII 是 C++ 最重要的资源管理惯用法，它在语言层面的全部保障都在这里。

阅读前提：[[special]]（隐式声明总表、合格的概念）、[[basic.life]]（生命周期）、[[class.free]]（类专属的 `operator delete`）。

## 预期析构函数的声明形式（¶1）

¶1 规定，如果声明中 *declarator-id* 的 *unqualified-id* 以 `~` 开头，这个声明就声明了一个**预期析构函数**（prospective destructor，[[g:prospective-destructor]]）。其声明符必须是形如

```text
ptr-declarator ( parameter-declaration-clause ) noexcept-specifier(可选) 属性(可选)
```

的函数声明符，其中 *id-expression* 是：

- ¶1.1 在类（模板）的 *member-specification* 中的非友元成员声明里，写作 `~类名`，类名是直接外围实体的注入类名；
- ¶1.2 其他情况下写作 `嵌套名说明符 ~类名`，类名是该嵌套名说明符所指名的类的注入类名（用于类外定义 `X::~X() { }` 和友元声明）。

预期析构函数**不能有形参**（`void` 形参列表除外）。*decl-specifier-seq* 中只能出现 `friend`、`inline`、`virtual`、`constexpr`：不能有 `explicit`（析构函数不参与转换），不能有 `consteval` 和 `static`，也没有返回类型。

```cpp title="dtor-decl.cpp" error
struct S {
    ~S();                 // OK
    // ~S(int);           // error: 析构函数不能有形参
};
struct T {
    virtual ~T() = default;     // OK
    void ~T();            // error: 析构函数不能有返回类型
};
struct U {
    static ~U();          // error: 析构函数不能是 static
};
```

和构造函数一样，类模板中应写 `~X();` 而不是 `~X<T>();`，C++20 起后者不符合 ¶1.1 的形式。

## 隐式声明（¶2–¶3）

¶2 规定，如果类没有用户声明的预期析构函数，并且不是匿名联合体，就隐式声明一个预置的预期析构函数，它是类的 inline public 成员。¶3 规定其形式是 `~X()`。

与其他特殊成员函数不同，**析构函数的隐式声明不会被任何东西抑制**，每个类（匿名联合体除外）都有析构函数。

## 选出析构函数（¶4）

¶4 规定，在类定义结束处（匿名联合体除外），以空实参列表在该类声明的预期析构函数之间做重载决议，选出类的**析构函数**，也称为选中的析构函数（selected destructor）。重载决议失败时程序非良构。**选择析构函数本身不构成对选中析构函数的引用或 odr-use**，所以选中的析构函数可以是弃置的。

这是 C++20 为条件平凡（[[P0848R3]]）引入的机制。析构函数没有形参，所以多个预期析构函数只能靠约束来区分：

```cpp run title="select-dtor.cpp" ok
#include <type_traits>
#include <string>

template<class T>
struct Box {
    ~Box() requires std::is_trivially_destructible_v<T> = default;  // #1
    ~Box() { t.~T(); }                                              // #2（真实代码中配合 union 存储）
    union { T t; };
    Box() : t() { }
};

static_assert( std::is_trivially_destructible_v<Box<int>>);         // 选中 #1：约束满足且更受约束
static_assert(!std::is_trivially_destructible_v<Box<std::string>>); // #1 约束不满足，选中 #2

int main() { Box<std::string> b; (void)b; }
```

如果有两个预期析构函数的约束都满足，又无法比较谁更受约束，选择就是二义的，程序非良构。按 [[dcl.fct.def.default#5]]，没有被选为析构函数的预置预期析构函数定义为弃置，这并无害处，因为它反正不会被调用。

## 不能取地址；构造期间 cv 不生效（¶5）

¶5 规定，**不能取析构函数的地址**，析构函数体中的 `return` 不能带值。析构函数可以对 `const`、`volatile`、`const volatile` 对象调用；**正在析构的对象不受 `const`/`volatile` 语义约束**，这些语义从最派生对象的析构函数开始时起就不再生效。这与构造（[[class.ctor.general#4]]）是对称的：`const` 对象的析构函数可以修改成员，例如把指针置空。

## 异常说明：默认 noexcept（¶6）

¶6 注 2 指出，没有 *noexcept-specifier* 的析构函数声明，与隐式声明的析构函数具有相同的异常说明（[[except.spec]]）。也就是说，只要基类和成员的析构函数都不抛出，**用户写的析构函数默认也是 `noexcept`**，哪怕函数体里有 `throw`：

```cpp run title="dtor-noexcept.cpp" ok
#include <type_traits>

struct T { ~T() { } };                      // 隐式 noexcept(true)
struct U { ~U() noexcept(false) { } };      // 显式允许抛出
struct V { U u; ~V() { } };                 // 成员 U 的析构可能抛出 ⇒ V 的析构也是 noexcept(false)

static_assert( std::is_nothrow_destructible_v<T>);
static_assert(!std::is_nothrow_destructible_v<U>);
static_assert(!std::is_nothrow_destructible_v<V>);
int main() { }
```

这是 C++11 的变化。在 C++98 中，没有异常说明的析构函数可以抛出任何异常。改变的理由是，析构函数会在栈展开期间调用，如果此时再抛出异常，只能 `std::terminate`；标准库也要求所有类型的析构函数不抛出。从 `noexcept` 析构函数中抛出异常会直接调用 `std::terminate`。

## 预置析构函数何时被删除（¶7）

¶7 规定，在以下情形中，类 `X` 的预置析构函数**定义为弃置**：

- ¶7.1 `X` 是非联合体类，它的某个非变体潜在构造子对象是类类型 `M`（或其多维数组），而 `M` 的析构函数已删除，或者从预置析构函数中不可访问；
- ¶7.2 `X` 是联合体，并且：
    - ¶7.2.1 为默认初始化 `X` 而对构造函数做的重载决议失败，或者选中了一个弃置的或非平凡的构造函数；或
    - ¶7.2.2 `X` 有某个类类型 `M`（或其多维数组）的变体成员 V，V 有默认成员初始化器，并且 `M` 的析构函数非平凡；
- ¶7.3 对虚析构函数而言，查找非数组解分配函数的结果有二义，或者找到的函数是弃置的，或者从预置析构函数中不可访问。

### 联合体的析构：C++26 的新规则 {{c++26}}

C++26 的平凡联合体改动分为两半，¶7.2 是其中一半，另一半见 [[class.default.ctor#2]]。思路是这样的：联合体的析构函数不知道哪个成员是活跃的，所以不能析构任何成员；那么在什么情况下什么也不做是安全的？

- 如果联合体的默认构造函数是平凡的（不开始任何成员的生命周期），默认构造出来的联合体就没有活跃成员，什么都不析构是对的；
- 如果默认构造函数非平凡（例如某个变体成员有默认成员初始化器，或者用户提供了构造函数），它可能开始了某个成员的生命周期，而那个成员需要析构，所以预置的析构函数被删除，迫使用户自己写。

C++23 及以前的规则是：只要联合体有某个变体成员的析构函数非平凡，联合体的预置析构函数就被删除。所以 `union { std::string s; }` 在 C++23 中必须手写 `~U() { }`，而在 C++26 中它的析构函数是平凡的（[[class.dtor#8]] ¶8.3 中的"或 X 是联合体"）。截至写作时，Clang 23 尚未实现这一变化。

```cpp title="union-dtor.cpp"
#include <string>

union U1 { std::string s; };              // C++26：析构平凡（默认构造平凡）；C++23：析构被删除
union U2 { std::string s = "x"; };        // 两个版本中析构都被删除（¶7.2.2）：默认构造开始了 s 的生命周期
union U3 { std::string s; U3() : s() { } ~U3() { s.~basic_string(); } };   // 用户自己负责
int main() { U3 u; (void)u; }
```

## 平凡的析构函数（¶8）

¶8 规定，如果类 `X` 的析构函数不是用户提供的，并且满足以下条件，它就是**平凡的**：

- ¶8.1 析构函数不是虚的；
- ¶8.2 `X` 的所有直接基类都有平凡析构函数；
- ¶8.3 `X` 是联合体，或者 `X` 的所有类类型（或其数组）的非变体非静态数据成员都有平凡析构函数。

平凡的析构函数什么也不做。平凡析构是平凡可复制（[[class.prop#1]]）和隐式生存期（[[class.prop#8]]）的必要条件，也是字面类型的条件之一（另一个选择是 `constexpr` 析构函数，[[basic.types.general]]）。

注意，**虚析构函数永远不是平凡的**，即使它是 `= default`。所以多态基类不可能是平凡可复制的。

## constexpr 与隐式定义（¶9–¶10）

¶9 规定，**预置的析构函数是 `constexpr` 析构函数**（C++20 起析构函数可以是 `constexpr`）。¶10 规定，预置析构函数隐式定义之前，其基类和非静态数据成员的所有非用户提供的析构函数要先隐式定义。

## 虚析构函数与纯虚析构函数（¶11）

¶11 规定，预期析构函数可以声明为 `virtual`（[[class.virtual]]），也可以声明为纯虚的（带 *pure-specifier*，[[class.abstract]]）。如果类的析构函数是虚的，并且程序中创建了该类或其任何派生类的对象，**该析构函数就必须有定义**。

为什么纯虚析构函数也必须有定义？因为派生类的析构函数执行完自己的函数体后，总会调用基类的析构函数（¶13，按限定名调用，不经虚分派）。纯虚析构函数唯一的用途，是让一个没有其他纯虚函数的类成为抽象类：

```cpp run title="pure-virtual-dtor.cpp" ok
struct Shape {
    virtual ~Shape() = 0;      // 纯虚：Shape 是抽象类
};
Shape::~Shape() = default;     // 但必须定义：派生类析构时会调用它

struct Circle : Shape { };

int main() {
    Shape* p = new Circle;
    delete p;                  // 虚分派到 Circle::~Circle，后者调用 Shape::~Shape
}
```

什么时候需要虚析构函数？当对象会通过基类指针 `delete` 时。如果对象的静态类型与动态类型不同，而静态类型又没有虚析构函数，`delete` 它就是 **UB**（[[expr.delete]]）：

```cpp title="non-virtual-dtor.cpp" ub
#include <string>

struct Base { };                     // 析构函数不是虚的
struct Derived : Base { std::string s = "leak?"; };

int main() {
    Base* p = new Derived;
    delete p;                        // UB: 静态类型 Base 没有虚析构函数
}
```

常见的说法是"只会泄漏 `Derived` 的成员"，这是错的。标准规定这是 UB；实践中也可能按错误的大小释放（sized deallocation），在多重继承下还可能把错误的地址传给 `operator delete`。

## 析构的顺序（¶13）

¶13 规定，执行完析构函数体、销毁了函数体中分配的自动存储期对象之后，类 `X` 的析构函数依次调用：

1. `X` 的直接非变体非静态数据成员（匿名联合体除外）的析构函数；
2. `X` 的非虚直接基类的析构函数；
3. 若 `X` 是最派生类（[[class.base.init]]），`X` 的虚基类的析构函数。

所有这些调用都如同使用了限定名，即不考虑更派生类中的虚覆盖。**基类与成员按其构造完成顺序的逆序销毁**。注 4 指出，析构函数中的 `return` 语句不一定直接返回调用方，成员和基类的析构还要先进行。数组元素按构造的逆序析构（[[class.init]]）。

```cpp run title="dtor-order.cpp" ok
#include <cstdio>

struct M { const char* n; ~M() { std::printf("~M(%s) ", n); } };
struct B1 { ~B1() { std::printf("~B1 "); } };
struct B2 { ~B2() { std::printf("~B2 "); } };

struct X : B1, B2 {
    M a{"a"}, b{"b"};
    ~X() { std::printf("~X-body "); }
};

int main() {
    { X x; }          // 输出：~X-body ~M(b) ~M(a) ~B2 ~B1
    std::printf("\n");
}
```

逆序销毁保证了 RAII 的正确性：后构造的成员可能依赖先构造的成员（例如持有对它的引用），所以必须先销毁。

## 隐式调用与"潜在调用"（¶14）

¶14 规定，析构函数在以下情形中隐式调用：

- ¶14.1 静态存储期的已构造对象，在程序终止时（[[basic.start.term]]）；
- ¶14.2 线程存储期的已构造对象，在线程退出时；
- ¶14.3 自动存储期的已构造对象，在创建它的块退出时（[[stmt.dcl]]）；
- ¶14.4 已构造的临时对象，在其生命周期结束时（[[conv.rval]]、[[class.temporary]]）。

在每种情形中，调用的上下文（用于访问检查）都是对象构造的上下文。由 *new-expression* 创建的对象，也可以通过 *delete-expression* 隐式调用析构函数，这时上下文是该 *delete-expression*。注 5 指出，类类型的数组包含若干子对象，每个子对象都要调用析构函数。析构函数也可以显式调用。

析构函数被调用，或者在 [[expr.new]]、[[stmt.return]]、[[dcl.init.aggr]]、[[class.base.init]]、[[except.throw]] 规定的情形下可能被调用，就称它被**潜在调用**（potentially invoked）。典型的情形是构造中途抛出异常，需要析构已构造的部分。**如果潜在调用的析构函数已删除，或者从调用上下文不可访问，程序非良构。**

```cpp title="dtor-access.cpp" error
struct P { private: ~P(); public: P(); };

P* mk() { return new P; }        // OK: new P 不潜在调用析构函数（非数组、没有需要回滚的部分）
void f(P* p) { delete p; }       // error: 析构函数是 private 的
void g() { P local; }            // error: 块退出时调用 private 析构函数
P* arr() { return new P[2]; }    // error: 数组 new 潜在调用析构函数（第二个元素构造失败时析构第一个）
```

私有析构函数可以用来实现只能在堆上创建对象的惯用法，通常配合一个 `destroy()` 成员或友元的工厂函数、删除器使用。

## 虚析构函数的 operator delete 查找（¶15）

¶15 规定，在虚析构函数的定义点（包括隐式定义），非数组解分配函数的确定方式，如同该类的非虚析构函数中出现了 `delete this`（[[expr.delete]]）。查找失败或找到弃置的函数时，程序非良构。注 6 指出，这保证了与对象**动态类型**对应的解分配函数在 *delete-expression* 中可用（[[class.free]]）。

```cpp title="virtual-dtor-delete.cpp" error
struct NoDel {
    void operator delete(void*) = delete;
    virtual ~NoDel() { }          // error: 虚析构函数的定义需要可用的 operator delete
};
```

即使程序从来不 `delete` 一个 `NoDel`（比如只在栈上使用它），这也是错误，因为虚析构函数的定义要生成删除析构函数（见下文）。

!!! impl "Itanium ABI：D0、D1、D2"
    Itanium C++ ABI 为每个析构函数最多生成三个变体：

    - **D2**（base object destructor）：作为基类子对象析构，不析构虚基类；
    - **D1**（complete object destructor）：析构完整对象，包括虚基类；
    - **D0**（deleting destructor）：先调用 D1，再调用该类选定的 `operator delete`。只有虚析构函数才有 D0，它放在虚表里。

    当 `p` 的静态类型有虚析构函数时，`delete p;` 编译为经虚表调用 D0。于是 `operator delete` 由动态类型的类决定。[[class.free]] 说效果如同虚函数，实现方式就是这样；¶15 要求在虚析构函数的定义点就能找到 `operator delete`，原因也在这里，D0 需要它。自动对象和静态对象的析构调用 D1，派生类的析构函数调用基类的 D2。MSVC 的方案不同，它使用一个带隐藏标志参数的标量删除析构函数（scalar deleting destructor）。

## 显式析构调用（¶16–¶17）

¶16 规定，在显式析构调用中，析构函数用 `~` 后跟一个表示该类类型的 *type-name* 或 *computed-type-specifier*（如 `decltype`）来指定。析构函数的调用遵守成员函数的一般规则：**如果对象既不是析构函数所属的类类型，也不是其派生类类型（包括通过空指针调用的情形），行为未定义**。注 7 指出，对空指针 `delete` 不会调用析构函数。

标准例 1 展示了虚析构与限定名的区别：

```cpp run title="explicit-dtor-call.cpp" ok
#include <new>
#include <cstdio>

struct B { virtual ~B() { std::puts("~B"); } };
struct D : B { ~D() { std::puts("~D"); } };

int main() {
    alignas(D) unsigned char buf[sizeof(D)];
    typedef B B_alias;

    B* p = ::new (buf) D;
    p->~B();                 // 虚调用：~D 然后 ~B
    p = ::new (buf) D;
    p->~B_alias();           // 同上：经 typedef 指名，仍是虚调用
    p = ::new (buf) D;
    p->B_alias::~B();        // 限定名：只调用 B 的析构函数（非虚）——D 部分未析构
    // 此时 buf 中的对象生命周期已结束（[basic.life]），但 D 的析构函数从未运行；
    // 对 D 而言这只是跳过析构（不是 UB），但通常是 bug。
}
```

注 8 指出，显式析构调用必须写成成员访问（`p->~X()`、`x.~X()`）或限定名（在成员函数中写 `X::~X()`）。在成员函数中单独写 `~X()` 不是析构调用，而是对临时对象 `X()` 施加一元 `~` 运算符（[[expr.unary.op]]）。

¶17 注 9 指出，显式析构调用很少需要，典型用途是配合 placement new 管理特定地址上的对象，例如内存池、`std::optional`、`std::vector` 的实现。C++17 起推荐使用 `std::destroy_at(p)`，它也适用于数组，而且不需要写出类型名。

## 对已结束生命周期的对象再次析构（¶18）

¶18 规定，一旦为某个对象调用了析构函数，该对象的生命周期就结束了；**为生命周期已经结束的对象调用析构函数是 UB**（[[basic.life]]）。例 3：如果显式调用了一个自动存储期对象的析构函数，之后块又以通常会隐式析构该对象的方式退出，行为未定义。

```cpp title="double-destroy.cpp" ub
#include <string>

int main() {
    std::string s = "a fairly long string that lives on the heap";
    s.~basic_string();       // 显式析构：生命周期结束
}                            // UB: 块退出时再次隐式析构 s（double free）
```

修复方法见 [[basic.life]] 的 `scope-exit-fixed.cpp`：退出作用域之前，在原位置用 placement new 构造一个新对象。

## 伪析构函数（¶19）

¶19 注 10 指出，显式析构调用的写法可以用于任何标量类型名（[[expr.prim.id.dtor]]），这样编写泛型代码时就不需要知道类型是否有析构函数：

```cpp run title="pseudo-dtor.cpp" ok
#include <new>

template<class T>
void destroy(T* p) { p->~T(); }      // T = int 时是伪析构调用

int main() {
    int i = 1;
    typedef int I;
    I* p = &i;
    p->I::~I();                      // 伪析构：C++20 起结束 i 的生命周期
    ::new (&i) int(2);               // 重新开始一个 int 的生命周期
    destroy(&i);
    ::new (&i) int(3);
    return i - 3;
}
```

C++20 之前，伪析构调用是空操作（no-op）；C++20 起它**结束对象的生命周期**（[[basic.life#2]]）。这样 `std::destroy_at` 之类的泛型代码对标量类型和类类型的行为一致，常量求值也能检测出析构后使用。

## 不能是协程（¶20）

¶20 规定，析构函数不能是协程。

## 实现视角

!!! impl "虚表中的析构函数"
    在 Itanium ABI 中，虚析构函数在虚表中占两个槽位（D1 与 D0），所以有虚析构函数的类，虚表项比虚函数的个数多一项。类有虚函数却没有虚析构函数时，`-Wnon-virtual-dtor`（GCC/Clang）会给出警告；`delete` 这种类的指针时，`-Wdelete-non-abstract-non-virtual-dtor` 会给出警告。

!!! impl "析构函数与 constexpr"
    C++20 起，常量求值中可以调用 `constexpr` 析构函数。Clang 会在常量求值中检测双重析构、析构后使用等错误并给出诊断，所以 ¶18 这类 UB 有许多可以在 `constexpr` 测试中发现。

## 历史与演进

!!! history "历史与演进"
    - **C++98**：析构函数、虚析构函数、显式析构调用、伪析构调用（空操作）都已存在。
    - **C++11**：析构函数默认 `noexcept`（与隐式声明的异常说明相同）；引入 `= default`/`= delete`；引入定义为弃置的规则。
    - **C++20**：引入预期析构函数与析构函数的选择（[[P0848R3]]）；`constexpr` 析构函数；伪析构调用结束生命周期；销毁型 `operator delete`（[[class.free]]）；类模板中不再允许写 `~X<T>()`。
    - **C++26 草案**：联合体的预置析构函数是否删除，按默认构造是否平凡来判断（平凡联合体）；即使变体成员的析构函数不平凡，联合体的析构函数也可以是平凡的。

## 陷阱

!!! pitfall "多态基类没有虚析构函数"
    通过基类指针 `delete` 派生类对象是 UB。有虚函数的类，析构函数要么是 `public virtual`，要么是 `protected` 非虚的（禁止通过基类指针删除）。

!!! pitfall "析构函数中抛出异常"
    析构函数默认是 `noexcept`，抛出异常就会 `std::terminate`。需要报告析构中的失败时，可以提供显式的 `close()` 成员，让调用方处理。

!!! pitfall "显式析构后忘了作用域退出时的隐式析构"
    见 `double-destroy.cpp`。

!!! pitfall "以为 `= default` 的虚析构函数是平凡的"
    虚析构函数永远是非平凡的（¶8.1），所以多态类型不是平凡可复制的，也不是隐式生存期类型（除非是聚合）。

## 思考题

!!! question "思考题 1"
    ```cpp
    template<class T> struct W {
        ~W() requires (sizeof(T) > 4);
        ~W() requires (sizeof(T) > 2);
    };
    W<int> a;     // (1)
    W<double> b;  // (2)
    ```

<details markdown="1">
<summary>答案</summary>

(1)：在主流实现上 `sizeof(int) == 4`，第一个约束不满足，只剩下第二个，于是选中它。程序良构（链接时需要它的定义）。

(2)：`sizeof(double) == 8`，两个约束都满足。两个原子约束 `sizeof(T) > 4` 和 `sizeof(T) > 2` 是不同的表达式，**彼此不存在包含关系**（约束的偏序比较的是原子约束是否相同，不做数值推理），所以重载决议有二义，按 ¶4 程序非良构，在实例化 `W<double>` 的类定义时报错。
</details>

!!! question "思考题 2"
    为什么 ¶15 要在定义虚析构函数时就查找 `operator delete`，而不是等到出现 `delete` 表达式时再查找？

<details markdown="1">
<summary>答案</summary>

因为在 `delete p;` 处只知道 `p` 的静态类型，而应当调用的 `operator delete` 由动态类型决定（[[class.free]]）。唯一知道动态类型的地方，是动态类型自己的虚析构函数。在实现上，删除析构函数（D0）就是在类的虚析构函数定义处生成的，并在那里调用该类的 `operator delete`。所以查找必须在定义虚析构函数时进行，找不到就是错误，即使程序从不 `delete` 该类的对象。
</details>

## 小结

| 主题 | 规则 |
|---|---|
| 声明 | `~注入类名()`；无形参、无返回类型；说明符只能是 `friend`/`inline`/`virtual`/`constexpr` |
| 隐式声明 | 无用户声明的预期析构函数时；无法抑制 |
| 选择 | 类结束时在预期析构函数间做重载决议；可选中弃置的；二义则非良构 |
| 异常说明 | 无 `noexcept` 时同隐式声明：通常 `noexcept(true)` |
| 弃置 | 非变体子对象析构不可用；联合体按默认构造是否平凡判断（C++26）；虚析构找不到可用 `operator delete` |
| 平凡 | 非用户提供 + 非虚 + 基类与（非联合体的）成员析构平凡 |
| 顺序 | 函数体 → 成员（逆序）→ 非虚直接基类（逆序）→（最派生时）虚基类 |
| 潜在调用 | 被删除或不可访问的潜在调用析构函数使程序非良构 |
| 显式调用 | 必须用成员访问或限定名；限定名调用不经虚分派；对已结束生命周期的对象再次析构为 UB |
| 伪析构 | 标量类型也能写 `p->~T()`；C++20 起结束生命周期 |
