---
title: 异常说明
summary: 函数能否以异常退出由它的异常说明决定：noexcept 的写法，不写时的默认值（析构函数和释放函数默认不抛出），潜在抛出表达式的定义，编译器生成的函数怎样推导异常说明，虚函数覆盖的约束，以及异常说明作为函数类型一部分的后果。
status: done
since: c++11
papers: N3050, P0003R5, P0012R1, P0619R4, P1286R2, P3668R4
related: except.handle, except.terminate, expr.unary.noexcept, dcl.fct, conv.fctptr, class.virtual, class.dtor, basic.link, temp.explicit, toolchain/exception-implementation
tags: 异常, noexcept, 异常说明, 函数类型
updated: 2026-10-19
---

!!! tldr
    - 异常说明只区分两种情况：函数可能以异常退出（潜在抛出），或者不会（非抛出）。它不列出会抛哪些类型。
    - `noexcept` 是承诺而不是编译期检查：异常真的离开 `noexcept` 函数时，程序调用 `std::terminate`。
    - 没写 `noexcept` 的函数默认潜在抛出；析构函数、释放函数和首次声明即预置的函数例外，它们的异常说明由编译器推导，析构函数通常推导为非抛出。
    - `noexcept(expr)` 运算符的结果取决于表达式里有没有潜在抛出的子表达式，临时对象的析构也算在内。
    - C++17 起异常说明是函数类型的一部分：`noexcept` 函数的指针可以转成普通函数指针，反之不行；覆盖非抛出虚函数的函数也必须非抛出。

```cpp run title="vector-move-if-noexcept.cpp" ok
#include <cstdio>
#include <vector>

template<bool NX>
struct W {
    W() = default;
    W(const W&) { std::puts("  copy"); }
    W(W&&) noexcept(NX) { std::puts("  move"); }
};

int main() {
    std::puts("noexcept move:");
    std::vector<W<true>> a(1);  a.reserve(2);    // 扩容时移动
    std::puts("potentially-throwing move:");
    std::vector<W<false>> b(1); b.reserve(2);    // 扩容时拷贝
}
```

两个 `vector` 的元素类型只差一个 `noexcept`，扩容时的行为却不同：移动构造函数不抛出时，`vector` 移动元素；可能抛出时，它改为拷贝。原因是扩容要提供强异常安全保证，即失败时原来的元素保持不变。移动到一半抛出，原来的元素已经被移走了，无法恢复；拷贝失败则不影响原来的元素。`vector` 在编译期查询移动构造函数的异常说明，据此选择算法。

忘记给移动构造函数加 `noexcept`，`vector` 就会默默地拷贝。预置的移动构造函数（`= default`）会自动推导出正确的异常说明，这是推荐写 `= default` 的理由之一。

## 异常说明是一个谓词（¶1–¶3）

¶1 函数不能以异常退出这个谓词，叫做函数的**异常说明**（[[g:exception-specification]]）。谓词为假，函数具有**潜在抛出的异常说明**（[[g:potentially-throwing-exception-specification]]）；为真，则具有**非抛出的异常说明**（[[g:non-throwing-exception-specification]]）。异常说明可以由函数声明符末尾的 *noexcept-specifier* 显式给出，也可以隐式确定：

```text
noexcept-specifier:
    noexcept ( constant-expression )
    noexcept
```

¶2 不带表达式的 `noexcept` 等价于 `noexcept(true)`。括号里的表达式必须是类型为 `bool` 的按语境转换的常量表达式（[[expr.const.const]]），因此不允许窄化：

```cpp title="noexcept-narrowing.cpp" error
void f() noexcept(sizeof(char[2]));  // error: 2 转换到 bool 是窄化
void g() noexcept(sizeof(char));     // OK：1 转换到 bool 不是窄化
```

`noexcept(...)` 里写的常常是一个复杂条件。如果 `noexcept(sizeof(T))` 这类笔误被默默当成 `true`，一个可能抛出的函数就被标成了不抛出，后果是运行时终止。

