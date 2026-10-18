---
title: 析构函数
summary: 预期析构函数与析构函数的选择、隐式声明与定义、何时被删除、何时平凡、析构顺序、何时被隐式调用与"潜在调用"、虚析构函数与 operator delete 的查找（Itanium D0/D1/D2）、显式析构调用与伪析构、对已结束生命周期的对象再次析构是 UB、默认 noexcept
status: draft
papers: P0848R3
related: special, class.ctor, basic.life, class.free, expr.delete, expr.prim.id.dtor, class.cdtor, except.spec, class.virtual
tags: 析构函数, 虚析构, 预期析构函数, 显式析构调用, UB
updated: 2026-10-18
---

析构函数是对象生命周期的终点：对类类型而言，**析构函数调用开始时生命周期就结束了**（[[basic.life#2]]）。本节规定析构函数如何声明、如何从多个"预期析构函数"中选出、编译器生成的析构函数做什么、何时被隐式调用，以及虚析构函数与 `operator delete` 的配合。RAII——C++ 最重要的资源管理惯用法——的全部语言保障都在这里。

阅读前提：[[special]]（隐式声明总表、"合格"）、[[basic.life]]（生命周期）、[[class.free]]（类专属 `operator delete`）。

## 预期析构函数的声明形式（¶1）

¶1：*declarator-id* 的 *unqualified-id* 以 `~` 开头的声明，声明一个**预期析构函数**（prospective destructor，[[g:prospective-destructor]]）。其声明符必须是形如

```text
ptr-declarator ( parameter-declaration-clause ) noexcept-specifier(可选) 属性(可选)
```

的函数声明符，其中 *id-expression* 是：

- ¶1.1 在类（模板）的 *member-specification* 中的非友元成员声明里：`~类名`，类名是直接外围实体的**注入类名**；
- ¶1.2 否则：`嵌套名说明符 ~类名`，类名是该嵌套名说明符所提名类的注入类名（类外定义 `X::~X() { }`、友元声明）。

预期析构函数**不能有形参**（`void` 形参列表除外）。*decl-specifier-seq* 中只能有 `friend`、`inline`、`virtual`、`constexpr`——没有 `explicit`（不参与转换）、没有 `consteval`、没有 `static`，也没有返回类型。

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

和构造函数一样，类模板中应写 `~X();` 而不是 `~X<T>();`——后者在 C++20 起不符合 ¶1.1 的形式。

## 隐式声明（¶2–¶3）

¶2：若类没有**用户声明的**预期析构函数，且不是匿名联合体，则隐式声明一个预置的预期析构函数；它是类的 **inline public** 成员。¶3：其形式是 `~X()`。

与其他特殊成员函数不同，**没有任何东西能抑制析构函数的隐式声明**——每个类（匿名联合体除外）都有析构函数。

## 选出析构函数（¶4）

¶4：在类定义结束时（匿名联合体除外），在该类声明的预期析构函数之间以**空实参列表**进行重载决议，选出类的**析构函数**，也称**选中的析构函数**（selected destructor）。重载决议失败则程序非良构。**析构函数的选择不构成对选中析构函数的引用或 odr-use**——特别地，选中的析构函数可以是弃置的。

这是 C++20 为条件平凡（[[P0848R3]]）引入的机制。由于析构函数没有形参，多个预期析构函数只能靠**约束**区分：

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

若有两个约束都满足、又不能比较谁更受约束的预期析构函数，选择二义——程序非良构。[[dcl.fct.def.default#5]]：一个预置的预期析构函数若**没有被选为**析构函数，它被定义为弃置（无害，因为反正不会被调用）。

## 不能取地址；构造期间 cv 不生效（¶5）

¶5：**不能取析构函数的地址**；析构函数体中的 `return` 不能带值。析构函数可以为 `const`、`volatile`、`const volatile` 对象调用；**正在析构的对象不受 `const`/`volatile` 语义约束**——这些语义在**最派生对象的析构函数开始时**就停止生效。与构造（[[class.ctor.general#4]]）对称：`const` 对象的析构函数可以修改成员（例如把指针置空）。

## 异常说明：默认 noexcept（¶6）

¶6 注 2：没有 *noexcept-specifier* 的析构函数声明，与隐式声明时具有**相同的异常说明**（[[except.spec]]）。也就是说：只要基类和成员的析构函数都不抛出，**用户写的析构函数也默认是 `noexcept`**，哪怕函数体里有 `throw`：

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

这是 C++11 的变化：C++98 中析构函数没有异常说明就可以抛出任何异常。改变的理由是，析构函数在栈展开期间被调用，若此时再抛出异常只能 `std::terminate`；标准库要求所有类型的析构函数不抛出。从 `noexcept` 析构函数中抛出异常会直接调用 `std::terminate`。

## 预置析构函数何时被删除（¶7）

¶7：类 `X` 的预置析构函数在以下情形被**定义为弃置**：

- ¶7.1 `X` 是非联合体类，某个**非变体**的潜在构造子对象是类类型 `M`（或其多维数组），`M` 的析构函数被删除或从预置析构函数中**不可访问**；
- ¶7.2 `X` 是**联合体**，并且：
    - ¶7.2.1 用来默认初始化 `X` 的构造函数的重载决议失败，或选中了一个弃置的或**非平凡**的构造函数；或
    - ¶7.2.2 `X` 有某个变体成员 V 是类类型 `M`（或其多维数组），V 有默认成员初始化器且 `M` 的析构函数非平凡；
- ¶7.3 对**虚析构函数**：查找非数组的解分配函数结果二义，或得到一个弃置的或从预置析构函数中不可访问的函数。

### 联合体的析构：C++26 的新规则 {{c++26}}

¶7.2 是 C++26"平凡联合体"改动的另一半（另一半见 [[class.default.ctor#2]]）。思路是：联合体的析构函数不知道哪个成员活跃，所以不能析构任何成员；那么什么时候"什么也不做"是安全的？

- 若联合体的默认构造函数是**平凡的**（不开始任何成员的生命周期），那么默认构造的联合体没有活跃成员，什么都不析构是对的；
- 若默认构造函数**非平凡**（例如某个变体成员有默认成员初始化器，或用户提供了构造函数），它可能开始了某个成员的生命周期，而那个成员需要析构——于是预置的析构函数被删除，迫使用户自己写。

C++23 及以前的规则是：联合体若有变体成员的析构函数非平凡，联合体的预置析构函数就被删除。所以 `union { std::string s; }` 在 C++23 中必须手写 `~U() { }`；在 C++26 中它的析构函数是平凡的（[[class.dtor#8]] ¶8.3"或 X 是联合体"）。截至写作时 Clang 23 尚未实现这一变化。

```cpp title="union-dtor.cpp"
#include <string>

union U1 { std::string s; };              // C++26：析构平凡（默认构造平凡）；C++23：析构被删除
union U2 { std::string s = "x"; };        // 两个版本中析构都被删除（¶7.2.2）：默认构造开始了 s 的生命周期
union U3 { std::string s; U3() : s() { } ~U3() { s.~basic_string(); } };   // 用户自己负责
int main() { U3 u; (void)u; }
```

## 平凡的析构函数（¶8）

¶8：类 `X` 的析构函数是**平凡的**，若它**不是用户提供的**，并且：

- ¶8.1 析构函数不是虚的；
- ¶8.2 `X` 的所有直接基类都有平凡析构函数；
- ¶8.3 `X` 是联合体，或者 `X` 的所有类类型（或其数组）的非变体非静态数据成员都有平凡析构函数。

平凡的析构函数什么也不做。平凡析构是**平凡可复制**（[[class.prop#1]]）和**隐式生存期**（[[class.prop#8]]）的必要条件，也是**字面类型**的条件之一（另一个选择是 `constexpr` 析构函数，[[basic.types.general]]）。

注意：**虚析构函数永远不平凡**，即使它是 `= default`。所以多态基类不可能是平凡可复制的。

## constexpr 与隐式定义（¶9–¶10）

¶9：**预置的析构函数是 `constexpr` 析构函数**（C++20 起析构函数可以是 `constexpr`）。¶10：在预置析构函数被隐式定义之前，其基类和非静态数据成员的所有非用户提供的析构函数先被隐式定义。

## 虚析构函数与纯虚析构函数（¶11）

¶11：预期析构函数可以声明为 `virtual`（[[class.virtual]]）和**纯虚**（带 *pure-specifier*，[[class.abstract]]）。若类的析构函数是虚的，并且程序中创建了该类或任何派生类的对象，则**该析构函数必须被定义**。

为什么纯虚析构函数也必须有定义？因为派生类的析构函数在执行完自己的函数体后，**总会调用**基类析构函数（¶13，按限定名调用，不经虚分派）。纯虚析构函数的唯一用途是"让一个没有其他纯虚函数的类成为抽象类"：

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

**什么时候需要虚析构函数**：当对象会通过**基类指针 `delete`** 时。`delete` 一个静态类型与动态类型不同、且静态类型没有虚析构函数的对象，是 **UB**（[[expr.delete]]）：

```cpp title="non-virtual-dtor.cpp" ub
#include <string>

struct Base { };                     // 析构函数不是虚的
struct Derived : Base { std::string s = "leak?"; };

int main() {
    Base* p = new Derived;
    delete p;                        // UB: 静态类型 Base 没有虚析构函数
}
```

常见的说法"只会泄漏 `Derived` 的成员"是错的：标准说这是 UB，实践中也可能释放错误大小（sized deallocation）、在多重继承下传给 `operator delete` 错误的地址。

## 析构的顺序（¶13）

¶13：执行完析构函数**体**、并销毁了函数体中分配的自动存储期对象之后，类 `X` 的析构函数依次调用：

1. `X` 的直接非变体非静态数据成员（匿名联合体除外）的析构函数；
2. `X` 的非虚直接基类的析构函数；
3. 若 `X` 是最派生类（[[class.base.init]]），`X` 的虚基类的析构函数。

所有这些调用都**如同使用限定名**，即忽略更派生类中的虚覆盖。基类与成员按其**构造完成顺序的逆序**销毁。注 4：析构函数中的 `return` 语句不一定直接返回调用方——成员和基类的析构还要先进行。数组元素按构造的逆序析构（[[class.init]]）。

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

"逆序"保证了 RAII 的正确性：后构造的成员可能依赖先构造的成员（例如持有对它的引用），所以必须先销毁。

## 隐式调用与"潜在调用"（¶14）

¶14：析构函数在以下情形被**隐式调用**：

- ¶14.1 静态存储期的已构造对象：程序终止时（[[basic.start.term]]）；
- ¶14.2 线程存储期的已构造对象：线程退出时；
- ¶14.3 自动存储期的已构造对象：创建它的块退出时（[[stmt.dcl]]）；
- ¶14.4 已构造的临时对象：其生命周期结束时（[[conv.rval]]、[[class.temporary]]）。

每种情形中，调用的**上下文**（用于访问检查）是对象构造的上下文。对 *new-expression* 创建的对象，也可以通过 *delete-expression* 隐式调用析构函数，上下文是该 *delete-expression*。注 5：类类型数组包含若干子对象，每个都调用析构函数。析构函数也可以**显式调用**。

**潜在调用**（potentially invoked）：析构函数被调用，或在 [[expr.new]]、[[stmt.return]]、[[dcl.init.aggr]]、[[class.base.init]]、[[except.throw]] 规定的情形下被"可能调用"——典型的是构造中途抛异常时需要析构已构造的部分。**若潜在调用的析构函数被删除或从调用上下文不可访问，程序非良构。**

```cpp title="dtor-access.cpp" error
struct P { private: ~P(); public: P(); };

P* mk() { return new P; }        // OK: new P 不潜在调用析构函数（非数组、没有需要回滚的部分）
void f(P* p) { delete p; }       // error: 析构函数是 private 的
void g() { P local; }            // error: 块退出时调用 private 析构函数
P* arr() { return new P[2]; }    // error: 数组 new 潜在调用析构函数（第二个元素构造失败时析构第一个）
```

私有析构函数是"只能在堆上创建"的惯用法：配合一个 `destroy()` 成员或友元工厂/删除器使用。

## 虚析构函数的 operator delete 查找（¶15）

¶15：在**虚析构函数**的定义点（包括隐式定义），非数组的解分配函数按"在该类的非虚析构函数中出现 `delete this`"的方式确定（[[expr.delete]]）。若查找失败或找到的是弃置的函数，程序非良构。注 6：这保证了对应对象**动态类型**的解分配函数在 *delete-expression* 中可用（[[class.free]]）。

```cpp title="virtual-dtor-delete.cpp" error
struct NoDel {
    void operator delete(void*) = delete;
    virtual ~NoDel() { }          // error: 虚析构函数的定义需要可用的 operator delete
};
```

即使程序从来不 `delete` 一个 `NoDel`（比如只在栈上用），这也是错误——因为虚析构函数的定义要生成"删除析构函数"（见下）。

!!! impl "Itanium ABI：D0、D1、D2"
    Itanium C++ ABI 为每个析构函数发出最多三个变体：

    - **D2**（base object destructor）：作为基类子对象析构，**不**析构虚基类；
    - **D1**（complete object destructor）：析构完整对象，包括虚基类；
    - **D0**（deleting destructor）：调用 D1，然后调用**该类**选定的 `operator delete`。只有虚析构函数才有 D0，它放在虚表里。

    `delete p;`（`p` 静态类型有虚析构函数）编译为"经虚表调用 D0"。于是 `operator delete` 由**动态类型**的类决定——这就是 [[class.free]] 中"效果如同虚函数"的实现，也是 ¶15 要求在虚析构函数定义点就能找到 `operator delete` 的原因：D0 需要它。自动/静态对象的析构调用 D1，派生类析构函数调用基类的 D2。MSVC 的方案不同：使用一个带隐藏标志参数的"标量删除析构函数"（scalar deleting destructor）。

## 显式析构调用（¶16–¶17）

¶16：显式析构调用中，析构函数由 `~` 后跟一个表示该类类型的 *type-name* 或 *computed-type-specifier*（如 `decltype`）指定。析构函数的调用遵守成员函数的一般规则：若对象**不是**析构函数所属类类型、也不是其派生类类型（**包括通过空指针调用**），行为未定义。注 7：对空指针 `delete` 不调用析构函数。

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

注 8：显式析构调用**必须**写成成员访问（`p->~X()`、`x.~X()`）或限定名（`X::~X()` 在成员函数中）。成员函数中单独写 `~X()` **不是**析构调用，而是对 `X()` 临时对象施加一元 `~` 运算符（[[expr.unary.op]]）。

¶17 注 9：显式析构调用很少需要，典型用途是配合 placement new 管理特定地址上的对象（内存池、`std::optional`、`std::vector` 的实现）。C++17 起推荐用 `std::destroy_at(p)`，它对数组也适用，并且不需要写出类型名。

## 对已结束生命周期的对象再次析构（¶18）

¶18：一旦为某个对象调用了析构函数，对象的生命周期就结束了；**为一个生命周期已经结束的对象调用析构函数是 UB**（[[basic.life]]）。例 3：若显式调用了一个自动存储期对象的析构函数，之后块以通常会隐式析构该对象的方式退出，行为未定义。

```cpp title="double-destroy.cpp" ub
#include <string>

int main() {
    std::string s = "a fairly long string that lives on the heap";
    s.~basic_string();       // 显式析构：生命周期结束
}                            // UB: 块退出时再次隐式析构 s（double free）
```

修复方式见 [[basic.life]] 的 `scope-exit-fixed.cpp`：退出作用域前在原位置 placement new 一个新对象。

## 伪析构函数（¶19）

¶19 注 10：显式析构调用的写法可以用于任何**标量**类型名（[[expr.prim.id.dtor]]），这样写泛型代码时不需要知道类型是否有析构函数：

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

C++20 之前，伪析构调用是空操作（no-op）；C++20 起它**结束对象的生命周期**（[[basic.life#2]]），这使 `std::destroy_at` 等泛型代码对标量和类类型行为一致，也让常量求值能检测"析构后使用"。

## 不能是协程（¶20）

¶20：析构函数不能是协程。

## 实现视角

!!! impl "虚表中的析构函数"
    Itanium ABI 中，虚析构函数在虚表中占**两个**槽位（D1 与 D0），所以有虚析构函数的类的虚表比"函数数目"多一项。`-Wnon-virtual-dtor`（GCC/Clang）在类有虚函数却没有虚析构函数时警告；`-Wdelete-non-abstract-non-virtual-dtor` 对 `delete` 这种类的指针时警告。

!!! impl "析构函数与 constexpr"
    C++20 起，常量求值中可以调用 `constexpr` 析构函数；Clang 会在常量求值中检测双重析构、析构后使用等错误并给出诊断。这让许多 ¶18 类的 UB 在 `constexpr` 测试中可以被捕获。

## 历史与演进

!!! history "历史与演进"
    - **C++98**：析构函数、虚析构函数、显式析构调用、伪析构调用（空操作）都已存在。
    - **C++11**：析构函数默认 `noexcept`（与隐式声明的异常说明相同）；`= default`/`= delete`；"定义为弃置"的规则。
    - **C++20**：**预期析构函数**与析构函数选择（[[P0848R3]]）；`constexpr` 析构函数；伪析构调用结束生命周期；销毁型 `operator delete`（[[class.free]]）；类模板中 `~X<T>()` 不再允许。
    - **C++26 草案**：联合体的预置析构函数按"默认构造是否平凡"判断是否删除（平凡联合体）；联合体的析构函数可以平凡，即使变体成员的析构函数不平凡。

## 陷阱

!!! pitfall "多态基类没有虚析构函数"
    通过基类指针 `delete` 派生类对象是 UB。规则：有虚函数的类，析构函数要么 `public virtual`，要么 `protected` 非虚（禁止通过基类指针删除）。

!!! pitfall "析构函数中抛出异常"
    默认 `noexcept`，抛出即 `std::terminate`。需要报告析构中的失败时，提供显式的 `close()` 成员让调用方处理。

!!! pitfall "显式析构后忘了作用域退出时的隐式析构"
    见 `double-destroy.cpp`。

!!! pitfall "以为 `= default` 的虚析构函数是平凡的"
    虚析构函数永远非平凡（¶8.1），所以多态类型不是平凡可复制的，也不是隐式生存期类型（除非是聚合）。

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

(1)：`sizeof(int) == 4`（主流实现），第一个约束不满足，只剩第二个——选中它。良构（链接时需要它的定义）。

(2)：`sizeof(double) == 8`，两个约束都满足。两个原子约束 `sizeof(T) > 4` 和 `sizeof(T) > 2` 是不同的表达式，**不存在包含关系**（约束的偏序比较的是原子约束的同一性，不做数值推理），所以重载决议二义，¶4 规定程序非良构——在 `W<double>` 的类定义被实例化时报错。
</details>

!!! question "思考题 2"
    为什么 ¶15 要在**定义**虚析构函数时就查找 `operator delete`，而不是等到 `delete` 表达式出现时？

<details markdown="1">
<summary>答案</summary>

因为 `delete p;` 处只知道 `p` 的**静态类型**，而应调用的 `operator delete` 由**动态类型**决定（[[class.free]]）。唯一知道动态类型的地方是动态类型自己的虚析构函数——实现上就是删除析构函数（D0）在类的虚析构函数定义处生成，并在那里调用类的 `operator delete`。所以查找必须在定义虚析构函数时进行，找不到就是错误，即使程序从不 `delete` 该类对象。
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
