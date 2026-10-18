---
title: 类的性质
summary: 平凡可复制类、标准布局类（每一条限制的理由、M(X) 集合、首成员地址与 offsetof）、标准布局 struct/union、隐式生存期类；C++26 中"平凡类"移入附录 D
status: draft
papers: P0848R3, P0593R6, P3247R2
related: basic.types, basic.types.trivial, class.mem, special, intro.object, basic.compound, support.types.layout, depr.meta.types
tags: 平凡可复制, 标准布局, 隐式生存期, memcpy, offsetof
updated: 2026-10-17
---

本节给类类型定义了三个"性质"（properties），它们是语言与**字节层面**打交道的三张通行证：

| 性质 | 一句话 | 买到了什么 | 类型特征 |
|---|---|---|---|
| **平凡可复制**（trivially copyable）| 复制/移动/析构都"什么也不额外做" | 按字节复制 = 按值复制：`memcpy`、`std::bit_cast`、`std::atomic<T>` | `std::is_trivially_copyable` |
| **标准布局**（standard-layout）| 布局像 C 结构体一样可预测 | 首成员与对象同地址、`offsetof`、公共初始序列、与 C 互操作 | `std::is_standard_layout` |
| **隐式生存期**（implicit-lifetime）| 不运行任何代码就能"凭空出现" | `malloc`/`memcpy` 出来的存储可以隐式创建这种对象 | `std::is_implicit_lifetime` |

这三个性质是**相互独立**的（¶6 的例子正好覆盖了各种组合）。在它们之上，[[basic.types.general]] 把标量类型也纳入进来，定义了"平凡可复制**类型**"、"标准布局**类型**"、"隐式生存期**类型**"；本节只管**类**。