¶2 还规定，紧跟在 `noexcept` 之后的 `(` 属于 *noexcept-specifier*，不会开始一个初始化器：

```cpp title="noexcept-paren.cpp" ok
void target() noexcept;
void (*p1)() noexcept (false);     // p1 是潜在抛出函数的指针，没有初始化器
void (*p2)() noexcept = target;    // 要初始化，用 = 或 {}
void (*p3)() noexcept {target};
```

没有这条规则，`(false)` 也可以读成用 `false` 直接初始化 `p1`。

¶3 *noexcept-specifier* 出现在函数类型中时，其中的常量表达式就是这个类型的异常说明。异常说明是函数类型的一部分，后文专门讨论。

## 潜在抛出的表达式（¶6）

编译器怎样判断一个表达式会不会抛出？¶6 给出了定义。表达式 `E` 是**潜在抛出的**（[[g:potentially-throwing-expression]]），如果：

- ¶6.1 `E` 是函数调用，被调用的函数类型或函数指针类型具有潜在抛出的异常说明；
- ¶6.2 `E` 隐式调用了一个具有潜在抛出异常说明的函数，例如重载运算符、*new-expression* 中的分配函数、为函数实参调用的构造函数、析构函数；
- ¶6.3 `E` 是 *throw-expression*；
- ¶6.4 `E` 是转换到引用类型、需要运行时检查的 `dynamic_cast`，失败时抛出 `std::bad_cast`；
- ¶6.5 `E` 是作用于 `*p` 的 `typeid`，其中 `p` 指向多态类类型，`p` 为空时抛出 `std::bad_typeid`；
- ¶6.6 `E` 的某个直接子表达式是潜在抛出的，未求值操作数除外。

这个判断是静态的、保守的：它只看类型上的异常说明，不看函数实际会不会抛出。`noexcept` 运算符（[[expr.unary.noexcept]]）的结果，就是操作数不是潜在抛出的表达式。

```cpp title="potentially-throwing.cpp" ok
#include <new>
#include <typeinfo>

struct Poly { virtual ~Poly(); };
struct Der : Poly {};
struct Thr { ~Thr() noexcept(false); };
Thr make_thr() noexcept;

void may();
int may_int();
void never() noexcept;
int x;
Poly* pp;

static_assert(!noexcept(may()));                    // 6.1
static_assert( noexcept(never()));
static_assert(!noexcept(new int));                  // 6.2：operator new 潜在抛出
static_assert( noexcept(new (&x) int));             // 定位 operator new 不抛出
static_assert(!noexcept(throw 1));                  // 6.3
static_assert(!noexcept(dynamic_cast<Der&>(*pp)));  // 6.4
static_assert( noexcept(dynamic_cast<Der*>(pp)));   // 转换到指针：失败返回空指针
static_assert(!noexcept(typeid(*pp)));              // 6.5
static_assert( noexcept(typeid(pp)));               // 没有解引用多态指针
static_assert(!noexcept(make_thr()));               // 6.2：临时对象的析构函数
static_assert( noexcept(x + 1));
static_assert( noexcept(sizeof(may_int())));        // 6.6：未求值操作数不算
```

