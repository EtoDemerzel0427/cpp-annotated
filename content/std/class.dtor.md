---
title: 析构函数
summary: 析构函数怎样声明、怎样从多个预期析构函数中选出；它何时被删除、何时平凡、默认为何是 noexcept；成员和基类的析构顺序，何时隐式调用，虚析构函数与 operator delete，以及显式析构调用的规则。
status: done
papers: P0848R3, P3074R7
related: special, class.ctor, basic.life, class.free, expr.delete, expr.prim.id.dtor, class.cdtor, except.spec, class.virtual
tags: 析构函数, 虚析构, 预期析构函数, 显式析构调用, UB
updated: 2026-10-19
---

!!! tldr
    - 每个类都有析构函数，用户不声明，编译器就隐式声明一个。C++20 起一个类可以写多个带约束的预期析构函数，类定义结束时用重载决议选出其中一个。
    - 没有写 `noexcept` 的析构函数，异常说明与隐式声明的相同，通常就是 `noexcept`；从中抛出异常会调用 `std::terminate`。
    - 析构函数先执行函数体，再按构造完成的逆序析构成员和基类。
    - 通过基类指针 `delete` 派生类对象，基类必须有虚析构函数，否则是未定义行为。
    - 对生命周期已经结束的对象再调用析构函数是未定义行为，最常见的情形是显式析构了一个局部变量，作用域结束时它又被析构一次。

