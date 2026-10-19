---
title: 对象的诞生与消亡
summary: 编译器什么时候替类声明特殊成员函数，初始化时什么时候复制、移动或什么都不做，以及 noexcept 移动、平凡可复制和构造析构顺序在实际程序里的表现。
status: draft
order: 60
since: c++11
papers: P0135R1, P2266R3
related: special, class.ctor, class.copy.ctor, class.copy.assign, class.dtor, class.base.init, class.copy.elision, class.temporary, class.prop, basic.types.trivial, depr.impldec, expr.call, topics/value-categories
tags: 特殊成员函数, 复制消除, 移动语义, Rule of five, 平凡可复制
updated: 2026-10-19
---

!!! tldr
    - 用户声明了析构函数、复制构造或复制赋值中的任何一个，移动操作就不再隐式声明，按右值传入时会悄悄退回复制。
    - 函数不声明和函数被删除是两回事：前者重载决议看不到它，后者选中它就报错。
    - 用同类型的 prvalue 初始化对象时什么都不发生，目标就是 prvalue 的结果对象；`return local;` 可能被省略（NRVO），不省略时也是移动。
    - 移动构造函数不是 `noexcept` 时，`std::vector` 扩容会复制元素而不是移动。
    - 写一个空的 `~T() {}` 会让类型不再平凡可复制；需要显式声明时用 `= default`。

## 一个空析构函数让移动变成了复制

```cpp run title="silent-copy.cpp" ok
#include <cstdio>
#include <utility>

struct Logged {
    Logged() = default;
    Logged(const Logged&) { std::puts("copy"); }
    Logged(Logged&&) noexcept { std::puts("move"); }
};

struct WithDtor {
    Logged l;
    ~WithDtor() {}            // 用户声明了析构函数：不再隐式声明移动构造函数
};

struct Plain {
    Logged l;                 // 什么都没声明：有隐式的移动构造函数
};

int main() {
    WithDtor a;
    WithDtor b(std::move(a)); // copy：没有移动构造函数，选中了隐式的复制构造函数
    Plain c;
    Plain d(std::move(c));    // move
}
```

程序输出 `copy`，然后是 `move`。`WithDtor` 只多了一个什么也不做的析构函数，移动就变成了复制。原因在于编译器替类声明哪些函数的规则。

**特殊成员函数**（special member function）有六个：默认构造函数、复制构造函数、移动构造函数、复制赋值运算符、移动赋值运算符、析构函数（[[special]]）。用户没有声明它们时，编译器在一定条件下隐式声明，并且通常声明为**预置**（defaulted）的，也就是由编译器按逐成员的方式生成。

## 编译器替你声明什么

各条规则的出处：