`make_thr()` 那一行容易看错。`make_thr` 本身是 `noexcept` 的，但 `noexcept` 运算符会把 prvalue 操作数实质化成临时对象（[[expr.unary.noexcept#1]]），这个临时对象在完整表达式结束时析构，而 `Thr` 的析构函数潜在抛出。（Clang 会对未求值操作数里的 `new`、`throw` 警告副作用无效，这是预期的。）

## 不写 noexcept 时（¶4、¶8、¶10）

¶4 不带 *noexcept-specifier* 的函数声明默认潜在抛出，但有三类例外：

- 析构函数（¶8）；
- 释放函数，即 `operator delete` 系列（¶10）；
- 在首次声明时就预置（`= default`）的函数（¶7、¶9、¶11，见下一节）。

### 析构函数默认不抛出（¶8）

¶8 隐式声明的析构函数，以及没有 *noexcept-specifier* 的析构函数（包括用户自己写了函数体的），只在下面两种情况下潜在抛出：某个潜在构造子对象（基类和非静态数据成员，[[class.base.init]]）的析构函数潜在抛出；或者析构函数是虚函数，而某个虚基类的析构函数潜在抛出。

```cpp title="dtor-implicit-noexcept.cpp" ok
#include <type_traits>

struct User { ~User() { /* 即使这里 throw，也是 noexcept */ } };
static_assert(std::is_nothrow_destructible_v<User>);

struct Loud { ~Loud() noexcept(false); };
struct Holder { Loud l; };                 // 子对象潜在抛出，于是潜在抛出
static_assert(!std::is_nothrow_destructible_v<Holder>);

struct Holder2 { Loud l; ~Holder2() {} };  // 用户提供、没写说明：同样按子对象推导
static_assert(!std::is_nothrow_destructible_v<Holder2>);
```

这就是析构函数默认 `noexcept` 的准确含义。只要没写 `noexcept(false)`，而且子对象的析构函数都不抛出，它就是非抛出的，函数体里的 `throw` 会导致 `std::terminate`。

析构函数默认不抛出有两个原因。析构函数在栈回溯中被调用，那时再抛出异常就会终止程序（[[except.throw]]）；标准库容器也要求元素的析构函数不抛出（[[res.on.exception.handling]]）。把不抛出设为默认值，绝大多数代码自动得到正确的语义，编译器也可以省掉调用方的清理代码。

### 释放函数默认不抛出（¶10）

¶10 没有显式 *noexcept-specifier* 的释放函数是非抛出的。释放函数会在 *new-expression* 构造失败、正在传播异常的时候被调用（[[except.ctor]]），这时它不能再抛出。

```cpp title="dealloc-noexcept.cpp" ok
#include <cstddef>

struct Pool {
    static void* operator new(std::size_t);
    static void  operator delete(void*);      // 隐式 noexcept
};
static_assert(noexcept(Pool::operator delete(nullptr)));
static_assert(!noexcept(Pool::operator new(1)));
```

### 其他声明不能再写 noexcept（¶4）

对这三类函数，¶4 还规定：只要有一个声明没写 *noexcept-specifier*，这个函数的其他声明就都不能写。所以析构函数的 `noexcept` 要么每个声明都写，要么都不写：

<div class="compare" markdown="1">

```cpp error
struct S { ~S(); };
S::~S() noexcept {}  // error
```

```cpp ok
struct S { ~S() noexcept(false); };
S::~S() noexcept(false) {}
```

</div>

Clang 23 对左边只给出警告（`-Wimplicit-exception-spec-mismatch`），反过来写成 `~T() noexcept;` 加 `T::~T() {}` 也一样。按 [[intro.compliance]]，警告也算诊断，但程序仍是非良构的。

对普通函数，各声明的异常说明不同就是类型不同，由 [[basic.link#11]] 处理：

```cpp title="redecl-mismatch.cpp" error
void k();
void k() noexcept;   // error: 与之前的声明类型不同
```

¶4 后半处理显式实例化（[[temp.explicit]]）：显式实例化可以写 *noexcept-specifier*，也可以不写；写了就必须与这个函数其他声明的异常说明相同。只有不一致出现在同一个翻译单元里时才要求诊断。

```cpp title="explicit-inst.cpp" error
template<class T> void tf(T) noexcept(sizeof(T) > 1) {}

template void tf<int>(int) noexcept;     // OK：一致
template void tf<char>(char);            // OK：不写也行
template void tf<char>(char) noexcept;   // error: tf<char> 是 noexcept(false)
```

## 编译器生成的函数（¶7、¶9、¶11–¶12）

编译器生成的函数，异常说明取决于它实际会调用什么：如果它会调用潜在抛出的函数，或者含有潜在抛出的表达式，它就潜在抛出。这适用于隐式声明的函数，以及首次声明即预置而且没写 *noexcept-specifier* 的函数。

¶7 构造函数在下列任一项潜在抛出时潜在抛出：为初始化潜在构造子对象而选中的构造函数的调用（¶7.1）；这种初始化的子表达式，例如默认实参（¶7.2）；对默认构造函数，还有默认成员初始化器（¶7.3）。

注 1 解释了一个看似遗漏的地方。构造函数中途抛出时，已构造子对象的析构函数会被调用（[[except.ctor]]），但它们不参与推导。因为这时析构函数如果再抛出，会直接调用 `std::terminate`，异常不会离开构造函数。

¶9 赋值运算符在隐式定义中调用的某个赋值运算符潜在抛出时潜在抛出。

¶11 比较运算符函数（[[class.compare]]），以及预置的后缀自增、自减运算符函数（[[over.inc]]，{{c++29}} [[P3668R4]]），在隐式定义中有潜在抛出的表达式时潜在抛出。

```cpp title="defaulted-compare.cpp" ok
#include <string>

struct P { int a, b; bool operator==(const P&) const = default; };
static_assert(noexcept(P{} == P{}));

struct Q {
    std::string s;
    auto operator<=>(const Q&) const = default;
    bool operator==(const Q&) const = default;
};
static_assert(noexcept(Q{} == Q{}) == noexcept(std::string{} == std::string{}));
```

预置的后缀 `++` 在本机 Clang 23 上还不能编译（`only special member functions and comparison operators may be defaulted`）。

¶12 标准的例 3 把这些规则放在一起：

```cpp title="except-spec-example.cpp" ok
#include <new>
#include <type_traits>
#include <utility>

struct A {
    A(int = (A(5), 0)) noexcept;
    A(const A&) noexcept;
    A(A&&) noexcept;
    ~A();                                 // 隐式 noexcept(true)
};
struct B {
    B() noexcept;
    B(const B&) = default;                // 推导为 noexcept(true)
    B(B&&, int = (throw 42, 0)) noexcept; // 默认实参会抛出
    ~B() noexcept(false);
};
int n = 7;
struct D : public A, public B {
    int* p = new int[n];
    // D::D()         潜在抛出：默认成员初始化器里的 new
    // D::D(const D&) 非抛出
    // D::D(D&&)      潜在抛出：B(B&&, int) 的默认实参会抛出（7.2）
    // D::~D()        潜在抛出：B::~B 潜在抛出
};

static_assert(!std::is_nothrow_default_constructible_v<D>);
static_assert(!std::is_nothrow_move_constructible_v<D>);
static_assert(!std::is_nothrow_destructible_v<D>);
static_assert(!noexcept(D(std::declval<const D&>())));
static_assert( noexcept(::new (static_cast<void*>(nullptr)) D(std::declval<const D&>())));
```

最后两个断言值得注意。`D(const D&)` 本身是非抛出的，但表达式 `D(...)` 还包括临时对象的析构，`D::~D()` 潜在抛出，所以结果是 `false`。用定位 new 构造就没有临时对象，查询到的才是构造函数自己的异常说明。

例 3 最后还说，如果 `A::~A()` 是虚函数，程序就非良构：`D::~D()` 潜在抛出，却覆盖了一个非抛出的虚函数，违反下面的 ¶5。

## 虚函数覆盖（¶5）

¶5 虚函数是非抛出的，那么任何派生类中覆盖它的函数，所有声明（包括定义）也必须是非抛出的，除非覆盖函数被定义为删除的。

```cpp title="virtual-noexcept.cpp" error
struct B {
    virtual void f() noexcept;
    virtual void g();
    virtual void h() noexcept = delete;
};

struct D : B {
    void f();              // error: B::f 不抛出，覆盖者却潜在抛出
    void g() noexcept;     // OK：收紧承诺
    void h() = delete;     // OK：删除的函数例外
};
```

通过 `B&` 调用 `f()` 的代码依赖不会抛出的承诺，编译器可能据此省掉调用点的清理代码，所以派生类不能放松它。反过来，基类可能抛出而派生类保证不抛出，是收紧承诺，没有问题。

!!! impl "Clang 拒绝删除的覆盖函数"
    本机 Clang 23 对上例的 `void h() = delete;` 也报错 `exception specification of overriding function is more lax than base version`。按 ¶5 的例外，这一行是良构的，这是 Clang 的不符合之处。

最常见的触发场景是虚析构函数。只要某个成员的析构函数是 `noexcept(false)`，派生类的隐式析构函数就潜在抛出，与基类的非抛出虚析构函数冲突。

## 何时计算异常说明（¶13）

¶13 预置函数的异常说明只在需要时才计算。下面几种情况算作需要：

- ¶13.1 在表达式中，重载决议（[[over.match]]、[[over.over]]）选中了这个函数；
- ¶13.2 函数被 odr-use（[[basic.def.odr]]）；
- ¶13.3 要与另一个声明的异常说明比较，例如显式特化或覆盖的虚函数；
- ¶13.4 函数被定义；
- ¶13.5 {{c++26}} 函数被一个反射值表示（[[meta.reflection]]）；
- ¶13.6 一个调用这个函数的预置函数需要异常说明。

为什么要延迟？计算预置函数的异常说明可能需要完整的类和默认成员初始化器。在类定义内部它们可能还没准备好，比如嵌套类的默认构造函数依赖外围类里尚未解析的默认成员初始化器。等到真正有人问的时候再算，就避开了这类循环依赖。

注 2 补充：预置声明本身不要求立即计算基类成员函数的异常说明；但如果预置函数显式写了 *noexcept-specifier*，就需要算出隐式的异常说明来比较。C++20 起，两者不一致时以显式写出的为准（[[P1286R2]]）：

```cpp title="defaulted-explicit-noexcept.cpp" ok
#include <type_traits>

struct Base { Base() noexcept(false); };
struct D1 : Base { D1() = default; };            // 推导为潜在抛出
struct D2 : Base { D2() noexcept = default; };   // 以显式的 noexcept 为准
static_assert(!std::is_nothrow_default_constructible_v<D1>);
static_assert( std::is_nothrow_default_constructible_v<D2>);
```

`D2()` 如果真的从 `Base()` 收到异常，程序会调用 `std::terminate`。

## 异常说明是函数类型的一部分

C++17 起异常说明是函数类型的一部分（[[dcl.fct]]，[[P0012R1]]）：

```cpp title="noexcept-in-type.cpp" ok
#include <type_traits>

void g() noexcept;
void h();

static_assert(!std::is_same_v<decltype(g), decltype(h)>);

void (*p1)() = g;               // OK：函数指针转换，丢掉 noexcept
// void (*p2)() noexcept = h;   // error: 不能凭空加上 noexcept

void take(void (*)());
void take(void (*)() noexcept); // OK：形参类型不同，是两个重载

template<class F> constexpr bool is_nx(F) { return std::is_nothrow_invocable_v<F>; }
static_assert(is_nx(g) && !is_nx(h));
```

| 方面 | 后果 |
|---|---|
| 转换 | `noexcept` 函数的指针可以隐式转换成普通函数指针（函数指针转换，[[conv.fctptr]]），反方向不行 |
| 重载 | 不能只凭异常说明重载同一个函数，但形参可以按是否 `noexcept` 区分 |
| 模板推导 | 传入 `noexcept` 函数时，`F` 推导为 `void(*)() noexcept` |
| 名字修饰 | Itanium ABI 用 `Do` 标记 `noexcept` 函数类型：`void take(void (*)() noexcept)` 修饰为 `_Z4takePDoFvvE`（本机实测） |

因为 `noexcept` 进入了名字修饰，以 `noexcept` 函数指针为形参的接口，在 C++14 和 C++17 下编译会得到不同的符号名。GCC 在 C++17 推出时为此提供了 `-Wnoexcept-type` 警告。

`noexcept` 对代码生成的影响：调用 `noexcept` 函数的地方不需要为异常准备着陆点；`noexcept` 函数自身需要一个捕获一切并调用 `std::terminate` 的着陆点，但可以省掉内部对象的清理，因为 [[except.terminate#2]] 允许此时不回溯或只部分回溯。汇编实例见 [[toolchain/exception-implementation]]。

## 历史与演进

!!! history
    - C++98 的异常说明是动态的：`void f() throw(A, B);` 声明 `f` 只抛出 `A` 或 `B`，违反时调用 `std::unexpected()`。检查在运行时进行，类型列表在模板里几乎写不对，编译器也无法据此优化。实践中只有 `throw()` 有人用。
    - C++11 引入 `noexcept` 说明符和 `noexcept` 运算符（[[N3050]]）。违反时直接调用 `std::terminate`，析构函数默认不抛出，动态异常说明被弃用。
    - C++17 把异常说明并入函数类型（[[P0012R1]]），删除了 `throw(T...)`，只把 `throw()` 保留为 `noexcept(true)` 的弃用写法（[[P0003R5]]）。
    - C++20 删除了 `throw()`（[[P0619R4]]），并允许显式预置的函数写出与推导结果不同的异常说明（[[P1286R2]]）。
    - C++26 起，¶13 增加了被反射值表示的情形。C++26 之后，预置的后缀自增、自减纳入 ¶11。

!!! impl "编译器对旧语法的处理"
    本机 Clang 23 在 `-std=c++2c` 下拒绝 `throw(int)`（`ISO C++17 does not allow dynamic exception specifications`），但即使加 `-pedantic` 也静默接受 `throw()`，把它当作 `noexcept(true)`。按当前标准，`throw()` 在语法上已经不存在。

## 常见误解

!!! pitfall "`noexcept` 会在编译期检查"
    `void f() noexcept { may_throw(); }` 完全合法（[[except.handle#7]] 注 3）。违反承诺的后果是运行时 `std::terminate`。

!!! pitfall "条件 `noexcept` 只测了构造"
    `noexcept(T(std::declval<T>()))` 测的是构造一个临时 `T` 再析构它。对析构函数可能抛出的类型，即使移动构造函数是 `noexcept`，结果也是 `false`。`std::is_nothrow_move_constructible` 在本机 libc++ 上同样把析构算了进去，这是一个已知的库问题（[[LWG2116]]）。

!!! pitfall "`noexcept(false)` 析构函数会传染"
    一个成员的 `~M() noexcept(false)` 让所有包含它的类的隐式析构函数都潜在抛出（¶8），这些类也就不能覆盖非抛出的虚析构函数（¶5）。

## 思考题

!!! question "思考题 1"
    下面的 `b` 是什么？

    ```cpp
    struct S { S(int) noexcept; ~S() noexcept(false); };
    void f(S) noexcept;
    bool b = noexcept(f(1));
    ```

<details markdown="1">
<summary>答案</summary>

`false`。`f(1)` 调用构造函数 `S(int)` 初始化形参（不抛出），再调用 `f`（不抛出），但形参对象最后要析构，而 `~S()` 潜在抛出。¶6.2 明确把为函数实参调用的构造函数和析构函数都算作隐式调用的函数。形参在哪里析构由实现定义（[[expr.call]]），但无论在哪里，它都是这个调用表达式隐式调用的。
</details>

!!! question "思考题 2"
    `struct X { virtual ~X(); }; struct Y : X { std::vector<int> v; };` 中 `Y` 的析构函数是否抛出？把 `std::vector<int>` 换成一个 `~M() noexcept(false)` 的类型 `M` 呢？

<details markdown="1">
<summary>答案</summary>

`X::~X()` 没写说明，按 ¶8 推导：`X` 没有子对象，所以非抛出。`Y` 的隐式析构函数的子对象 `X` 和 `std::vector<int>` 都不抛出，所以也非抛出。

换成 `M` 后，`Y::~Y()` 因 `M::~M()` 而潜在抛出，但它覆盖了非抛出的虚函数 `X::~X()`，违反 ¶5，程序非良构。这正是例 3 最后一句描述的情形。
</details>
