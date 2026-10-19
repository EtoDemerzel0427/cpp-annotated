---
title: 类的性质
summary: 三个决定能否在字节层面操作对象的类性质：平凡可复制（能否 memcpy）、标准布局（布局是否像 C 结构体一样可预测）、隐式生存期（malloc 出的内存里能否直接使用对象）。
status: draft
papers: P0848R3, P0593R6, P3247R2, P1847R4
related: basic.types, basic.types.trivial, class.mem, special, intro.object, basic.compound, support.types.layout, depr.meta.types
tags: 平凡可复制, 标准布局, 隐式生存期, memcpy, offsetof
updated: 2026-10-19
---

!!! tldr
    - 平凡可复制类可以用 `memcpy`、`std::bit_cast` 按字节复制。条件只涉及复制、移动和析构，与默认构造函数无关。
    - 标准布局类的布局像 C 结构体一样可预测：首成员与对象同地址，`offsetof` 有保证。数据成员必须集中在继承层次的同一个类里，访问控制也要相同。
    - 隐式生存期类的对象可以不运行任何代码就出现，所以 `malloc`、`memcpy` 得到的存储里可以直接使用它。
    - 三个性质相互独立；平凡可复制不等于标准布局。C++26 把平凡类的概念移进了附录 D 并弃用。

## 三个性质各管什么

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

这是标准例 2（¶6）的改编。`N` 有虚析构函数，既不能按字节复制，也有隐藏的虚表指针；`T` 的两个成员访问控制不同；`SL` 有用户写的析构函数。三个性质分别回答三个问题：

| 性质 | 回答的问题 | 类型特征 |
|---|---|---|
| 平凡可复制 | 按字节复制是否等于按值复制 | `std::is_trivially_copyable` |
| 标准布局 | 布局能否像 C 结构体一样推断 | `std::is_standard_layout` |
| 隐式生存期 | 能否不运行任何代码就让对象出现 | `std::is_implicit_lifetime` |

[[basic.types.general]] 在此基础上把标量类型也包括进来，定义了平凡可复制类型、标准布局类型和隐式生存期类型。本节只讨论类。

C++98 的 **POD**（plain old data）同时承担了能 `memcpy` 和布局像 C 两个保证。C++11 把它拆成两个独立的概念，因为前者关乎复制语义，后者关乎内存布局，很多类型只需要其中一个。

## 平凡可复制类（¶1）