- 默认构造函数：没有任何用户声明的构造函数时隐式声明（[[class.default.ctor#1]]）。
- 复制构造函数：没有用户声明的复制构造函数时隐式声明。如果类声明了移动构造或移动赋值，隐式的复制构造函数定义为删除。如果类有用户声明的复制赋值或析构函数，隐式声明为预置的做法已被弃用（[[class.copy.ctor#6]]、[[depr.impldec]]）。
- 移动构造函数：只有在没有用户声明的复制构造、复制赋值、移动赋值、析构函数时才隐式声明（[[class.copy.ctor#8]]）。
- 复制赋值、移动赋值：与上面两条对称（[[class.copy.assign#2]]、[[class.copy.assign#4]]）。
- 析构函数：没有用户声明的析构函数时隐式声明（[[class.dtor]]）。

这里的用户声明包括写成 `= default` 和 `= delete` 的声明。把规则排成表：

| 用户声明了 ↓ / 编译器提供 → | 默认构造 | 析构 | 复制构造 | 复制赋值 | 移动构造 | 移动赋值 |
|---|---|---|---|---|---|---|
| 什么都没有 | 预置 | 预置 | 预置 | 预置 | 预置 | 预置 |
| 任意构造函数 | 不声明 | 预置 | 预置 | 预置 | 预置 | 预置 |
| 默认构造 | 用户 | 预置 | 预置 | 预置 | 预置 | 预置 |
| 析构函数 | 预置 | 用户 | 预置（弃用） | 预置（弃用） | 不声明 | 不声明 |
| 复制构造 | 不声明 | 预置 | 用户 | 预置（弃用） | 不声明 | 不声明 |
| 复制赋值 | 预置 | 预置 | 预置（弃用） | 用户 | 不声明 | 不声明 |
| 移动构造 | 不声明 | 预置 | 删除 | 删除 | 用户 | 不声明 |
| 移动赋值 | 预置 | 预置 | 删除 | 删除 | 不声明 | 用户 |

表里有两种没有，要分清：

- 不声明：这个函数不存在，重载决议看不到它。声明了析构函数的类没有移动构造函数，`T b(std::move(a));` 于是选中复制构造函数，因为 `const T&` 也能绑定右值。代码照常编译，只是变成了复制。
- 删除：函数存在，参与重载决议，选中它就是错误。声明了移动操作的类，复制构造函数是删除的，`T b = a;` 直接编译失败。

表中的预置只说明函数被声明为预置，它仍可能被定义为删除。例如类有一个不可复制的成员，隐式的复制构造函数就是删除的（[[class.copy.ctor#10]]）。其中有一个例外：定义为删除的预置移动操作会被排除出候选集（[[over.match.funcs.general#9]]），这样在移动做不到时会退回复制，而不是报错。

## Rule of 0、3、5

上表直接导出三条经验法则：

- **Rule of 0**：如果类只是组合了自己管理资源的成员，比如 `std::string`、`std::vector`、`std::unique_ptr`，就一个特殊成员都不写。编译器生成的六个函数逐成员操作，做的就是正确的事；只要成员的移动不抛出，生成的移动也是 `noexcept` 的。
- **Rule of 3**（C++98）：如果需要自定义析构函数、复制构造、复制赋值中的任何一个（通常是因为手工管理资源），那么三个都需要自定义。
- **Rule of 5**（C++11）：在三个之外再加上移动构造和移动赋值。按上表，声明了前三者中的任何一个，移动操作就不再隐式声明，不显式提供就只能复制。

多态基类需要虚析构函数，这时常见的写法是把其余几个显式预置：

```cpp run title="rule-of-5-defaults.cpp" ok
#include <type_traits>

struct Base {
    virtual ~Base() = default;               // 用户声明了析构函数，移动不再隐式声明
    Base() = default;
    Base(const Base&) = default;             // 所以把其余的都显式预置
    Base& operator=(const Base&) = default;
    Base(Base&&) = default;
    Base& operator=(Base&&) = default;
};

static_assert(std::is_nothrow_move_constructible_v<Base>);
int main() {}
```

多态基类是否应当允许复制，以免发生切片，是设计问题，不是语言规则。

## 复制、移动，还是什么都不发生

用表达式 `e` 初始化一个 `T` 类型的对象时，发生什么取决于 `e` 的值类别（[[basic.lval]]）：

| `e` 是 | 例子 | 结果 | 依据 |
|---|---|---|---|
| `T` 类型的 prvalue | `T()`、返回 `T` 的 `f()`、`T{1, 2}` | 什么都不发生，目标就是 `e` 的结果对象 | [[dcl.init#15.6.1]]、[[basic.lval#5]] |
| `T` 类型的 xvalue | `std::move(a)`、`return local;` | 移动构造，没有移动构造函数时复制 | 重载决议 |
| `T` 类型的 lvalue | `a`、`*p`、`arr[0]` | 复制构造 | 重载决议 |
| 其他类型 | `T x = 42;` | 经转换构造函数或转换函数得到 prvalue，然后同第一行 | [[dcl.init]] |

第一行是 C++17 的保证（[[P0135R1]]）：prvalue 不再是一个需要复制的临时对象，而是一个初始化方式，最终在目标的位置上直接构造。所以不可复制、不可移动的类型，比如 `std::mutex`，也能从返回 prvalue 的工厂函数按值返回。

在此之上，[[class.copy.elision]] 列出了实现可以省略一次复制或移动的几个场合：`return` 一个局部对象（称为 NRVO，具名返回值优化）、`throw` 一个局部对象、协程形参的复制、`catch` 按值捕获。这些省略是可选的。实践中，函数只有一个返回变量时 GCC 和 Clang 会可靠地做 NRVO。

省略没有发生时，还有一条兜底规则：`return local;` 和 `throw local;` 里的名字是**可隐式移动**（move-eligible）的，作为 xvalue 处理（[[expr.prim.id.unqual#15]]，C++23 起由 [[P2266R3]] 简化成这种形式），所以是移动而不是复制。

常见写法的开销（C++17 起，GCC 和 Clang）：

| 写法 | 开销 |
|---|---|
| `T x = T(args);`、`T x = make();`（`make` 返回 prvalue） | 1 次构造 |
| `T make() { T t; ...; return t; }` | 1 次构造（NRVO）；NRVO 不发生时再加 1 次移动 |
| `T f(T p) { return p; }` | 形参不能 NRVO，再加 1 次移动 |
| `return cond ? a : b;` | 再加 1 次复制，条件表达式不是可隐式移动的名字 |
| `return std::move(t);` | 再加 1 次移动，并且阻止了 NRVO |
| `f(T(args))`，形参按值 | 1 次构造，形参就是结果对象 |
| `f(a)`，形参按值，`a` 是左值 | 再加 1 次复制 |

## `noexcept` 移动与 `std::vector` 扩容

`std::vector` 扩容时要把旧元素搬到新内存。按 [[vector.modifiers#2]]，在末尾插入单个元素时如果抛出异常，只要 `T` 可复制插入或 `is_nothrow_move_constructible_v<T>` 为真，就不能有任何效果，这就是强异常保证。

如果用移动构造函数搬运元素，移动到一半抛出异常，旧内存里的元素已经被移走，无法恢复原状。所以实现只在移动构造函数是 `noexcept` 的（或者类型不可复制）时才移动，否则复制。标准库用 `std::move_if_noexcept` 表达这个选择。

```cpp run title="vector-growth.cpp" ok
#include <cstdio>
#include <vector>

template<bool NoExcept>
struct T {
    int id;
    T(int i) : id(i) {}
    T(const T& o) : id(o.id)                 { std::printf("copy%d ", id); }
    T(T&& o) noexcept(NoExcept) : id(o.id)   { std::printf("move%d ", id); }
};

int main() {
    {
        std::vector<T<false>> v;
        v.reserve(2); v.emplace_back(1); v.emplace_back(2);
        std::printf("扩容（移动可能抛出）: ");
        v.emplace_back(3);     // copy1 copy2
        std::puts("");
    }
    {
        std::vector<T<true>> v;
        v.reserve(2); v.emplace_back(1); v.emplace_back(2);
        std::printf("扩容（noexcept 移动）: ");
        v.emplace_back(3);     // move1 move2
        std::puts("");
    }
}
```

所以移动构造函数和移动赋值运算符几乎总应当是 `noexcept` 的。隐式生成或 `= default` 的移动操作，异常说明由成员推导（[[except.spec]]），成员的移动不抛出时它自动是 `noexcept`。这也是 Rule of 0 的好处之一。

## 平凡可复制与 `memcpy`

**平凡可复制**（trivially copyable）的类型可以绕过特殊成员函数，直接按字节复制。按 [[class.prop#1]]，一个类是平凡可复制的，当且仅当它满足三个条件：至少有一个合格的复制或移动构造函数、复制或移动赋值运算符（合格指未删除、约束满足，见 [[special]]）；每个合格的这类函数都是平凡的；有一个平凡且未删除的析构函数。

平凡大致是说函数由编译器生成，并且不需要做任何额外的事：不是用户提供的，类没有虚函数和虚基类，所有子对象对应的操作也平凡（[[class.copy.ctor#12]]）。在首次声明处写的 `= default` 不算用户提供，不影响平凡性；写一个空的 `~T() {}` 就会破坏它。

```cpp run title="trivially-copyable.cpp" ok
#include <cstring>
#include <string>
#include <type_traits>

struct P  { int x; double y; };
struct P2 { int x; P2() = default; P2(const P2&) = default; ~P2() = default; };  // 仍平凡
struct P3 { int x; ~P3() {} };                     // 用户提供的析构函数：不再平凡可复制
struct P4 { std::string s; };                      // 成员不平凡：不再平凡可复制
struct P5 { int x; virtual void f() {} };          // 虚函数：不再平凡可复制

static_assert(std::is_trivially_copyable_v<P>);
static_assert(std::is_trivially_copyable_v<P2>);
static_assert(!std::is_trivially_copyable_v<P3>);
static_assert(!std::is_trivially_copyable_v<P4>);
static_assert(!std::is_trivially_copyable_v<P5>);

int main() {
    P a{1, 2.0}, b{};
    std::memcpy(&b, &a, sizeof(P));   // OK：b 获得 a 的值
    return b.x == 1 ? 0 : 1;
}
```

对平凡可复制类型，[[basic.types.trivial#3]] 和 [[basic.types.trivial#4]] 保证：把对象的字节复制到 `char`、`unsigned char` 或 `std::byte` 数组再复制回来，或者从一个对象直接复制到另一个（非潜在重叠的）对象，目标对象就获得源对象的值。`std::memcpy` 复制结构体、`std::bit_cast`、二进制序列化都以此为依据。

这还有 ABI 层面的后果。[[class.temporary#3]] 允许实现为传参和返回额外创建临时对象，条件是类型的合格复制、移动构造函数都平凡，析构函数平凡或被删除。主流 ABI 据此用寄存器传递这类小对象。一个空的用户析构函数不仅让 `memcpy` 失去依据，还可能让一个两个 `int` 大小的对象从寄存器传递变成经内存传递。

## 构造与析构的顺序

按 [[class.base.init#15]] 和 [[class.dtor]]：

1. 构造：虚基类（只由最派生类构造，深度优先、从左到右），然后直接基类（声明顺序），然后非静态数据成员（声明顺序），最后是构造函数体。
2. 析构：析构函数体，然后非静态数据成员（声明逆序），然后直接基类（声明逆序），最后虚基类（只由最派生类析构，构造的逆序）。

构造和析构期间，对象在多态意义上是当前构造函数或析构函数所属的类（[[class.cdtor]]），虚调用、`typeid`、`dynamic_cast` 都看不到更派生的部分。构造中途抛出异常时，已经构造完的子对象按逆序析构，对象本身的析构函数不会调用；委托构造函数的函数体抛出是例外，这时目标构造函数已经完成，对象的析构函数会被调用（[[except.ctor]]）。

## 逐行追踪

下面用一个打印全部特殊成员函数的类型，把前面的规则落到一段具体程序上。每个对象构造时得到一个新编号 `#n`。

```cpp run title="trace.cpp" ok
#include <cstdio>
#include <utility>
#include <vector>

struct Tr {
    static inline int next = 0;
    int id;
    Tr() : id(++next)                  { std::printf("  #%d Tr()\n", id); }
    Tr(const Tr& o) : id(++next)       { std::printf("  #%d Tr(const Tr&) <- #%d\n", id, o.id); }
    Tr(Tr&& o) noexcept : id(++next)   { std::printf("  #%d Tr(Tr&&) <- #%d\n", id, o.id); }
    Tr& operator=(const Tr& o)         { std::printf("  #%d = copy #%d\n", id, o.id); return *this; }
    Tr& operator=(Tr&& o) noexcept     { std::printf("  #%d = move #%d\n", id, o.id); return *this; }
    ~Tr()                              { std::printf("  #%d ~Tr()\n", id); }
};

Tr factory() { Tr t; return t; }       // 可以 NRVO
Tr pass(Tr p) { return p; }            // 形参：只能隐式移动

struct Holder {
    Tr m;
    Holder(Tr x) : m(std::move(x)) {}
};

int main() {
    std::puts("[1] Tr a = factory();");
    Tr a = factory();
    std::puts("[2] Tr b = pass(a);");
    Tr b = pass(a);
    std::puts("[3] Holder h(Tr{});");
    Holder h(Tr{});
    std::puts("[4] a = pass(Tr{});");
    a = pass(Tr{});
    std::puts("[5] vector");
    std::vector<Tr> v;
    v.reserve(1);
    v.push_back(b);
    v.push_back(std::move(a));
    std::puts("[6] end of main");
}
```

下面是本机 Clang 23 + libc++ 的输出，逐段解释。

**[1] `Tr a = factory();`**

```text
  #1 Tr()
```

`factory()` 是 prvalue，`a` 是它的结果对象（[[dcl.init#15.6.1]]）。`factory` 里的 `return t;` 满足 NRVO 的条件（[[class.copy.elision#1]] ¶1.1），Clang 把 `t` 直接构造在 `a` 的存储里，全程只有一次构造。用 `-fno-elide-constructors` 编译，这里会多出一次从 `t` 到 `a` 的 `Tr(Tr&&)` 和一次析构。

**[2] `Tr b = pass(a);`**

```text
  #2 Tr(const Tr&) <- #1
  #3 Tr(Tr&&) <- #2
  #2 ~Tr()
```

`a` 是左值，按值的形参 `p` 由复制构造（#2）。`return p;` 中形参不能 NRVO，但 `p` 是可隐式移动的，于是移动构造返回值，返回值的结果对象就是 `b`（#3）。最后形参 #2 销毁。形参在函数返回时销毁，还是在调用所在的完整表达式结束时销毁，由实现定义（[[expr.call#7]]）；Itanium ABI 由调用方在完整表达式末尾销毁。

**[3] `Holder h(Tr{});`**

```text
  #4 Tr()
  #5 Tr(Tr&&) <- #4
  #4 ~Tr()
```

实参 `Tr{}` 是 prvalue，形参 `x` 就是它的结果对象（#4），没有复制。*mem-initializer* `m(std::move(x))` 用 xvalue 直接初始化成员，于是移动构造（#5）。然后形参 #4 销毁。成员 `m` 必须位于 `h` 内部，不能占用形参的存储，所以这次移动无法避免。按值接收再移动进成员的写法，代价就是这一次移动。

**[4] `a = pass(Tr{});`**

```text
  #6 Tr()
  #7 Tr(Tr&&) <- #6
  #1 = move #7
  #7 ~Tr()
  #6 ~Tr()
```

`Tr{}` 直接成为形参 `p`（#6），`return p;` 隐式移动到返回值（#7）。这次返回值不是用来初始化一个对象，而是作为 `operator=(Tr&&)` 的实参。引用要绑定到 prvalue，于是发生**临时量实质化**（temporary materialization，[[class.temporary#2]]），#7 就是这个临时对象。接着移动赋值给 `a`，它的编号仍是 #1，因为赋值不创建对象。完整表达式结束时，先销毁临时对象 #7，再销毁形参 #6。

**[5] `std::vector`**

```text
  #8 Tr(const Tr&) <- #3
  #9 Tr(Tr&&) <- #1
  #10 Tr(Tr&&) <- #8
  #8 ~Tr()
```

`v.push_back(b)` 中 `b` 是左值，复制进容量为 1 的缓冲区（#8）。`v.push_back(std::move(a))` 时容量不足，需要扩容。libc++ 先在新缓冲区里构造新元素（#9，从 `a` 移动），再把旧元素搬过去（#10，从 #8 移动，因为 `Tr` 的移动构造函数是 `noexcept` 的），最后销毁旧元素 #8。去掉 `Tr(Tr&&)` 的 `noexcept`，#10 这一行会变成 `Tr(const Tr&)`。

**[6] `main` 结束**

```text
  #9 ~Tr()
  #10 ~Tr()
  #5 ~Tr()
  #3 ~Tr()
  #1 ~Tr()
```

局部变量按构造的逆序销毁（[[stmt.jump]]）：先是 `v`，再是 `h`（成员 `m` 是 #5），再是 `b`（#3），最后是 `a`（#1）。`v` 先销毁 `v[1]`（#9）再销毁 `v[0]`（#10），元素的销毁顺序由库决定。

一共构造了 10 个对象，析构了 10 次。即使发生了复制消除，每次构造也恰好对应一次析构（[[class.copy.elision#1]] 注 1）。

## 小结

- 能用 Rule of 0 就用 Rule of 0。
- 需要虚析构函数时，用 `= default` 显式恢复其余几个，或者明确地 `= delete` 复制。
- 移动操作写成 `noexcept`，可以用 `static_assert(std::is_nothrow_move_constructible_v<T>)` 检查。
- 工厂函数返回 prvalue（`return T(...);`）或单一的局部变量，不要写 `return std::move(local);`。
- 想用 `memcpy` 复制，就保证类型平凡可复制：不写空的析构函数，用 `= default`。
- 复制构造函数里不要有业务上的副作用，它会不会被调用取决于复制消除。

值类别与 prvalue 的语义见 [[topics/value-categories]]。
