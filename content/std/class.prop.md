---
title: 类的性质
summary: 平凡可复制类、标准布局类（每一条限制的理由、M(X) 集合、首成员地址与 offsetof）、标准布局 struct/union、隐式生存期类；C++26 中平凡类移入附录 D
status: draft
papers: P0848R3, P0593R6, P3247R2
related: basic.types, basic.types.trivial, class.mem, special, intro.object, basic.compound, support.types.layout, depr.meta.types
tags: 平凡可复制, 标准布局, 隐式生存期, memcpy, offsetof
updated: 2026-10-17
---

本节为类类型定义了三种性质（properties），语言在字节层面操作对象时，依据的就是这三种性质：

| 性质 | 一句话 | 带来什么保证 | 类型特征 |
|---|---|---|---|
| **平凡可复制**（trivially copyable）| 复制、移动、析构都不做额外的事 | 按字节复制等于按值复制：`memcpy`、`std::bit_cast`、`std::atomic<T>` | `std::is_trivially_copyable` |
| **标准布局**（standard-layout）| 布局像 C 结构体一样可预测 | 首成员与对象同地址、`offsetof`、公共初始序列、与 C 互操作 | `std::is_standard_layout` |
| **隐式生存期**（implicit-lifetime）| 不运行任何代码就能产生对象 | `malloc`/`memcpy` 得到的存储中可以隐式创建这种对象 | `std::is_implicit_lifetime` |

这三个性质相互独立，¶6 的例子正好覆盖了各种组合。[[basic.types.general]] 在此基础上把标量类型也纳入进来，定义了平凡可复制类型、标准布局类型和隐式生存期类型；本节只讨论类。