一个特殊成员函数如果什么额外的事都不做，就是**平凡的**：平凡的复制构造和复制赋值就是逐字节复制，平凡的析构就是什么也不做。具体条件写在各自的条款里（[[class.copy.ctor#12]]、[[class.copy.assign#9]]、[[class.dtor#8]]），模式相同：

1. 不是用户提供的（[[g:user-provided]]），即隐式声明的，或在第一次声明处就 `= default`；
2. 类没有虚函数和虚基类（析构函数的版本是：析构函数不是虚的）；
3. 每个基类和类类型成员上，选来做同一操作的函数也是平凡的。

虚函数和虚基类会破坏平凡性，是因为复制时虚表指针和虚基类偏移必须设成目标对象类型对应的值。源对象可能是某个更派生对象里的基类子对象，它的这些字节不能照搬。

¶1 一个类是**平凡可复制类**（[[g:trivially-copyable-class|trivially copyable class]]），当且仅当：

- ¶1.1 它至少有一个合格的复制构造函数、移动构造函数、复制赋值运算符或移动赋值运算符；
- ¶1.2 每一个合格的这四种函数都是平凡的；
- ¶1.3 它有平凡的、未弃置的析构函数。

条件里没有默认构造函数。`struct S { int x = 0; };` 的默认构造函数因为默认成员初始化器而不平凡，但 `S` 仍是平凡可复制的。

### 合格：只看真正会被用到的函数

一个特殊成员函数**合格**（[[g:eligible-special-member-function|eligible]]），是指它未被弃置，约束（如果有）得到满足，并且没有另一个同类、同样满足而约束更严的函数（[[special#6]]）。C++20 引入这个概念（[[P0848R3]]），是为了让 `std::optional<T>` 这类包装器在 `T` 平凡可复制时自己也平凡可复制：

```cpp run title="conditionally-trivial.cpp" ok
#include <string>
#include <type_traits>

template<class T>
struct Opt {
    Opt(const Opt&) requires std::is_trivially_copy_constructible_v<T> = default;  // #1
    Opt(const Opt&) { /* 手工复制 */ }                                               // #2
    T t;
};

// Opt<int>：#1 满足约束，比无约束的 #2 更受约束，只有 #1 合格，它是平凡的
static_assert(std::is_trivially_copyable_v<Opt<int>>);
// Opt<std::string>：#1 不满足约束，只有 #2 合格，它是用户提供的
static_assert(!std::is_trivially_copyable_v<Opt<std::string>>);

int main() { }
```

¶1.2 只要求合格的函数平凡。`Opt<int>` 里的 #2 不平凡，但它不合格，不影响结论。C++20 之前要达到同样效果，只能写一层层基类模板的特化。

### 复制和移动全部弃置的类

¶1.1 要求至少有一个合格的复制或移动操作，而弃置的函数不合格。所以把复制和移动全部 `= delete` 的类不是平凡可复制的：作者刻意禁止复制的类型，不应该能用 `memcpy` 复制。

```cpp run title="all-deleted.cpp" ok
#include <type_traits>
#include <cstdio>

struct NoCopy {
    NoCopy() = default;
    NoCopy(const NoCopy&) = delete;
    NoCopy& operator=(const NoCopy&) = delete;
};   // 移动操作不会被隐式声明

struct MoveOnly {
    MoveOnly() = default;
    MoveOnly(MoveOnly&&) = default;             // 平凡且合格
    MoveOnly& operator=(MoveOnly&&) = default;  // 平凡且合格
};   // 复制操作被定义为弃置，不合格，不影响结论

static_assert(std::is_trivially_copyable_v<MoveOnly>);

int main() {
    // 按标准应为 0（¶1.1），Clang 23 输出 1
    std::printf("%d\n", std::is_trivially_copyable_v<NoCopy>);
}
```

!!! warning "Clang 与标准不一致"
    Clang 23 对复制、移动全部弃置的类报告 `is_trivially_copyable` 为 `true`。至少一个未弃置操作的要求来自 [[CWG1734]]，Clang 没有实现这项决议。写可移植代码时不要依赖这个边界。

### 平凡可复制能用来做什么

- 用 `memcpy`、`memmove` 把对象的字节复制到另一个同类型对象，或者复制出去再复制回来，得到的值相同（[[basic.types.trivial]]）。
- `std::bit_cast` 要求源和目标都是平凡可复制类型（[[bit.cast]]），`std::atomic<T>` 要求 `T` 平凡可复制。
- 平凡可复制类通常也是隐式生存期类（它有平凡的复制构造函数和平凡的析构函数），所以 `memcpy` 到新存储会隐式创建对象（[[intro.object]]）。

在 Itanium ABI 中，对象能否放进寄存器传参，看的是它对调用而言是否平凡（复制构造、移动构造、析构），与平凡可复制相近但不相同，见 [[basic.types]] 的实现视角。

## 标准布局类（¶2）

```cpp run title="first-member.cpp" ok
#include <cstddef>

struct Header { int tag; };
struct Packet {            // 标准布局：所有数据成员都在 Packet 里
    Header h;
    char payload[16];
};

static_assert(offsetof(Packet, h) == 0);
static_assert(offsetof(Packet, payload) == sizeof(Header));

int main() {
    Packet p{{7}, {}};
    Header* hp = reinterpret_cast<Header*>(&p);   // OK：hp 指向 p.h
    return hp->tag - 7;
}
```

直观地说，**标准布局类**（[[g:standard-layout-class|standard-layout class]]）就是布局能像 C 结构体一样推断的类：数据成员按声明顺序排列，第一个成员在偏移 0，没有隐藏的虚表指针，也不会因为同类型子对象必须地址不同而被迫挪位。

¶2 类 `S` 满足下面全部条件时是标准布局类：

| 列表项 | 条件 | 理由 |
|---|---|---|
| ¶2.1 | 没有非标准布局类类型（或其数组）的、或引用类型的非静态数据成员 | 标准布局要递归成立；C 里没有引用成员 |
| ¶2.2 | 没有虚函数和虚基类 | 虚表指针、虚基类指针的位置由实现决定（Itanium 放在偏移 0） |
| ¶2.3 | 所有非静态数据成员的访问控制相同 | 历史原因，见下文 |
| ¶2.4 | 没有非标准布局的基类 | 递归 |
| ¶2.5 | 同一类型的基类子对象至多一个 | 两个同类型子对象地址必须不同，不能都在偏移 0 |
| ¶2.6 | 类及其基类中的所有非静态数据成员和位域，都首先声明于同一个类 | 第一个成员唯一确定，并位于偏移 0 |
| ¶2.7 | 没有集合 *M*(S) 中的类型作为基类 | 防止空基类和第一个成员同类型而被迫错开 |

### 数据成员只能集中在一层（¶2.6）

```cpp run title="sl-hierarchy.cpp" ok
#include <type_traits>

struct B { int i; };              // 标准布局
struct C : B { };                 // 标准布局：数据成员都在 B
struct D : C { };                 // 标准布局
struct E : D { char : 4; };       // 不是：E 有位域，而 i 声明在 B

struct Base { int a; };
struct Derived : Base { int b; }; // 不是：a 在 Base，b 在 Derived

static_assert(std::is_standard_layout_v<D>);
static_assert(!std::is_standard_layout_v<E>);
static_assert(!std::is_standard_layout_v<Derived>);
int main() { }
```

继承层次里最多只能有一个类有数据成员，其余都是空类。基类和派生类都有数据成员时，哪个成员在最前面取决于实现怎样安排基类子对象；Itanium ABI 还可能把派生类成员塞进基类的尾部填充。`E` 说明无名位域也算在内：它不是成员（[[class.bit#2]]），所以条文特意写了 "and bit-fields"。前四行是标准例 1（¶3）。

### 同类型的基类至多一个（¶2.5）

```cpp run title="sl-dup-base.cpp" ok
#include <type_traits>

struct Q { };
struct S : Q { };
struct T : Q { };
struct U : S, T { };          // U 里有两个 Q 子对象

static_assert(!std::is_standard_layout_v<U>);
int main() { }
```

两个 `Q` 子对象是同类型的不同对象，地址必须不同（[[intro.object]]），不可能都在偏移 0。而标准布局类要求对象地址等于每个基类子对象的地址（[[class.mem.general#31]]），做不到。

### 空基类与第一个成员同类型（¶2.7）

```cpp run title="sl-mx.cpp" ok
#include <type_traits>
#include <cstdio>

struct E { };
struct S1 : E { E e; int x; };   // 基类 E 与第一个成员 e 同类型
struct S2 : E { int x; E e; };   // 第一个成员是 int

static_assert(!std::is_standard_layout_v<S1>);
static_assert(std::is_standard_layout_v<S2>);

int main() {
    S1 s;
    std::printf("%td\n", reinterpret_cast<char*>(&s.e) - reinterpret_cast<char*>(&s));
}
```

空基类优化希望把空基类 `E` 放在偏移 0，第一个成员 `e` 也想在偏移 0。两者是同类型的不同对象，地址必须不同（脚注 81 说的就是这一点），实现只好把 `e` 挪到偏移 1，本机输出 `1`。首成员与对象同地址的保证因此落空，所以标准规定 `S1` 不是标准布局。

注 1 说明，*M*(X) 是 X 里所有可能位于偏移 0 的非基类子对象的类型集合。它递归定义：

- ¶2.7.1 X 是没有非静态数据成员的非联合体类：*M*(X) 为空；
- ¶2.7.2 X 是非联合体类，有一个类型为 X₀ 的非静态数据成员，它要么是第一个非静态数据成员（可以是匿名联合体），要么大小为零：*M*(X) 由 X₀ 和 *M*(X₀) 的元素组成；
- ¶2.7.3 X 是联合体：*M*(X) 是所有成员类型 Uᵢ 及所有 *M*(Uᵢ) 的并，因为联合体的每个成员都在偏移 0；
- ¶2.7.4 X 是元素类型为 Xₑ 的数组：*M*(X) 由 Xₑ 和 *M*(Xₑ) 的元素组成；
- ¶2.7.5 X 不是类也不是数组：*M*(X) 为空。

因为定义是递归的，隔了一层的情况也能捕获：`struct S : E { struct { E inner; } w; };` 里 `w` 的类型在 *M*(S) 中，`E` 又在 `w` 的类型的 *M* 中，所以 `S` 不是标准布局。¶2.7.2 把大小为零的成员也算进去，是因为 `[[no_unique_address]]` 的空成员即使不是第一个成员，也可能被放在偏移 0。

### 访问控制相同（¶2.3）

```cpp run title="sl-access.cpp" ok
#include <type_traits>

struct OK {         // 数据成员都是 private：标准布局
private:
    int i;
    int j;
public:
    int get() const { return i + j; }   // 成员函数的访问控制无关
};
static_assert(std::is_standard_layout_v<OK>);
int main() { }
```

¶2.3 只看非静态数据成员。C++23 之前，不同访问区段（`public:` 与 `private:` 之间）的成员相对顺序是未指定的，实现理论上可以重排，这一条就是为了排除重排。C++23 删掉了重排许可（[[P1847R4]]），现在非零大小的非变体成员都按声明顺序分配（[[class.mem.general#24]]）。但 ¶2.3 保留了下来，因为改动它会改变现有代码里 `is_standard_layout` 的结果。

### 标准布局带来的保证

标准布局本身只是一个分类，保证写在别处：

1. 对象与它的第一个非静态数据成员（不是位域时）以及所有基类子对象**指针可互转换**（[[g:pointer-interconvertible]]，[[class.mem.general#31]]、[[basic.compound#7]]）：用 `reinterpret_cast` 在两者间转换指针，结果直接指向对方。C 风格的头部继承（`struct Derived { Base base; ... }`，把 `Derived*` 当 `Base*` 用）就依赖这一点。
2. `offsetof` 对标准布局类保证可用，对其他类是有条件支持的（[[support.types.layout#1]]）。GCC 和 Clang 对非标准布局类型用 `offsetof` 会给出 `-Winvalid-offsetof` 警告。
3. 两个标准布局 struct 有公共初始序列（[[class.mem.general#27]]）。它们放在同一个联合体里时，可以通过非活跃成员读取公共前缀（[[class.mem.general#30]]）。
4. 布局兼容（[[class.mem.general#28]]）。
5. ¶5 的注指出，标准布局类适合与其他语言编写的代码通信，比如在 `extern "C"` 接口里传递结构体。

¶4 用 `struct` 或 `class` 定义的标准布局类叫**标准布局 struct**，用 `union` 定义的叫**标准布局 union**。公共初始序列只对 struct 定义，联合体的布局兼容另有规则（[[class.mem.general#29]]），所以要区分。

## 隐式生存期类（¶8）

```cpp run title="implicit-lifetime.cpp" ok
#include <cstdlib>

struct Point { int x, y; };          // 隐式生存期类

int main() {
    auto* p = static_cast<Point*>(std::malloc(sizeof(Point)));
    p->x = 1;                         // C++20 起 OK：malloc 隐式创建了 Point 对象
    p->y = 2;
    int r = p->x + p->y;
    std::free(p);
    return r - 3;
}
```

在 C++17 中，这段代码严格说是 UB：`malloc` 只分配存储，没有任何 `Point` 对象存在。C++20 引入了**隐式对象创建**（[[P0593R6]]，[[intro.object]]）：`malloc`、`operator new`、`memcpy`、开始一个 `unsigned char` 或 `std::byte` 数组的生存期等操作，只要这样做能让程序有定义的行为，就会在存储里隐式创建隐式生存期类型的对象。

¶8 类 `S` 满足下列条件之一时，是**隐式生存期类**（[[g:implicit-lifetime-class|implicit-lifetime class]]）：

- ¶8.1 它是聚合，并且析构函数不是用户提供的；或
- ¶8.2 它至少有一个平凡的合格构造函数，并且有平凡的、未弃置的析构函数。

两条路径的意思相同：对象可以不运行任何用户代码就出现。¶8.2 里有一个平凡构造函数（默认、复制、移动都可以），说明存在不执行代码就产生对象的方式；析构函数平凡，说明对象也可以不执行代码就结束。¶8.1 的聚合可以不调用构造函数，通过聚合初始化让成员各自初始化，所以即使成员不平凡，只要析构函数不是用户写的，聚合本身也可以隐式出现。¶8.1 关于析构函数的限制是 C++20 之后由一项核心语言 issue 补上的。

```cpp run title="il-classes.cpp" ok
#include <type_traits>

struct Agg   { int x; ~Agg() { } };                   // 聚合，但析构函数用户提供：不是
struct P     { P() : x(1) { } int x; };               // 复制构造平凡、析构平凡：是（¶8.2）
struct NotIL { NotIL() { } NotIL(const NotIL&) { } int x; };   // 没有平凡构造函数：不是

static_assert(!std::is_implicit_lifetime_v<Agg>);
static_assert( std::is_implicit_lifetime_v<P>);
static_assert(!std::is_implicit_lifetime_v<NotIL>);
int main() { }
```

`P` 有用户提供的默认构造函数，但复制构造函数是平凡的：把另一个 `P` 的字节搬过来就得到一个 `P`，这正是 `memcpy` 隐式创建对象时发生的事。

!!! lawyer "含 `std::string` 的聚合也是隐式生存期类"
    `struct A { std::string s; };` 是聚合，析构函数是隐式声明的，按 ¶8.1 它是隐式生存期类。但这不意味着 `malloc` 出的存储里会自动有一个可用的 `std::string`。`std::string` 不是隐式生存期类型，隐式创建 `A` 时，成员 `s` 的生存期不会开始，使用它仍是 UB。隐式生存期只保证外层对象可以隐式出现。

C++23 还提供了 `std::start_lifetime_as<T>`（[[obj.lifetime]]），在已有字节上显式开始一个隐式生存期类型对象的生存期并保留字节内容。把网络缓冲区解释为结构体时应当用它。

<details class="fine" markdown="1"><summary>其余条文</summary>

¶7 是注：类类型的聚合在 [[dcl.init.aggr]] 中描述。聚合关乎初始化语法，与本节三个性质都不同。

</details>

## 实现视角

!!! impl "类型特征由编译器内建实现"
    `std::is_trivially_copyable`、`std::is_standard_layout`、`std::is_implicit_lifetime` 在 GCC、Clang、MSVC 上都由编译器内建实现（如 Clang 的 `__is_trivially_copyable`、`__is_standard_layout`、`__builtin_is_implicit_lifetime`）。它们依赖函数是否合格、是否用户提供这些只有前端知道的信息，纯库代码写不出来。

!!! impl "Itanium ABI 的用于布局的 POD"
    Itanium ABI 有自己的 POD for the purpose of layout 概念，用来决定派生类能否复用基类的尾部填充。例如 `struct A { int i; char c; }; struct B : A { char d; };`：如果 `A` 是用于布局的 POD，`d` 就不能放进 `A` 的尾部填充，因为 C 程序员可能用 `memcpy(&a, ..., sizeof(A))` 覆盖填充。这个定义基于 C++03 的 POD，为了 ABI 稳定已经冻结，与标准布局并不一致。类型是否为标准布局，与派生类会不会复用它的尾部填充，不能等同。

## 历史与演进

!!! history
    - C++98/03 只有 POD 一个概念，同时承担能 `memcpy` 和布局像 C 两种保证。
    - C++11 拆分为平凡、平凡可复制和标准布局，POD 等于平凡加标准布局。有用户构造函数的类也可以是标准布局。
    - [[CWG1734]] 修改了平凡可复制的定义，要求至少有一个未弃置的复制或移动操作。
    - C++20 引入合格的特殊成员函数（[[P0848R3]]）和隐式生存期类（[[P0593R6]]），弃用 POD 和 `std::is_pod`。
    - C++23 不再允许按访问区段重排成员（[[P1847R4]]），¶2.3 仍然保留。
    - C++26 把平凡类、平凡类型和 `std::is_trivial` 移入附录 D 并弃用（[[P3247R2]]，[[depr.meta.types#3]]）。平凡类要求平凡可复制并且默认构造函数平凡，把两件不相关的事捆在一起；需要的话，分别查 `is_trivially_copyable` 和 `is_trivially_default_constructible`。

## 常见误解

!!! pitfall "有默认成员初始化器就不能 `memcpy`"
    `struct S { int x = 0; };` 是平凡可复制的。默认成员初始化器只让默认构造函数不平凡，与复制无关。

!!! pitfall "标准布局就能 `memcpy`"
    标准布局不等于平凡可复制。`SL` 有用户提供的析构函数，它是标准布局，但不能按字节复制。

!!! pitfall "对派生类用 `offsetof`"
    `struct Derived : Base { int b; };`（`Base` 有数据成员）不是标准布局，`offsetof(Derived, b)` 是有条件支持的，GCC 和 Clang 会警告。需要 `offsetof` 的结构体，应当把所有数据成员放在同一个类里。

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

- `A`：*M*(A) = {int}，基类 `E` 不在其中，数据成员都在 `A` 里，是标准布局。
- `B`：*M*(B) = {A} ∪ *M*(A) = {A, int}，基类 `E` 不在其中，数据成员只有 `B` 自己的 `a`。按字面规则 `B` 是标准布局，Clang 也报告 `true`。但 `a` 里面有一个 `E` 基类子对象，`a` 如果在偏移 0，它就和 `B` 的 `E` 基类子对象同址，而同类型的不同对象不能同址。*M*(X) 只收集非基类子对象，捕获不到这种情况。本机 Clang 把 `a` 放在偏移 4，[[class.mem.general#31]] 承诺的首成员与对象同址在这里落空。这是定义的一个漏洞。
- `C`：`e2` 大小为零，按 ¶2.7.2 `E` ∈ *M*(C)，而 `E` 是 `C` 的基类，不是标准布局。
- `U`：联合体，没有基类，成员都是标准布局，是。
- `D`：*M*(D) = {U} ∪ *M*(U) = {U, E, int}，`E` 是 `D` 的基类，不是。
</details>

!!! question "思考题 2"
    `struct X { X(const X&) = default; X(X&&) = delete; int i; };` 是平凡可复制的吗？把 `X(X&&) = delete;` 改成 `X(X&&) { }` 呢？

<details markdown="1">
<summary>答案</summary>

第一种是。复制构造函数合格且平凡；移动构造函数弃置，不合格。因为用户声明了移动构造函数，复制赋值被隐式声明为弃置（[[class.copy.assign#2]]），移动赋值不会被隐式声明（[[class.copy.assign#4]]）。析构函数平凡。合格的只有复制构造函数，它是平凡的。

第二种不是。移动构造函数是用户提供的，合格但不平凡，违反 ¶1.2。
</details>

!!! question "思考题 3"
    ¶8.2 为什么只要求至少一个平凡的合格构造函数，而不要求默认构造函数平凡？

<details markdown="1">
<summary>答案</summary>

隐式对象创建只要求存在一种能让程序有定义行为的创建方式，不指定用哪个构造函数。只要有一个平凡构造函数，这种类型的对象就可以不执行代码而产生，例如 `memcpy` 对应平凡复制构造的语义。如果要求默认构造函数平凡，就会把 `struct P { P() : x(1) {} int x; };` 这类默认构造做了事、复制却只是按位复制的类型排除在外，而它们在 `memcpy` 和网络缓冲区的场景里很常见。
</details>