!!! note "\"平凡类\"去哪了？"
    C++23 及以前，本节还定义了**平凡类**（trivial class）：平凡可复制，且有一个或多个合格的默认构造函数、全部平凡。C++26 草案 {{c++26}} 把这个概念连同 `std::is_trivial` 一起移入附录 D 弃用（[[depr.meta.types#3]]，[[P3247R2]]）。理由是"平凡"把"可以 `memcpy`"与"默认构造什么都不做"两件不相关的事捆在一起，几乎没有代码真正需要这个组合；需要的人应该分别问 `is_trivially_copyable` 和 `is_trivially_default_constructible`。同理，POD 早在 C++20 就已弃用。

!!! note "平凡可重定位？"
    C++26 周期中一度加入的"平凡可重定位"（trivially relocatable）与"可替换"（replaceable）类性质（[[P2786]]）后来被撤回，**当前草案中不存在**。

## 平凡可复制类（¶1）

¶1：一个类是**平凡可复制类**，当且仅当：

- ¶1.1 它**至少有一个合格的**复制构造函数、移动构造函数、复制赋值运算符或移动赋值运算符；
- ¶1.2 每一个**合格的**复制/移动构造函数和复制/移动赋值运算符都是**平凡的**；
- ¶1.3 它有一个**平凡的、未弃置的**析构函数。

注意这里**完全不涉及默认构造函数**：`struct S { int x = 0; };` 的默认构造不平凡（有默认成员初始化器），但 `S` 是平凡可复制的。

### "平凡"是什么意思

每种特殊成员函数的"平凡"定义在各自的子条款里（[[class.copy.ctor#12]]、[[class.copy.assign#9]]、[[class.dtor#8]]），模式完全一致：

1. **不是用户提供的**（user-provided，[[dcl.fct.def.default#5]]）——隐式声明的，或在首次声明处 `= default` 的；
2. 类**没有虚函数、没有虚基类**（析构函数的版本是"析构函数不是虚的"）；
3. 对每个基类和类类型成员，**被选中**用来做相应操作的函数也是平凡的。

直觉：平凡的复制构造/赋值就是"逐字节复制"，平凡的析构就是"什么都不做"。虚函数和虚基类之所以破坏平凡性，是因为复制时 vptr / 虚基类偏移需要被**设置为目标对象类型的值**，而不是从源对象逐字节复制过来（源可能是更派生类型的基类子对象）。

### 为什么是"合格的"（eligible）

**合格的特殊成员函数**（[[special#6]]）是：未被弃置、约束（若有）得到满足、并且没有同类的、约束更严格且满足的另一个特殊成员函数。这个概念是 C++20 为**条件平凡的特殊成员函数**（[[P0848R3]]）引入的。动机是 `std::optional<T>` 这类包装器：希望当 `T` 平凡可复制时 `optional<T>` 也平凡可复制。在 C++20 之前，这只能靠一层层基类模板特化来实现；C++20 起可以直接写：

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

¶1.2 说的是"每一个**合格的**都是平凡的"——不合格的那个（`Opt<int>` 中的 #2）再不平凡也不影响结论。

### "至少一个"：被删光的类

¶1.1 要求至少有一个合格的复制/移动操作。由于合格要求"未被弃置"，一个**把复制和移动全部 `= delete`** 的类没有任何合格的此类函数，因此**不是**平凡可复制的。这在直觉上是对的：一个刻意禁止复制的类型，`memcpy` 它显然违背作者意图。

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
    截至写作时，Clang 23 对 `NoCopy` 这类"复制移动全部弃置"的类报告 `is_trivially_copyable == true`（其他编译器请自行验证）。这是实现落后于标准的地方（规则来自 C++17 时期的一个核心语言 issue 决议）。写可移植代码时，不要依赖这个边界。

### 平凡可复制有什么用

- **按字节复制保值**：[[basic.types.trivial]] 保证用 `memcpy`/`memmove` 把一个平凡可复制对象的字节复制到另一个同类型对象（或复制出去再复制回来），得到相同的值。
- **`std::bit_cast`** 要求源和目标都是平凡可复制类型（[[bit.cast]]）。
- **`std::atomic<T>`** 要求 `T` 平凡可复制。
- **隐式对象创建**：`memcpy` 到新存储会隐式创建对象（[[intro.object]]），平凡可复制类通常同时是隐式生存期类（有平凡的复制构造函数 + 平凡析构）。
- **ABI**：Itanium ABI 中，类对象能否通过寄存器传参取决于"对调用而言是否平凡"（复制/移动构造与析构），与"平凡可复制"相近但不相同（[[basic.types]] 的实现视角有详述）。

## 标准布局类（¶2）

¶2 给出标准布局类的七条条件。先给直觉：**标准布局类就是"布局可以像 C 结构体一样推断"的类**——非静态数据成员按声明顺序排列，第一个成员在偏移 0 处，没有隐藏的 vptr，没有因为"同类型子对象必须不同地址"而被迫挪位的情况。

类 `S` 是标准布局类，若它：

| 列表项 | 条件 | 为什么 |
|---|---|---|
| ¶2.1 | 没有非标准布局类类型（或其数组）的、或引用类型的非静态数据成员 | 标准布局性要"递归"成立；引用成员没有 C 对应物 |
| ¶2.2 | 没有虚函数、没有虚基类 | vptr / 虚基类指针的位置由实现决定（Itanium 放在偏移 0），会破坏"首成员地址 = 对象地址" |
| ¶2.3 | 所有非静态数据成员的**访问控制相同** | 历史上允许实现按访问区段重排成员（见下） |
| ¶2.4 | 没有非标准布局的基类 | 同 ¶2.1，递归 |
| ¶2.5 | 任何给定类型的基类子对象**至多一个** | 两个同类型的基类子对象必须地址不同，可能迫使空基类无法放在偏移 0 |
| ¶2.6 | 类及其基类中的所有非静态数据成员和位域都**首先声明于同一个类** | 保证"第一个成员"是唯一确定的、位于偏移 0 |
| ¶2.7 | 没有 *M*(S) 中的类型作为基类 | 防止空基类和第一个成员同类型而被迫错开 |

### ¶2.6：成员只能集中在一层

"类及其基类中的所有非静态数据成员和位域首先声明于同一个类"——也就是说，在继承层次里，**最多只有一个类有数据成员**（其余都是空类）。

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

为什么这么严？如果基类和派生类都有数据成员，"对象的第一个非静态数据成员"是哪个就要依赖于实现如何安排基类子对象与派生类成员——在 Itanium ABI 中派生类成员可以**塞进基类的尾部填充**里（只要基类不是 POD-for-layout），这会让 C 视角的布局推断失效。E 的例子说明，即使是**无名位域**（它不是成员，[[class.bit#2]]）也算数——条款原文特意写了"non-static data members **and bit-fields**"。

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

两个 `Q` 子对象是**同类型的不同对象**，必须有不同的地址（[[intro.object]]），所以它们不可能都在偏移 0。标准布局要求"对象的地址等于其**每个**基类子对象的地址"（[[class.mem.general#31]]），这就做不到了。

### ¶2.7 与 *M*(X)：空基类与第一个成员撞类型

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

空基类优化希望把空基类 `E` 放在偏移 0（不占空间），而第一个成员 `e` 也要在偏移 0；但两者是同类型的不同对象，地址必须不同（脚注 81 正是此意）。于是实现只好把 `e` 挪到偏移 1，"首成员与对象同地址"的保证被破坏——所以标准干脆规定这种类不是标准布局。

*M*(X) 就是"所有可能位于 X 内偏移 0 处的**非基类**子对象的类型集合"（注 1），递归定义如下：

- ¶2.7.1 X 是没有非静态数据成员的非联合体类：*M*(X) 为空；
- ¶2.7.2 X 是非联合体类，其第一个非静态数据成员（或零大小的成员，如 `[[no_unique_address]]` 的空成员）类型为 X₀（可以是匿名联合体）：*M*(X) = {X₀} ∪ *M*(X₀)；
- ¶2.7.3 X 是联合体：*M*(X) 是所有成员类型 Uᵢ 及其 *M*(Uᵢ) 的并——联合体的**每个**成员都在偏移 0；
- ¶2.7.4 X 是数组，元素类型 Xₑ：*M*(X) = {Xₑ} ∪ *M*(Xₑ)——数组的第一个元素在偏移 0；
- ¶2.7.5 X 是非类非数组类型：*M*(X) 为空。

因为是递归的，`struct S : E { struct { E inner; } wrap; };` 这种"隔了一层"的情况也会被捕获：`wrap` 的类型在 *M*(S) 中，`E` 在 *M*(wrap 的类型) 中，所以也在 *M*(S) 中。

!!! lawyer "零大小成员也算"
    ¶2.7.2 特意写了"either of zero size or is the first non-static data member"：一个 `[[no_unique_address]]` 的空成员即使不是第一个成员，也可能被放在偏移 0（零大小子对象可以与其他子对象共享地址），所以它的类型也要进入 *M*(X)。

### ¶2.3：访问控制相同——一个"历史遗留"的条件

在 C++23 之前，[[class.mem.general]] 只保证**同一访问控制区段内**的成员按声明顺序递增分配；不同访问区段（`public:` 与 `private:` 之间）的相对顺序是**未指定**的，理论上实现可以重排。标准布局要求单一访问控制，就是为了排除这种重排。

C++23 通过 P1847 删除了这项重排许可：现在**所有**非变体、非零大小的非静态数据成员都按声明顺序分配（[[class.mem.general#24]]）。然而 ¶2.3 这个条件仍然保留在标准布局的定义中——改变它会改变 `is_standard_layout` 的结果，从而影响现有代码（以及某些 ABI 决策），委员会没有动它。

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

注意 ¶2.3 只看**非静态数据成员**；成员函数、静态成员、类型成员的访问控制不影响标准布局性。

### 标准布局买到了什么

标准布局本身只是一个分类，它的"福利"规定在别处：

1. **首成员地址 = 对象地址**（[[class.mem.general#31]]）：标准布局类对象与其第一个非静态数据成员（非位域）、以及其所有基类子对象**指针可互转换**（pointer-interconvertible，[[basic.compound#7]]），可以用 `reinterpret_cast` 在两者之间转换指针，结果直接指向对方。这是 C 风格"结构体头部继承"（`struct Derived { Base base; ... }` 然后把 `Derived*` 当 `Base*` 用）的法律依据。
2. **`offsetof`**（[[support.types.layout#1]]）：对标准布局类使用 `offsetof` 是保证支持的；对其他类型是**有条件支持**（conditionally-supported）的。GCC/Clang 对非标准布局类型使用 `offsetof` 会给出 `-Winvalid-offsetof` 警告。
3. **公共初始序列**（[[class.mem.general#27]]）：两个标准布局 struct 在联合体中可以通过另一个成员读取公共前缀（[[class.mem.general#30]]）。
4. **布局兼容**（layout-compatible，[[class.mem.general#28]]）。
5. **与其他语言互操作**（¶5 注 2）：标准布局类是 `extern "C"` 接口中传递结构体的基础。

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

¶3 是标准例 1（上文已改编）。¶4：用 `struct` 或 `class` 定义的标准布局类称为**标准布局 struct**；用 `union` 定义的称为**标准布局 union**。区分它们是因为公共初始序列（[[class.mem.general#27]]）等规则只对 struct 定义，而联合体的布局兼容有单独的规则（[[class.mem.general#29]]）。

¶5 注 2：标准布局类适合与其他语言编写的代码通信，其布局由 [[class.mem.general]] 和 [[expr.rel]]（成员地址比较）规定。

## 性质的四种组合（¶6）

标准例 2 展示了"平凡可复制"与"标准布局"的独立性：

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

"既平凡又标准布局"在 C++98 中大致对应 **POD**（plain old data）。C++11 把 POD 拆成了"平凡"与"标准布局"两个正交的概念，因为它们服务于不同目的：前者关乎**复制语义**，后者关乎**内存布局**。

¶7 注 3：类类型的**聚合**在 [[dcl.init.aggr]] 中描述——聚合是第四个常被混淆的类别，它关乎**初始化语法**，与上面三个性质都无关。

## 隐式生存期类（¶8）

¶8：类 `S` 是**隐式生存期类**（implicit-lifetime class，[[g:implicit-lifetime-class]]），若：

- ¶8.1 它是一个**析构函数不是用户提供的聚合**；或
- ¶8.2 它**至少有一个平凡的合格构造函数**，并且有一个**平凡的、未弃置的析构函数**。

### 为什么需要这个概念

C++20 的 [[P0593R6]] 引入了**隐式对象创建**（[[intro.object]]）：某些操作（`malloc`、`operator new`、`memcpy`、`std::bit_cast`、开始 `unsigned char`/`std::byte` 数组的生命周期……）会在存储中**隐式创建**隐式生存期类型的对象，只要这样做能让程序有定义的行为。这修复了大量 C 风格代码在 C++ 中"严格说是 UB"的问题：

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

两条路径的逻辑是："隐式创建"意味着**不运行任何用户代码**就让对象出现。

- **¶8.2**：有平凡的合格构造函数（任意一个：默认、复制或移动），说明存在一种"什么代码都不跑"就能产生该类对象的方式；平凡、未弃置的析构函数说明对象可以"什么代码都不跑"就消失。
- **¶8.1**：聚合可以在不调用任何构造函数的情况下被**聚合初始化**，成员各自初始化即可，所以即使它的成员不是平凡的，聚合本身也可以"凭空出现"——只要析构函数不是用户写的。

!!! lawyer "含 `std::string` 的聚合也是隐式生存期类"
    `struct A { std::string s; };` 是聚合，析构函数是隐式声明的（非用户提供），所以按 ¶8.1 它是隐式生存期类，`std::is_implicit_lifetime_v<A>` 为 `true`。但这并不意味着 `malloc` 出来的存储里能凭空出现一个**可用的** `std::string`：隐式创建 `A` 对象时，其成员 `s` 的生命周期并不会开始（`std::string` 不是隐式生存期类型），使用 `s` 仍然是 UB。这个概念只保证"外壳"可以隐式出现，内部非隐式生存期的子对象仍需显式构造。

!!! history "¶8.1 中\"析构函数不是用户提供的\""
    P0593R6 最初的定义是"是聚合，或……"，没有对聚合的析构函数加限制。这导致一个带有用户提供析构函数（可能释放资源）的聚合也能被"隐式创建"，与 ¶8.2 对析构函数的要求不一致。后来通过一个核心语言 issue 补上了"析构函数不是用户提供的"这一条件。

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

`P` 的例子值得体会：它有一个用户提供的默认构造函数，但它的**复制构造函数**是平凡的。平凡复制构造函数意味着"把另一个 `P` 的字节搬过来就得到一个 `P`"——这正是 `memcpy` 隐式创建对象时发生的事。

C++23 进一步提供了 `std::start_lifetime_as<T>`（[[obj.lifetime]]），可以在已有字节上显式开始隐式生存期类型对象的生命周期并**保留字节内容**——这是"把网络缓冲区解释为结构体"的标准做法。

## 实现视角

!!! impl "编译器内建"
    `std::is_trivially_copyable`、`std::is_standard_layout`、`std::is_implicit_lifetime` 在 GCC/Clang/MSVC 上都由编译器内建实现（如 Clang 的 `__is_trivially_copyable`、`__is_standard_layout`、`__builtin_is_implicit_lifetime`），因为它们依赖于"合格"、"用户提供"等只有前端知道的信息，无法用纯库代码实现。

!!! impl "标准布局与 Itanium ABI 的 \"POD for the purpose of layout\""
    Itanium ABI 有自己的"用于布局目的的 POD"概念，用来决定派生类能否复用基类的**尾部填充**。例如 `struct A { int i; char c; }; struct B : A { char d; };`：若 `A` 是"用于布局目的的 POD"，`d` 不能放进 `A` 的尾部填充（因为 C 程序员可能 `memcpy(&a, ..., sizeof(A))` 覆盖填充）；否则可以。这个 ABI 定义基于 C++03 的 POD 定义，与 C++11 的标准布局/平凡可复制**不完全一致**，且为 ABI 稳定性被冻结。所以"类型是否标准布局"与"派生类会不会复用它的尾部填充"不能简单画等号。

## 历史与演进

!!! history "历史与演进"
    - **C++98/03**：只有 **POD** 一个概念（聚合 + 无用户声明的复制赋值和析构 + 成员都是 POD），它同时承担"可 `memcpy`"与"布局像 C"两种保证。
    - **C++11**：拆分为**平凡**（trivial）、**平凡可复制**和**标准布局**；POD = 平凡 + 标准布局。标准布局允许非 POD 的类（比如有用户构造函数的类）也享受布局保证。
    - **C++17 前后**：通过核心语言 issue 修正平凡可复制的定义，要求至少有一个未弃置的复制/移动操作。
    - **C++20**：引入**合格的特殊成员函数**（[[P0848R3]]），平凡可复制改用"合格"表述；引入**隐式生存期类**（[[P0593R6]]）；POD 及 `std::is_pod` 弃用。
    - **C++23**：类成员布局不再允许按访问区段重排（P1847），但标准布局的 ¶2.3 条件保留。
    - **C++26 草案**：平凡类/平凡类型及 `std::is_trivial` 移入附录 D（[[P3247R2]]）。

## 陷阱

!!! pitfall "以为有默认成员初始化器就不能 `memcpy`"
    `struct S { int x = 0; };` 是平凡可复制的。默认成员初始化器只让**默认构造函数**非平凡，与复制无关。（在 C++26 中，它也不是"平凡类"了，但这个概念已被弃用，无关紧要。）

!!! pitfall "以为标准布局就能 `memcpy`"
    标准布局 ≠ 平凡可复制。¶6 的 `SL` 有用户提供的析构函数，是标准布局但不能按字节复制。

!!! pitfall "对派生类用 `offsetof`"
    `struct Base { int a; }; struct Derived : Base { int b; };` 不是标准布局（¶2.6），`offsetof(Derived, b)` 是有条件支持的，GCC/Clang 会警告。要用 `offsetof` 的结构体，把所有数据成员放在同一个类里。

!!! pitfall "把空基类和同类型首成员放一起"
    `struct S : Tag { Tag t; ... };`——¶2.7 使其不是标准布局，而且 `sizeof` 可能出乎意料地变大。

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

- `A`：*M*(A) = {int}；基类 `E` 不在其中，且数据成员都在 `A` 中——**是**。
- `B`：第一个成员 `a` 的类型是 `A`，*M*(B) = {A} ∪ *M*(A) = {A, int}，基类 `E` 不在其中；数据成员只有 `B` 自己的 `a`——按字面规则**是**标准布局，Clang 也报告 `true`。但请注意：`a` 内部有一个 `E` **基类**子对象，它若在偏移 0 就会与 `B` 的 `E` 基类子对象同址（同类型的不同对象，不允许）。*M*(X) 只沿"第一个成员"收集**非基类**子对象，捕获不到这种情况。实测 Clang（Itanium ABI）把 `a` 放在偏移 4，于是 [[class.mem.general#31]] 承诺的"首成员与对象同址"在这里落空——这是标准布局定义的一个边角漏洞，值得留意。
- `C`：`e2` 是零大小成员，按 ¶2.7.2 其类型 `E` ∈ *M*(C)，而 `E` 是 `C` 的基类——**不是**。
- `U`：联合体，没有基类，所有成员都是标准布局——**是**。
- `D`：第一个成员 `u` 的类型是 `U`，*M*(D) = {U} ∪ *M*(U) = {U, E, int}；`E` 是 `D` 的基类——**不是**（¶2.7.3 联合体的每个成员都在偏移 0）。
</details>

!!! question "思考题 2"
    `struct X { X(const X&) = default; X(X&&) = delete; int i; };` 是平凡可复制的吗？如果把 `X(X&&) = delete;` 改成 `X(X&&) { }` 呢？

<details markdown="1">
<summary>答案</summary>

第一种：复制构造函数合格且平凡；移动构造函数被弃置，不合格，不参与 ¶1.2 的判断；用户声明了移动构造函数导致复制赋值与移动赋值……复制赋值被隐式声明为**弃置**（[[class.copy.assign#2]]：有用户声明的移动构造函数），移动赋值不被隐式声明（[[class.copy.assign#4]]）。析构函数平凡。所以合格的只有复制构造函数，它平凡——**是**平凡可复制的。

第二种：移动构造函数是用户提供的，合格但不平凡，违反 ¶1.2——**不是**。
</details>

!!! question "思考题 3"
    为什么 ¶8.2 只要求"**至少一个**"平凡的合格构造函数，而不是要求默认构造函数平凡？

<details markdown="1">
<summary>答案</summary>

隐式对象创建的语义是"如果存在一种创建该对象的方式使程序有定义的行为，就认为对象被创建了"，它不需要指定是**哪一个**构造函数。只要有一个平凡构造函数存在，就说明这种类型的对象可以在不执行任何代码的情况下产生（例如 `memcpy` 对应平凡复制构造函数的语义）。要求默认构造函数平凡会把 `struct P { P() : x(1) {} int x; };` 这类"默认构造做了事，但复制只是按位"的类型排除在外，而这类类型在 `memcpy`/网络缓冲区场景中非常常见。
</details>

## 小结

| 性质 | 定义要点 | 主要用途 |
|---|---|---|
| 平凡可复制类 | ≥1 个合格复制/移动操作；所有合格的都平凡；析构平凡且未弃置 | `memcpy`、`bit_cast`、`atomic` |
| 标准布局类 | 无虚、无引用成员、单一访问控制、数据成员集中在一层、同类型基类至多一个、基类不与 *M*(S) 冲突 | 首成员同址、`offsetof`、公共初始序列、C 互操作 |
| 标准布局 struct / union | 按 *class-key* 区分 | 公共初始序列只对 struct 定义 |
| 隐式生存期类 | 析构非用户提供的聚合；或有平凡合格构造 + 平凡未弃置析构 | `malloc`/`memcpy` 隐式创建对象、`start_lifetime_as` |
| ~~平凡类~~ | C++26 移入附录 D 弃用 | 改用上面两个 trait 分别判断 |