!!! note "平凡类去哪了？"
    C++23 及以前，本节还定义了**平凡类**（trivial class）：平凡可复制，并且有一个或多个合格的默认构造函数，这些默认构造函数全都平凡。C++26 草案 {{c++26}} 把这个概念连同 `std::is_trivial` 一起移入附录 D 弃用（[[depr.meta.types#3]]，[[P3247R2]]）。理由是平凡这个概念把“可以 `memcpy`”与“默认构造什么也不做”两件不相关的事捆在一起，几乎没有代码真正需要这个组合；需要的人应该分别查询 `is_trivially_copyable` 和 `is_trivially_default_constructible`。同理，POD 早在 C++20 就已弃用。

!!! note "平凡可重定位？"
    C++26 周期中一度加入了平凡可重定位（trivially relocatable）与可替换（replaceable）两个类性质（[[P2786]]），后来又被撤回，当前草案中不存在。

## 平凡可复制类（¶1）

¶1：一个类是**平凡可复制类**，当且仅当：

- ¶1.1 它至少有一个合格的复制构造函数、移动构造函数、复制赋值运算符或移动赋值运算符；
- ¶1.2 每一个合格的复制/移动构造函数和复制/移动赋值运算符都是平凡的；
- ¶1.3 它有一个平凡的、未弃置的析构函数。

这里完全不涉及默认构造函数。`struct S { int x = 0; };` 有默认成员初始化器，所以默认构造不平凡，但 `S` 仍是平凡可复制的。

### 平凡是什么意思

每种特殊成员函数的平凡性定义在各自的子条款里（[[class.copy.ctor#12]]、[[class.copy.assign#9]]、[[class.dtor#8]]），模式完全一致：

1. 不是用户提供的（user-provided，[[dcl.fct.def.default#5]]），即隐式声明的，或在首次声明处 `= default` 的；
2. 类没有虚函数、没有虚基类（析构函数的版本是析构函数不是虚的）；
3. 对每个基类和类类型成员，选中用来做相应操作的函数也是平凡的。

直观地说，平凡的复制构造和复制赋值就是逐字节复制，平凡的析构就是什么也不做。虚函数和虚基类之所以破坏平凡性，是因为复制时 vptr 和虚基类偏移必须设置为目标对象类型对应的值，不能从源对象逐字节复制过来，因为源可能是更派生类型对象中的基类子对象。

### 为什么要求合格（eligible）

一个特殊成员函数如果未被弃置、约束（若有）得到满足，并且不存在另一个同类、约束更严格且同样满足的特殊成员函数，它就是**合格的特殊成员函数**（[[special#6]]）。这个概念是 C++20 为条件平凡的特殊成员函数（[[P0848R3]]）引入的，动机来自 `std::optional<T>` 这类包装器：当 `T` 平凡可复制时，希望 `optional<T>` 也平凡可复制。C++20 之前只能靠一层层基类模板特化来实现，C++20 起可以直接写：

```cpp run title="conditionally-trivial.cpp" ok
#include <string>
#include <type_traits>

template<class T>
struct Opt {
    Opt(const Opt&) requires std::is_trivially_copy_constructible_v<T> = default;  // #1
    Opt(const Opt&) { /* 手工复制活跃成员 */ }                                      // #2
    T t;
};

// Opt<int>：#1 的约束满足且比无约束的 #2 更受约束 ⇒ 只有 #1 合格，它是平凡的
static_assert(std::is_trivially_copyable_v<Opt<int>>);
// Opt<std::string>：#1 约束不满足 ⇒ 只有 #2 合格，它是用户提供的 ⇒ 非平凡
static_assert(!std::is_trivially_copyable_v<Opt<std::string>>);

int main() { }
```

¶1.2 要求的是每一个合格的函数都平凡。不合格的函数（`Opt<int>` 中的 #2）即使不平凡，也不影响结论。

### 至少一个：复制和移动全部弃置的类

¶1.1 要求至少有一个合格的复制/移动操作。合格要求未被弃置，所以一个把复制和移动全部 `= delete` 的类没有任何合格的此类函数，因此不是平凡可复制的。这符合直觉：作者刻意禁止复制的类型，用 `memcpy` 复制它显然违背作者意图。

```cpp run title="all-deleted.cpp" ok
#include <type_traits>

struct NoCopy {
    NoCopy() = default;
    NoCopy(const NoCopy&) = delete;
    NoCopy& operator=(const NoCopy&) = delete;
};   // 移动操作不被隐式声明（[class.copy.ctor] ¶8）

struct MoveOnly {
    MoveOnly() = default;
    MoveOnly(MoveOnly&&) = default;             // 平凡且合格
    MoveOnly& operator=(MoveOnly&&) = default;  // 平凡且合格
};   // 复制操作被定义为弃置——不合格，不影响结论

static_assert(std::is_trivially_copyable_v<MoveOnly>);   // 标准与 Clang 一致
// 标准：NoCopy 不是平凡可复制的（¶1.1）。
// Clang 23 的 std::is_trivially_copyable_v<NoCopy> 却为 true —— 与当前草案不符，不要依赖。
int main() { }
```

!!! warning "编译器与标准的分歧"
    截至写作时，Clang 23 对 `NoCopy` 这类复制、移动全部弃置的类报告 `is_trivially_copyable == true`（其他编译器请自行验证）。这是实现落后于标准的地方，相关规则来自 C++17 时期的一个核心语言 issue 决议。写可移植代码时，不要依赖这个边界。

### 平凡可复制有什么用

- **按字节复制保值**：[[basic.types.trivial]] 保证，用 `memcpy`/`memmove` 把一个平凡可复制对象的字节复制到另一个同类型对象（或复制出去再复制回来），得到的值相同。
- `std::bit_cast` 要求源和目标都是平凡可复制类型（[[bit.cast]]）。
- `std::atomic<T>` 要求 `T` 平凡可复制。
- **隐式对象创建**：`memcpy` 到新存储会隐式创建对象（[[intro.object]]）。平凡可复制类通常同时是隐式生存期类，因为它有平凡的复制构造函数和平凡的析构函数。
- **ABI**：在 Itanium ABI 中，类对象能否通过寄存器传参，取决于它对调用而言是否平凡（看复制/移动构造与析构）。这与平凡可复制相近，但并不相同，[[basic.types]] 的实现视角部分有详述。

## 标准布局类（¶2）

¶2 给出标准布局类的七条条件。直观地说，标准布局类就是布局可以像 C 结构体一样推断的类：非静态数据成员按声明顺序排列，第一个成员在偏移 0 处，没有隐藏的 vptr，也不会因为同类型子对象必须有不同地址而被迫挪动位置。

类 `S` 满足以下全部条件时，就是标准布局类：

| 列表项 | 条件 | 为什么 |
|---|---|---|
| ¶2.1 | 没有非标准布局类类型（或其数组）的、或引用类型的非静态数据成员 | 标准布局性要递归成立；引用成员在 C 中没有对应物 |
| ¶2.2 | 没有虚函数、没有虚基类 | vptr 和虚基类指针的位置由实现决定（Itanium 放在偏移 0），会破坏首成员地址等于对象地址 |
| ¶2.3 | 所有非静态数据成员的访问控制相同 | 历史上允许实现按访问区段重排成员（见下） |
| ¶2.4 | 没有非标准布局的基类 | 同 ¶2.1，递归 |
| ¶2.5 | 任何给定类型的基类子对象至多一个 | 两个同类型的基类子对象必须地址不同，可能使空基类无法放在偏移 0 |
| ¶2.6 | 类及其基类中的所有非静态数据成员和位域都首先声明于同一个类 | 保证第一个成员唯一确定，并位于偏移 0 |
| ¶2.7 | 没有 *M*(S) 中的类型作为基类 | 防止空基类和第一个成员类型相同而被迫错开 |

### ¶2.6：成员只能集中在一层

条款要求类及其基类中的所有非静态数据成员和位域都首先声明于同一个类。换句话说，继承层次里最多只有一个类有数据成员，其余都是空类。

```cpp run title="sl-hierarchy.cpp" ok
#include <type_traits>

struct B { int i; };              // 标准布局
struct C : B { };                 // 标准布局：数据成员都在 B
struct D : C { };                 // 标准布局
struct E : D { char : 4; };       // 不是：E 有一个（无名）位域，而 i 声明在 B 中（¶2.6）

struct Base { int a; };
struct Derived : Base { int b; }; // 不是：a 在 Base，b 在 Derived

static_assert(std::is_standard_layout_v<D>);
static_assert(!std::is_standard_layout_v<E>);
static_assert(!std::is_standard_layout_v<Derived>);
int main() { }
```

为什么这么严？如果基类和派生类都有数据成员，对象的第一个非静态数据成员是哪一个，就取决于实现如何安排基类子对象与派生类成员。在 Itanium ABI 中，只要基类不是 POD-for-layout，派生类成员就可以放进基类的尾部填充里，这会让按 C 的方式推断布局失效。E 的例子说明，即使是无名位域（它不是成员，[[class.bit#2]]）也算在内，条款原文特意写了 "non-static data members and bit-fields"。

### ¶2.5：同类型基类子对象至多一个

```cpp run title="sl-dup-base.cpp" ok
#include <type_traits>

struct Q { };
struct S : Q { };
struct T : Q { };
struct U : S, T { };          // U 中有两个 Q 子对象

static_assert(!std::is_standard_layout_v<U>);
int main() { }
```

两个 `Q` 子对象是同类型的不同对象，必须有不同的地址（[[intro.object]]），所以不可能都在偏移 0。而标准布局要求对象的地址等于它每一个基类子对象的地址（[[class.mem.general#31]]），这就做不到了。

### ¶2.7 与 *M*(X)：空基类与第一个成员类型相同

这是最微妙的一条。考虑：

```cpp run title="sl-mx.cpp" ok
#include <type_traits>

struct E { };
struct S1 : E { E e; int x; };   // 基类 E 与第一个成员 e 同类型
struct S2 : E { int x; E e; };   // 基类 E 与第一个成员 x 不同类型

static_assert(!std::is_standard_layout_v<S1>);   // E ∈ M(S1)，又是 S1 的基类（¶2.7）
static_assert(std::is_standard_layout_v<S2>);

int main() {
    S1 s;
    // 主流实现：基类 E 占偏移 0，成员 e 被挪到偏移 1 —— 第一个成员不在对象起始地址
    return static_cast<int>(reinterpret_cast<char*>(&s.e) - reinterpret_cast<char*>(&s)) == 1 ? 0 : 1;
}
```

空基类优化希望把空基类 `E` 放在偏移 0，不占空间；第一个成员 `e` 也要在偏移 0。但两者是同类型的不同对象，地址必须不同（脚注 81 说的正是这一点）。实现只好把 `e` 挪到偏移 1，首成员与对象同地址的保证就被破坏了，所以标准干脆规定这种类不是标准布局。

*M*(X) 是所有可能位于 X 内偏移 0 处的非基类子对象的类型集合（注 1），递归定义如下：

- ¶2.7.1 X 是没有非静态数据成员的非联合体类：*M*(X) 为空；
- ¶2.7.2 X 是非联合体类，其第一个非静态数据成员（或零大小的成员，如 `[[no_unique_address]]` 的空成员）类型为 X₀（可以是匿名联合体）：*M*(X) = {X₀} ∪ *M*(X₀)；
- ¶2.7.3 X 是联合体：*M*(X) 是所有成员类型 Uᵢ 及其 *M*(Uᵢ) 的并，因为联合体的每个成员都在偏移 0；
- ¶2.7.4 X 是数组，元素类型 Xₑ：*M*(X) = {Xₑ} ∪ *M*(Xₑ)，因为数组的第一个元素在偏移 0；
- ¶2.7.5 X 是非类非数组类型：*M*(X) 为空。

由于定义是递归的，`struct S : E { struct { E inner; } wrap; };` 这种隔了一层的情况也会被捕获：`wrap` 的类型在 *M*(S) 中，`E` 在 *M*(wrap 的类型) 中，所以 `E` 也在 *M*(S) 中。

!!! lawyer "零大小成员也算"
    ¶2.7.2 特意写了 "either of zero size or is the first non-static data member"。零大小子对象可以与其他子对象共享地址，所以一个 `[[no_unique_address]]` 的空成员即使不是第一个成员，也可能放在偏移 0，它的类型也要进入 *M*(X)。

### ¶2.3：访问控制相同，一个历史遗留的条件

在 C++23 之前，[[class.mem.general]] 只保证同一访问控制区段内的成员按声明顺序递增分配；不同访问区段（`public:` 与 `private:` 之间）的相对顺序是未指定的，理论上实现可以重排。标准布局要求单一访问控制，就是为了排除这种重排。

C++23 通过 P1847 删除了这项重排许可，现在所有非变体、非零大小的非静态数据成员都按声明顺序分配（[[class.mem.general#24]]）。然而 ¶2.3 仍然保留在标准布局的定义中。改动它会改变 `is_standard_layout` 的结果，从而影响现有代码以及某些 ABI 决策，所以委员会没有动它。

```cpp run title="sl-access.cpp" ok
#include <type_traits>

struct T {          // 平凡可复制，但不是标准布局
    int i;
private:
    int j;
};
static_assert(std::is_trivially_copyable_v<T>);
static_assert(!std::is_standard_layout_v<T>);

struct OK {         // 访问控制相同（都是 private）：标准布局
private:
    int i;
    int j;
public:
    int get() const { return i + j; }   // 成员函数的访问控制无关紧要
};
static_assert(std::is_standard_layout_v<OK>);
int main() { }
```

¶2.3 只看非静态数据成员；成员函数、静态成员、类型成员的访问控制不影响标准布局性。

### 标准布局带来什么保证

标准布局本身只是一个分类，由它带来的保证规定在别处：

1. **首成员地址等于对象地址**（[[class.mem.general#31]]）：标准布局类对象与它的第一个非静态数据成员（非位域）以及它的所有基类子对象**指针可互转换**（pointer-interconvertible，[[basic.compound#7]]），可以用 `reinterpret_cast` 在两者之间转换指针，结果直接指向对方。C 风格的结构体头部继承（定义 `struct Derived { Base base; ... }`，然后把 `Derived*` 当 `Base*` 用）正是以此为依据。
2. **`offsetof`**（[[support.types.layout#1]]）：对标准布局类使用 `offsetof` 保证受支持，对其他类型则是有条件支持（conditionally-supported）的。GCC/Clang 对非标准布局类型使用 `offsetof` 会给出 `-Winvalid-offsetof` 警告。
3. **公共初始序列**（[[class.mem.general#27]]）：两个标准布局 struct 放在联合体中时，可以通过另一个成员读取公共前缀（[[class.mem.general#30]]）。
4. **布局兼容**（layout-compatible，[[class.mem.general#28]]）。
5. **与其他语言互操作**（¶5 注 2）：在 `extern "C"` 接口中传递结构体，依赖的就是标准布局类。

```cpp run title="first-member.cpp" ok
#include <cstddef>

struct Header { int tag; };
struct Packet {            // 标准布局：所有数据成员都在 Packet 中
    Header h;
    char payload[16];
};

static_assert(offsetof(Packet, h) == 0);
static_assert(offsetof(Packet, payload) == sizeof(Header));

int main() {
    Packet p{{7}, {}};
    Header* hp = reinterpret_cast<Header*>(&p);   // OK: p 与 p.h 指针可互转换，hp 指向 p.h
    return hp->tag - 7;
}
```

## 标准布局 struct 与 union（¶3–¶5）

¶3 是标准例 1，上文已改编使用。¶4 规定，用 `struct` 或 `class` 定义的标准布局类称为**标准布局 struct**，用 `union` 定义的称为**标准布局 union**。之所以区分，是因为公共初始序列（[[class.mem.general#27]]）等规则只对 struct 定义，而联合体的布局兼容另有规则（[[class.mem.general#29]]）。

¶5 注 2 指出，标准布局类适合与其他语言编写的代码通信，其布局由 [[class.mem.general]] 和 [[expr.rel]]（成员地址比较）规定。

## 性质的四种组合（¶6）

标准例 2 展示了平凡可复制与标准布局相互独立：

```cpp run title="combinations.cpp" ok
#include <type_traits>

struct N {          // 两者都不是
    int i;
    int j;
    virtual ~N() = default;
};

struct T {          // 平凡可复制，但不是标准布局
    int i;
private:
    int j;
};

struct SL {         // 标准布局，但不是平凡可复制
    int i;
    int j;
    ~SL() { }
};

struct POD {        // 两者都是
    int i;
    int j;
};

static_assert(!std::is_trivially_copyable_v<N>   && !std::is_standard_layout_v<N>);
static_assert( std::is_trivially_copyable_v<T>   && !std::is_standard_layout_v<T>);
static_assert(!std::is_trivially_copyable_v<SL>  &&  std::is_standard_layout_v<SL>);
static_assert( std::is_trivially_copyable_v<POD> &&  std::is_standard_layout_v<POD>);
int main() { }
```

既平凡又是标准布局的类，在 C++98 中大致对应 **POD**（plain old data）。C++11 把 POD 拆成了平凡与标准布局两个正交的概念，因为它们服务于不同目的：前者关乎复制语义，后者关乎内存布局。

¶7 注 3 指出，类类型的聚合在 [[dcl.init.aggr]] 中描述。聚合是第四个常被混淆的类别，它关乎初始化语法，与上面三个性质都无关。

## 隐式生存期类（¶8）

¶8：类 `S` 满足下列条件之一时，是**隐式生存期类**（implicit-lifetime class，[[g:implicit-lifetime-class]]）：

- ¶8.1 它是一个析构函数不是用户提供的聚合；或
- ¶8.2 它至少有一个平凡的合格构造函数，并且有一个平凡的、未弃置的析构函数。

### 为什么需要这个概念

C++20 的 [[P0593R6]] 引入了隐式对象创建（[[intro.object]]）：`malloc`、`operator new`、`memcpy`、`std::bit_cast`、开始 `unsigned char`/`std::byte` 数组的生命周期等操作，只要这样做能让程序具有定义的行为，就会在存储中隐式创建隐式生存期类型的对象。大量 C 风格代码在 C++ 中严格来说是 UB，这一机制修复了这个问题：

```cpp run title="implicit-lifetime.cpp" ok
#include <cstdlib>

struct Point { int x, y; };          // 聚合，析构函数非用户提供 ⇒ 隐式生存期类

int main() {
    auto* p = static_cast<Point*>(std::malloc(sizeof(Point)));
    p->x = 1;                         // C++20 起 OK：malloc 隐式创建了 Point 对象
    p->y = 2;                         // （C++17 中严格说是 UB：没有任何 Point 对象存在）
    int r = p->x + p->y;
    std::free(p);
    return r - 3;
}
```

两条路径背后的逻辑相同：隐式创建意味着不运行任何用户代码就让对象出现。

- **¶8.2**：有一个平凡的合格构造函数（默认、复制或移动均可），说明存在一种不运行任何代码就能产生该类对象的方式；析构函数平凡且未弃置，说明对象也可以不运行任何代码就结束。
- **¶8.1**：聚合可以不调用任何构造函数，通过聚合初始化让成员各自初始化。所以即使成员不平凡，只要析构函数不是用户写的，聚合本身也可以隐式产生。

!!! lawyer "含 `std::string` 的聚合也是隐式生存期类"
    `struct A { std::string s; };` 是聚合，析构函数是隐式声明的（非用户提供），所以按 ¶8.1 它是隐式生存期类，`std::is_implicit_lifetime_v<A>` 为 `true`。但这并不意味着 `malloc` 得到的存储里会自动出现一个可用的 `std::string`。`std::string` 不是隐式生存期类型，隐式创建 `A` 对象时，成员 `s` 的生命周期并不会开始，使用 `s` 仍然是 UB。这个概念只保证外层对象可以隐式出现，内部非隐式生存期的子对象仍需显式构造。

!!! history "¶8.1 中的“析构函数不是用户提供的”"
    P0593R6 最初的定义是“是聚合，或……”，没有对聚合的析构函数加限制。这样一来，一个带有用户提供析构函数（可能负责释放资源）的聚合也能隐式创建，与 ¶8.2 对析构函数的要求不一致。后来一个核心语言 issue 补上了析构函数不是用户提供的这一条件。

```cpp run title="il-classes.cpp" ok
#include <type_traits>
#include <string>

struct Agg  { int x; ~Agg() { } };          // 聚合，但析构函数用户提供 ⇒ 不是
struct P    { P() : x(1) { } int x; };       // 默认构造非平凡，但隐式复制构造平凡、析构平凡 ⇒ 是（¶8.2）
struct NotIL{ NotIL() { } NotIL(const NotIL&) { } int x; };   // 没有平凡构造函数 ⇒ 不是

static_assert(!std::is_implicit_lifetime_v<Agg>);
static_assert( std::is_implicit_lifetime_v<P>);
static_assert(!std::is_implicit_lifetime_v<NotIL>);
int main() { }
```

`P` 这个例子值得留意：它有一个用户提供的默认构造函数，但它的复制构造函数是平凡的。平凡的复制构造函数意味着把另一个 `P` 的字节搬过来就得到一个 `P`，这正是 `memcpy` 隐式创建对象时发生的事。

C++23 进一步提供了 `std::start_lifetime_as<T>`（[[obj.lifetime]]），可以在已有字节上显式开始隐式生存期类型对象的生命周期，并保留字节内容。把网络缓冲区解释为结构体时，这是标准的做法。

## 实现视角

!!! impl "编译器内建"
    `std::is_trivially_copyable`、`std::is_standard_layout`、`std::is_implicit_lifetime` 在 GCC/Clang/MSVC 上都由编译器内建实现（如 Clang 的 `__is_trivially_copyable`、`__is_standard_layout`、`__builtin_is_implicit_lifetime`）。它们依赖函数是否合格、是否用户提供等只有前端知道的信息，无法用纯库代码实现。

!!! impl "标准布局与 Itanium ABI 的 POD for the purpose of layout"
    Itanium ABI 有自己的“用于布局目的的 POD”概念，用来决定派生类能否复用基类的尾部填充。例如 `struct A { int i; char c; }; struct B : A { char d; };`：如果 `A` 是用于布局目的的 POD，`d` 就不能放进 `A` 的尾部填充，因为 C 程序员可能用 `memcpy(&a, ..., sizeof(A))` 覆盖填充；否则可以。这个 ABI 定义基于 C++03 的 POD 定义，与 C++11 的标准布局、平凡可复制并不完全一致，并且为了 ABI 稳定已经冻结。所以，类型是否为标准布局，与派生类会不会复用它的尾部填充，不能简单等同。

## 历史与演进

!!! history "历史与演进"
    - **C++98/03**：只有 POD 一个概念（聚合，没有用户声明的复制赋值和析构，成员都是 POD），它同时承担可以 `memcpy` 与布局像 C 两种保证。
    - **C++11**：拆分为平凡（trivial）、平凡可复制和标准布局；POD 等于平凡加标准布局。非 POD 的类（比如有用户构造函数的类）也可以是标准布局，享有布局保证。
    - **C++17 前后**：核心语言 issue 修正了平凡可复制的定义，要求至少有一个未弃置的复制/移动操作。
    - **C++20**：引入合格的特殊成员函数（[[P0848R3]]），平凡可复制的定义改用合格来表述；引入隐式生存期类（[[P0593R6]]）；POD 及 `std::is_pod` 弃用。
    - **C++23**：类成员布局不再允许按访问区段重排（P1847），但标准布局的 ¶2.3 条件保留。
    - **C++26 草案**：平凡类/平凡类型及 `std::is_trivial` 移入附录 D（[[P3247R2]]）。

## 陷阱

!!! pitfall "以为有默认成员初始化器就不能 `memcpy`"
    `struct S { int x = 0; };` 是平凡可复制的。默认成员初始化器只让默认构造函数变得不平凡，与复制无关。在 C++26 中它也不再是平凡类，但平凡类这个概念已被弃用，这一点无关紧要。

!!! pitfall "以为标准布局就能 `memcpy`"
    标准布局不等于平凡可复制。¶6 的 `SL` 有用户提供的析构函数，它是标准布局，但不能按字节复制。

!!! pitfall "对派生类用 `offsetof`"
    `struct Base { int a; }; struct Derived : Base { int b; };` 不是标准布局（¶2.6），`offsetof(Derived, b)` 是有条件支持的，GCC/Clang 会警告。需要用 `offsetof` 的结构体，应把所有数据成员放在同一个类里。

!!! pitfall "把空基类和同类型首成员放在一起"
    `struct S : Tag { Tag t; ... };` 因 ¶2.7 而不是标准布局，而且 `sizeof` 可能意外变大。

## 思考题

!!! question "思考题 1"
    下面哪些是标准布局类？

    ```cpp
    struct E { };
    struct A : E { int x; };
    struct B : E { A a; };
    struct C : E { [[no_unique_address]] E e2; int y; };
    union  U { E e; int i; };
    struct D : E { U u; };
    ```

<details markdown="1">
<summary>答案</summary>

- `A`：*M*(A) = {int}，基类 `E` 不在其中，且数据成员都在 `A` 中，所以是标准布局。
- `B`：第一个成员 `a` 的类型是 `A`，*M*(B) = {A} ∪ *M*(A) = {A, int}，基类 `E` 不在其中；数据成员只有 `B` 自己的 `a`。按字面规则 `B` 是标准布局，Clang 也报告 `true`。但 `a` 内部有一个 `E` 基类子对象，它如果在偏移 0，就会与 `B` 的 `E` 基类子对象同址，而同类型的不同对象不允许同址。*M*(X) 只沿第一个成员收集非基类子对象，捕获不到这种情况。实测 Clang（Itanium ABI）把 `a` 放在偏移 4，[[class.mem.general#31]] 承诺的首成员与对象同址在这里就落空了。这是标准布局定义的一个边角漏洞，值得留意。
- `C`：`e2` 是零大小成员，按 ¶2.7.2 其类型 `E` ∈ *M*(C)，而 `E` 是 `C` 的基类，所以不是。
- `U`：联合体，没有基类，所有成员都是标准布局，所以是。
- `D`：第一个成员 `u` 的类型是 `U`，*M*(D) = {U} ∪ *M*(U) = {U, E, int}；`E` 是 `D` 的基类，所以不是（¶2.7.3：联合体的每个成员都在偏移 0）。
</details>

!!! question "思考题 2"
    `struct X { X(const X&) = default; X(X&&) = delete; int i; };` 是平凡可复制的吗？如果把 `X(X&&) = delete;` 改成 `X(X&&) { }` 呢？

<details markdown="1">
<summary>答案</summary>

第一种：复制构造函数合格且平凡；移动构造函数是弃置的，不合格，不参与 ¶1.2 的判断。由于用户声明了移动构造函数，复制赋值隐式声明为弃置（[[class.copy.assign#2]]），移动赋值不会隐式声明（[[class.copy.assign#4]]）。析构函数平凡。合格的只有复制构造函数，而它是平凡的，所以 `X` 是平凡可复制的。

第二种：移动构造函数是用户提供的，合格但不平凡，违反 ¶1.2，所以不是。
</details>

!!! question "思考题 3"
    为什么 ¶8.2 只要求至少一个平凡的合格构造函数，而不是要求默认构造函数平凡？

<details markdown="1">
<summary>答案</summary>

隐式对象创建的语义是：如果存在一种创建该对象的方式能使程序具有定义的行为，就认为对象已被创建。它不需要指定用的是哪一个构造函数。只要存在一个平凡构造函数，就说明这种类型的对象可以不执行任何代码而产生（例如 `memcpy` 对应平凡复制构造函数的语义）。如果要求默认构造函数平凡，就会把 `struct P { P() : x(1) {} int x; };` 这类默认构造做了事、复制却只是按位复制的类型排除在外，而这类类型在 `memcpy` 和网络缓冲区的场景中很常见。
</details>

## 小结

| 性质 | 定义要点 | 主要用途 |
|---|---|---|
| 平凡可复制类 | ≥1 个合格复制/移动操作；所有合格的都平凡；析构平凡且未弃置 | `memcpy`、`bit_cast`、`atomic` |
| 标准布局类 | 无虚、无引用成员、单一访问控制、数据成员集中在一层、同类型基类至多一个、基类不与 *M*(S) 冲突 | 首成员同址、`offsetof`、公共初始序列、C 互操作 |
| 标准布局 struct / union | 按 *class-key* 区分 | 公共初始序列只对 struct 定义 |
| 隐式生存期类 | 析构非用户提供的聚合；或有平凡合格构造 + 平凡未弃置析构 | `malloc`/`memcpy` 隐式创建对象、`start_lifetime_as` |
| ~~平凡类~~ | C++26 移入附录 D 弃用 | 改用上面两个 trait 分别判断 |