析构函数是对象生命周期的终点。对类类型，析构函数调用一开始，对象的生命周期就结束了（[[basic.life#2]]）。RAII 在语言层面的保障，即离开作用域时资源一定被释放、释放顺序确定，都来自这一节。

## 声明析构函数（¶1–¶3）

<div class="compare" markdown="1">

```cpp ok
struct S {
    ~S();
};
S::~S() { }

struct T {
    virtual ~T() = default;
};
```

```cpp error
struct A {
    ~A(int);      // error: 不能有形参
};
struct B {
    void ~B();    // error: 不能有返回类型
};
struct C {
    static ~C();  // error: 不能是 static
};
```

</div>

¶1 如果一个声明的名字以 `~` 开头，它声明的是一个**预期析构函数**（[[g:prospective-destructor]]，prospective destructor）。为什么叫预期，下一节讲。它的形式与构造函数类似（[[class.ctor.general#1]]）：

- ¶1.1 在类定义内的成员声明中，写作 `~类名`，类名是直接外围类的注入类名；
- ¶1.2 其他情况下（类外定义、友元声明），写作 `嵌套名说明符 ~类名`，如 `S::~S`。

预期析构函数不能有形参（`()` 或 `(void)`），没有返回类型。说明符只能是 `friend`、`inline`、`virtual`、`constexpr`。和构造函数一样，类模板中应写 `~X();` 而不是 `~X<T>();`。

¶2 类没有用户声明的预期析构函数，并且不是匿名联合体时，编译器隐式声明一个**预置**（defaulted，由编译器生成定义）的预期析构函数，它是类的 inline public 成员。¶3 它的形式是 `~X()`。

其他特殊成员函数会因为用户声明了别的成员而不再隐式声明，析构函数没有这种抑制。匿名联合体以外的每个类都有析构函数。

## 从预期析构函数中选出析构函数（¶4）

```cpp run title="select-dtor.cpp" ok
#include <type_traits>
#include <string>

template<class T>
struct Box {
    ~Box() requires std::is_trivially_destructible_v<T>
        = default;           // #1
    ~Box() { t.~T(); }       // #2
    union { T t; };
    Box() : t() { }
};

static_assert( std::is_trivially_destructible_v<Box<int>>);
static_assert(!std::is_trivially_destructible_v<Box<std::string>>);

int main() { Box<std::string> b; (void)b; }
```

¶4 在类定义的末尾（匿名联合体除外），编译器以空实参列表，在这个类声明的所有预期析构函数之间做重载决议，选出的那个就是类的**析构函数**，也叫选中的析构函数（selected destructor）。重载决议失败时程序非良构。

析构函数没有形参，所以多个预期析构函数只能靠约束（requires 子句）区分。上例中，`T` 平凡可析构时 #1 的约束满足，而且比没有约束的 #2 更受约束，选中 #1，`Box<int>` 的析构函数平凡；否则只有 #2 可行。这是 C++20 条件平凡特殊成员函数（[[P0848R3]]）的一部分，`std::optional` 这类包装类型靠它在 `T` 平凡时自己也保持平凡。

¶4 最后一句说，选出析构函数不构成对它的使用（odr-use），所以选中的析构函数可以是弃置的。另外按 [[dcl.fct.def.default#5]]，没被选中的预置预期析构函数定义为弃置，反正它也不会被调用。

## 析构期间的 const 与禁令（¶5、¶20）

¶5 不能取析构函数的地址，析构函数体中的 `return` 不能带值。

析构函数可以为 `const`、`volatile` 或 `const volatile` 对象调用。正在析构的对象不受 `const` 和 `volatile` 语义约束，这些语义从最派生对象的析构函数开始时就不再生效。这与构造（[[class.ctor.general#4]]）对称：`const` 对象的析构函数可以修改成员，例如把指针置空。

¶20 析构函数不能是协程。

## 默认是 noexcept（¶6）

```cpp run title="dtor-noexcept.cpp" ok
#include <type_traits>

struct T { ~T() { } };
struct U { ~U() noexcept(false) { } };
struct V { U u; ~V() { } };

static_assert( std::is_nothrow_destructible_v<T>);
static_assert(!std::is_nothrow_destructible_v<U>);
static_assert(!std::is_nothrow_destructible_v<V>);
int main() { }
```

¶6 注 2 指出，没有写异常说明的析构函数声明，其异常说明与隐式声明的析构函数相同（[[except.spec]]）。所以只要基类和成员的析构函数都不抛出，用户写的析构函数也是 `noexcept` 的，即使函数体里有 `throw`。`V` 的成员 `U` 的析构可能抛出，`V` 的析构函数才跟着是 `noexcept(false)`。

这是 C++11 的变化，C++98 中没有异常说明的析构函数可以抛出任何异常。改变的理由是析构函数会在栈展开期间被调用，此时再抛出异常只能 `std::terminate`；标准库也要求元素类型的析构函数不抛出。需要报告析构过程中的失败时，可以另外提供 `close()` 之类的成员，让调用方处理。

## 何时定义为弃置（¶7）

¶7 类 `X` 的预置析构函数在下列情况下**定义为弃置**（相当于 `= delete`）：

- ¶7.1 `X` 不是联合体，某个非变体的**潜在构造子对象**（[[g:potentially-constructed-subobjects]]，直接基类、非静态数据成员和虚基类）是类类型 `M`（或其多维数组），而 `M` 的析构函数被删除，或者从这里不可访问；
- ¶7.2 `X` 是联合体，并且满足下面任一条：
    - ¶7.2.1 为默认初始化 `X` 选构造函数的重载决议失败，或者选中的构造函数被删除或非平凡；
    - ¶7.2.2 某个类类型 `M` 的**变体成员**（[[g:variant-member]]，联合体的成员）带有默认成员初始化器，而 `M` 的析构函数非平凡；
- ¶7.3 析构函数是虚的，而查找非数组的 `operator delete` 结果二义，或者找到的函数被删除或不可访问（见下文 ¶15）。

### 联合体的析构 {{c++26}}

联合体的析构函数不知道哪个成员是活跃的，所以不析构任何成员。¶7.2 回答的是：什么时候这样什么也不做是安全的？

- 联合体的默认构造函数平凡时，默认构造出来的联合体没有活跃成员，什么都不析构是对的；
- 默认构造函数非平凡时（某个变体成员有默认成员初始化器，或用户提供了构造函数），它可能开始了某个成员的生命周期，那个成员需要析构。所以预置的析构函数被删除，迫使用户自己写。

```cpp title="union-dtor.cpp"
#include <string>

union U1 { std::string s; };         // C++26: 析构平凡
union U2 { std::string s = "x"; };   // 析构被删除（¶7.2.2）
union U3 {                           // 自己负责
    std::string s;
    U3() : s() { }
    ~U3() { s.~basic_string(); }
};
int main() { U3 u; (void)u; }
```

C++23 的规则是：只要某个变体成员的析构函数非平凡，联合体的预置析构函数就被删除，所以 `U1` 必须手写 `~U1() { }`。C++26 的平凡联合体（[[P3074R7]]）改成了上面的规则，另一半改动在默认构造函数一侧（[[class.default.ctor#2]]）。本机 Clang 23 还没有实现这一变化，所以这个例子不标判定。

## 平凡的析构函数（¶8）

¶8 析构函数**平凡**的前提是它不是**用户提供**（[[g:user-provided]]，用户声明了它，且没有在第一次声明处 `= default` 或 `= delete`）的，此外：

- ¶8.1 它不是虚函数；
- ¶8.2 所有直接基类的析构函数都平凡；
- ¶8.3 类是联合体，或者它所有类类型（或其数组）的非变体非静态数据成员，析构函数都平凡。

平凡的析构函数什么也不做。它是平凡可复制类型（[[class.prop#1]]）和隐式生存期类型（[[class.prop#8]]）的必要条件。

按 ¶8.1，虚析构函数即使写成 `= default` 也不平凡，所以多态类型不是平凡可复制的。

## 隐式定义（¶9–¶10）

¶9 预置的析构函数是 `constexpr` 析构函数（C++20 起析构函数可以是 `constexpr`）。¶10 预置析构函数被隐式定义之前，其基类和成员的所有非用户提供的析构函数先被隐式定义。

¶12 注 3 提醒，在析构期间调用虚函数等操作有特殊语义，见 [[class.cdtor]]。

## 析构顺序（¶13）

```cpp run title="dtor-order.cpp" ok
#include <cstdio>

struct M {
    const char* n;
    ~M() { std::printf("~M(%s) ", n); }
};
struct B1 { ~B1() { std::printf("~B1 "); } };
struct B2 { ~B2() { std::printf("~B2 "); } };

struct X : B1, B2 {
    M a{"a"}, b{"b"};
    ~X() { std::printf("~X-body "); }
};

int main() {
    { X x; }   // ~X-body ~M(b) ~M(a) ~B2 ~B1
    std::printf("\n");
}
```

¶13 析构函数执行完函数体、销毁了函数体里的自动对象之后，依次调用：

1. 直接的非变体非静态数据成员的析构函数（匿名联合体除外）；
2. 非虚直接基类的析构函数；
3. 如果 `X` 是最派生类，虚基类的析构函数。

这些调用都如同使用了限定名，不经虚分派。基类和成员按它们构造完成的逆序销毁，数组元素也按构造的逆序析构（[[class.init]]）。所以析构函数里的 `return` 并不直接回到调用方，之后还要析构成员和基类（注 4）。

逆序保证了 RAII 的正确性：后构造的成员可能依赖先构造的成员，例如持有对它的引用，所以要先销毁。

## 何时隐式调用（¶14）

¶14 析构函数在以下时机隐式调用：

- ¶14.1 静态存储期的已构造对象，在程序终止时（[[basic.start.term]]）；
- ¶14.2 线程存储期的已构造对象，在线程退出时；
- ¶14.3 自动存储期的已构造对象，在创建它的块退出时（[[stmt.dcl]]）；
- ¶14.4 已构造的临时对象，在其生命周期结束时（[[class.temporary]]）。

用 *new-expression* 创建的对象，可以通过 *delete-expression* 调用析构函数。析构函数也可以显式调用（¶16）。

```cpp title="dtor-access.cpp" error
struct P { private: ~P(); public: P(); };

P* mk() { return new P; }       // OK
void f(P* p) { delete p; }      // error: 析构函数是 private 的
void g() { P local; }           // error: 块退出时要调用它
P* arr() { return new P[2]; }   // error: 数组 new 潜在调用析构函数
```

¶14 还定义了**潜在调用**（[[g:potentially-invoked]]，potentially invoked）：析构函数被调用，或者在 [[expr.new]]、[[stmt.return]]、[[dcl.init.aggr]]、[[class.base.init]]、[[except.throw]] 规定的情形下可能被调用。典型情形是构造到一半抛出异常，要析构已经构造好的部分。潜在调用的析构函数如果被删除，或者从调用的上下文不可访问，程序非良构。

上例中，`new P[2]` 构造第二个元素时如果抛出异常，要析构第一个，所以它潜在调用析构函数；`new P` 没有这样的回滚，不调用。隐式调用时的访问检查，上下文是构造对象的地方；经由 `delete` 调用时，上下文是那个 *delete-expression*。私有析构函数因此可以用来限制对象只能在堆上创建，配合一个 `destroy()` 成员或友元删除器使用。

## 虚析构函数（¶11、¶15）

### 什么时候需要（¶11）

```cpp title="non-virtual-dtor.cpp" ub
#include <string>

struct Base { };   // 析构函数不是虚的
struct Derived : Base { std::string s = "leak?"; };

int main() {
    Base* p = new Derived;
    delete p;      // UB: Base 没有虚析构函数
}
```

对象会通过基类指针 `delete` 时，基类需要虚析构函数。`delete` 表达式中对象的静态类型与动态类型不同，而静态类型没有虚析构函数，就是未定义行为（[[expr.delete]]）。

常见的说法是这样只会泄漏 `Derived` 的成员，这不对。标准规定这是未定义行为；实践中还可能按错误的大小释放内存，多重继承下甚至把错误的地址传给 `operator delete`。

¶11 预期析构函数可以声明为 `virtual`，也可以声明为纯虚的。如果类的析构函数是虚的，并且程序创建了这个类或其派生类的对象，析构函数就必须有定义，纯虚的也不例外：

```cpp run title="pure-virtual-dtor.cpp" ok
struct Shape {
    virtual ~Shape() = 0;    // Shape 是抽象类
};
Shape::~Shape() = default;   // 仍然必须定义

struct Circle : Shape { };

int main() {
    Shape* p = new Circle;
    delete p;   // ~Circle，然后 ~Shape
}
```

派生类的析构函数执行完之后，总会按限定名调用基类的析构函数（¶13），所以它必须存在。纯虚析构函数的唯一用途，是让一个没有其他纯虚函数的类成为抽象类。

### 定义虚析构函数时查找 `operator delete`（¶15）

<div class="compare" markdown="1">

```cpp ok
struct A {
    void operator delete(void*)
        = delete;
    virtual ~A() = default;
    // 预置：定义为弃置（¶7.3）
};
```

```cpp error
struct B {
    void operator delete(void*)
        = delete;
    virtual ~B() { }
    // error: 用户提供，
    // 找到的 operator delete 被删除（¶15）
};
```

</div>

¶15 在虚析构函数的定义点（包括隐式定义），编译器就要确定非数组的解分配函数，方式如同在这个类的一个非虚析构函数里写了 `delete this`（[[expr.delete]]）。查找失败或找到弃置的函数时，程序非良构。注 6 说明，这保证了与对象动态类型对应的 `operator delete` 在 `delete` 表达式中可用（[[class.free]]）。

左边的类预置了析构函数，¶7.3 让它定义为弃置，本机 Clang 23 只给出 `-Wdefaulted-function-deleted` 警告；这样的类型不能被析构，也就不能创建自动对象。右边的析构函数是用户提供的，¶15 直接让程序非良构，即使程序从来不 `delete` 一个 `B`。

!!! impl "Itanium ABI：D0、D1、D2"
    Itanium C++ ABI 为每个析构函数最多生成三个变体：D2（base object destructor）作为基类子对象析构，不析构虚基类；D1（complete object destructor）析构完整对象，包括虚基类；D0（deleting destructor）先调用 D1，再调用该类选定的 `operator delete`。只有虚析构函数才有 D0，它和 D1 都放在虚表里。

    静态类型有虚析构函数时，`delete p;` 编译为经虚表调用 D0，`operator delete` 因此由动态类型决定。[[class.free]] 说效果如同虚函数，实现就是这样；¶15 要求定义虚析构函数时就能找到 `operator delete`，也是因为要在那里生成 D0。自动对象和静态对象的析构调用 D1，派生类的析构函数调用基类的 D2。MSVC 的做法不同，它用一个带隐藏标志参数的 scalar deleting destructor。

## 显式析构调用（¶16–¶19）

### 写法与虚分派（¶16）

```cpp run title="explicit-dtor-call.cpp" ok
#include <new>
#include <cstdio>

struct B { virtual ~B() { std::puts("~B"); } };
struct D : B { ~D() { std::puts("~D"); } };

int main() {
    alignas(D) unsigned char buf[sizeof(D)];
    typedef B B_alias;

    B* p = ::new (buf) D;
    p->~B();            // 虚调用：~D ~B
    p = ::new (buf) D;
    p->~B_alias();      // 同上
    p = ::new (buf) D;
    p->B_alias::~B();   // 限定名：只有 ~B
}
```

¶16 显式析构调用写作 `~` 后跟一个表示该类类型的类型名或 `decltype` 说明符。不带限定的 `p->~B()` 和普通虚函数调用一样经虚分派；带限定名的 `p->B_alias::~B()` 不经虚分派，只调用 `B` 的析构函数。最后一次调用之后，`buf` 中对象的生命周期结束了，但 `D` 的析构函数从未运行，这是合法的，通常却是错误。

析构函数的调用遵守成员函数的一般规则（[[class.mfct]]）：对象既不是析构函数所属的类类型、也不是其派生类类型时，行为未定义，通过空指针调用也包括在内。注 7 提醒，对空指针 `delete` 根本不会调用析构函数。

注 8 指出，显式析构调用必须写成成员访问（`p->~X()`、`x.~X()`）或限定名（成员函数中写 `X::~X()`）。在成员函数里单独写 `~X()`，是对临时对象 `X()` 施加一元 `~` 运算符（[[expr.unary.op]]）。

¶17 注 9 说明，显式析构调用很少需要，典型用途是配合 placement new 管理特定地址上的对象，例如内存池、`std::optional`、`std::vector` 的实现。C++17 起可以用 `std::destroy_at(p)`，它也适用于数组，而且不用写出类型名。

### 不要析构两次（¶18）

```cpp title="double-destroy.cpp" ub
#include <string>

int main() {
    std::string s = "a fairly long string that lives on the heap";
    s.~basic_string();   // 生命周期结束
}                        // UB: 块退出时再次析构 s
```

¶18 一旦为某个对象调用了析构函数，它的生命周期就结束了。为生命周期已经结束的对象调用析构函数是未定义行为（[[basic.life]]）。

例 3 就是上面的情形：显式析构了一个自动对象，块又按通常方式退出，再次隐式析构它。本机 AddressSanitizer 报告了重复释放。修复办法是在作用域结束之前，用 placement new 在原位置重新构造一个对象，见 [[basic.life]]。

### 标量类型的伪析构（¶19）

```cpp run title="pseudo-dtor.cpp" ok
#include <new>

template<class T>
void destroy(T* p) { p->~T(); }   // T = int 时是伪析构调用

int main() {
    int i = 1;
    typedef int I;
    I* p = &i;
    p->I::~I();          // 结束 i 的生命周期
    ::new (&i) int(2);   // 重新开始
    destroy(&i);
    ::new (&i) int(3);
    return i - 3;
}
```

¶19 注 10 说明，显式析构调用的写法可以用于任何标量类型名（[[expr.prim.id.dtor]]），这样泛型代码不必区分类型有没有析构函数。C++20 起，这种伪析构调用会结束对象的生命周期（[[basic.life#2]]），此前它什么也不做。这让 `std::destroy_at` 对标量和类类型的行为一致，常量求值也能发现析构之后的使用。

## 历史与演进

!!! history
    - C++98 已有析构函数、虚析构函数、显式析构调用，伪析构调用不做任何事。
    - C++11 起析构函数默认 `noexcept`；引入 `= default`、`= delete` 和定义为弃置的规则。
    - C++20 引入预期析构函数和析构函数的选择（[[P0848R3]]）、`constexpr` 析构函数和销毁型 `operator delete`（[[class.free]]）；伪析构调用改为结束生命周期；类模板中不再允许写 `~X<T>()`。
    - C++26 的平凡联合体（[[P3074R7]]）改为按默认构造函数是否平凡判断联合体的预置析构函数是否删除。

## 常见误解

!!! pitfall "多态基类没有虚析构函数"
    有虚函数的类，析构函数要么是 public 且 virtual，要么是 protected 且非虚，禁止通过基类指针删除。GCC 和 Clang 的 `-Wnon-virtual-dtor` 会对有虚函数却没有虚析构函数的类给出警告。

!!! pitfall "以为 `= default` 的虚析构函数是平凡的"
    虚析构函数永远非平凡（¶8.1），所以多态类型不是平凡可复制的。

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

(1) 在主流实现上 `sizeof(int) == 4`，只有第二个约束满足，选中它。程序良构，但链接时需要它的定义。

(2) `sizeof(double) == 8`，两个约束都满足。`sizeof(T) > 4` 和 `sizeof(T) > 2` 是两个不同的原子约束，约束的偏序只比较原子约束是否相同，不做数值推理，所以谁也不比谁更受约束。重载决议二义，按 ¶4 程序非良构，本机 Clang 23 在实例化 `W<double>` 时报告析构函数二义。

</details>

!!! question "思考题 2"
    为什么 ¶15 要在定义虚析构函数时就查找 `operator delete`，而不是等到出现 `delete` 表达式时再查？

<details markdown="1">
<summary>答案</summary>

在 `delete p;` 处只知道 `p` 的静态类型，而应该调用哪个 `operator delete` 由动态类型决定（[[class.free]]）。知道动态类型的只有它自己的虚析构函数。实现上，删除析构函数 D0 就在虚析构函数的定义处生成，并在那里调用该类的 `operator delete`。所以查找必须在那时进行，即使程序从不 `delete` 这个类的对象。

</details>
