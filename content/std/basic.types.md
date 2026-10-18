---
title: 类型
summary: 6.9 总览与 [basic.types.general]：对象/函数/引用/void 的划分、不完整类型、对象表示与值表示、标量/平凡可复制/标准布局/隐式生存期/字面量类型、布局兼容
status: draft
covers: basic.types.general
papers: P0593R6, P2448R2, P2674R1, P3247R2, P2996R13
related: basic.types.trivial, basic.fundamental, basic.compound, basic.type.qualifier, conv.rank, class.prop, intro.object, basic.lval
tags: 类型系统, 对象模型
updated: 2026-10-17
---

C++ 的每一个对象、引用、函数都有**类型**（type）。[[basic.types]] 这一节（6.9）并不讲怎样声明一个类型，那是 [[dcl]]、[[class]] 的事。它回答的是更底层的问题：一共有哪几类类型？一个类型的对象在内存里占多少字节，哪些位有意义？哪些类型可以按字节复制，可以凭空出现在 `malloc` 来的内存里，可以在常量表达式里创建？后面几乎每一章，包括值类别与别名规则 [[basic.lval]]、生存期 [[basic.life]]、转换 [[conv]]、`constexpr` [[expr.const]]、`<type_traits>`，都要用到本节定义的术语。

6.9 共七个子条款：

| 条款 | 本站页面 | 内容 |
|---|---|---|
| 6.9.1 [[basic.types.general]] | 本页 | 对象类型、不完整类型、对象表示/值表示、类型大类（标量、平凡可复制……）、字面量类型、布局兼容 |
| 6.9.2 [[basic.types.trivial]] | 平凡可复制类型 | 值与值表示的对应关系，`memcpy` 保证 |
| 6.9.3 [[basic.fundamental]] | 基础类型 | 整数、字符、`bool`、浮点、`void`、`nullptr_t`、`std::meta::info` |
| 6.9.4 [[basic.extended.fp]] | 并入基础类型页 | `std::float16_t` 等可选扩展浮点类型 |
| 6.9.5 [[basic.compound]] | 复合类型 | 数组、函数、指针（指针值的四种状态）、引用、类、枚举、成员指针、指针可互转 |
| 6.9.6 [[basic.type.qualifier]] | cv 限定符 | const/volatile 对象、数组的 cv、顶层 cv、更多 cv 限定 |
| 6.9.7 [[conv.rank]] | 转换等级 | 整数转换等级、浮点转换等级与子等级 |

## 类型全景

先给一张地图，后文逐段解释每个名词。第一层划分是基础类型与复合类型（¶1 的注）；第二层是 `<type_traits>` 的 14+1 个主类型类别（primary type categories，[[meta.unary.cat]]），任何类型恰好属于其中一个：

```text
类型
├── 基础类型 fundamental                    is_fundamental
│   ├── 算术类型 arithmetic                  is_arithmetic
│   │   ├── 整型 integral                    is_integral
│   │   │   ├── bool
│   │   │   ├── 字符类型 char wchar_t char8_t char16_t char32_t
│   │   │   ├── 有符号整数类型 signed char short int long long long (+扩展)
│   │   │   └── 无符号整数类型 unsigned char ... unsigned long long (+扩展)
│   │   └── 浮点类型 float double long double (+扩展浮点)   is_floating_point
│   ├── cv void                              is_void
│   ├── std::nullptr_t                       is_null_pointer
│   └── std::meta::info  (C++26)             is_reflection
└── 复合类型 compound                        is_compound
    ├── 数组（已知边界 / 未知边界）           is_array
    ├── 函数                                 is_function
    ├── 指针（对象指针、函数指针）            is_pointer
    ├── 引用（左值 / 右值）                   is_lvalue_reference / is_rvalue_reference
    ├── 类（非联合）                          is_class
    ├── 联合                                 is_union
    ├── 枚举（有作用域 / 无作用域）           is_enum
    └── 成员指针（数据成员 / 成员函数）       is_member_object_pointer / is_member_function_pointer
```

本节 ¶6–¶9 定义的一组性质类别与这棵树正交，横切上面的各个分支：

| 类别 | 定义要点 | trait | 用途 |
|---|---|---|---|
| 对象类型 object type | 不是函数、不是引用、不是 cv `void` | `is_object` | 能有对象的类型 |
| 标量类型 scalar | 算术、枚举、指针、成员指针、`nullptr_t`、`std::meta::info` 及其 cv 版本 | `is_scalar` | 构成其他类别的基本单元 |
| 平凡可复制 trivially copyable | 标量、平凡可复制类、它们的数组及 cv 版本 | `is_trivially_copyable` | `memcpy`/`bit_cast` 保留值 |
| 标准布局 standard-layout | 标量、标准布局类、它们的数组及 cv 版本 | `is_standard_layout` | 与 C 互通、`offsetof`、首成员同址 |
| 隐式生存期 implicit-lifetime | 标量、隐式生存期类、任意数组类型及 cv 版本 | `is_implicit_lifetime` | `malloc`/`memcpy` 等可隐式创建对象 |
| 字面量类型 literal | cv `void`、标量、引用、字面量数组、满足条件的类 | （`is_literal_type` 已于 C++20 移除） | 能在常量求值中创建对象 |
| 布局兼容 layout-compatible | 二元关系：同类型 / 布局兼容的枚举 / 布局兼容的标准布局类 | `is_layout_compatible` | 共同初始序列、指针表示 |
| 不完整类型 incomplete | 未定义的类、某些上下文中的枚举、未知边界数组、元素不完整的数组、cv `void` | （无；对不完整类型用 trait 多为 UB） | 限制 `sizeof`、定义对象等 |

!!! note "trait 与 cv"
    [[meta.unary.cat#2]] 规定主类别 trait 对 `T` 与 `cv T` 的结果相同，[[meta.unary.comp]] 的复合类别也一样。所以 `is_integral_v<const int>` 为真，这与 [[basic.fundamental]] ¶11 中整型包括 cv 版本的定义一致。

## 类型描述什么（¶1）

¶1 是一个注，说了三件事：本节和各子条款对实现提出类型表示上的要求；类型分为基础类型（[[basic.fundamental]]）和复合类型（[[basic.compound]]）两种；类型描述对象、引用或函数。

最后一句值得强调：**引用和函数不是对象**（[[intro.object]]），但它们有类型。所以后面必须专门定义对象类型（¶6），因为许多规则（`sizeof`、`new`、数组元素、`alignof`）只对对象类型有意义。

## 对象表示与值表示（¶2）

¶2 引入了一对贯穿全书的概念：

- **对象表示**（object representation）：类型 `T` 的一个非位域完整对象所占据的 `N` 个 `unsigned char` 对象的序列，`N == sizeof(T)`。
- **值表示**（value representation）：对象表示中参与表示 `T` 的值的那些位的集合。
- **填充位**（padding bits）：在对象表示中、但不属于值表示的位。

!!! std
    "Bits in the object representation of a type or object that are not part of the value representation are *padding bits*."
    —— 对象表示里不参与表示值的位就是填充位。

注意定义是分层的：先定义类型的对象表示和值表示，再说一个非位域完整对象的对象表示（值表示）就是该对象中对应于其类型的对象表示（值表示）的那些字节和位。位域对象另算：它的对象表示是它占据的 `N` 个位（`N` 是位域宽度，[[class.bit]]），值表示是其中参与表示值的位。

为什么要区分两者？因为同一个值可以有多个对象表示，这决定了很多操作是否有意义：

1. 结构体里的填充字节。`struct P { char c; int i; };` 在常见 ABI 上 `sizeof(P) == 8`，`c` 后面有 3 个填充字节。两个相等的 `P` 对象，字节可以不同，所以不能用 `memcmp` 比较，也不能对字节做哈希。
2. 标量里的填充位。例如 x87 的 80 位 `long double` 在 x86-64 System V 上 `sizeof` 为 16，有 48 位填充；`bool` 的对象表示通常是 8 位，但值只有两个（见 [[basic.fundamental#10]]）。
3. 多个表示对应同一个值，或一个值对应多个表示。IEEE 浮点的 NaN 有大量位模式，这正是 `has_unique_object_representations_v<float>` 为假的原因。

标准库用 `std::has_unique_object_representations`（[[meta.unary.prop]]）回答这个类型的每个值是否恰好对应一种对象表示。只有它为真时，按字节哈希或比较才是安全的。

```cpp run ok
#include <type_traits>

struct P { char c; int i; };   // c 之后通常有 3 字节填充
struct Q { int a; int b; };    // 常见 ABI 上没有填充

static_assert(!std::has_unique_object_representations_v<P>);
static_assert( std::has_unique_object_representations_v<Q>);   // 实现定义，主流 ABI 上为真
static_assert( std::has_unique_object_representations_v<int>); // C++20 起整数无陷阱表示、补码
static_assert(!std::has_unique_object_representations_v<float>);

int main() {}
```

`std::bit_cast` 也受值表示约束。在常量求值中，如果结果里某个字节来自源对象的填充位，结果就是不确定的，因而不能成为常量表达式（[[bit.cast]]）：

```cpp run error
#include <bit>

struct P  { char c; int i; };
struct B8 { unsigned char b[8]; };

constexpr P  p{1, 2};
constexpr B8 bytes = std::bit_cast<B8>(p);   // error: b[1..3] 来自填充，值不确定
```

!!! impl "实现视角"
    值表示这个概念是编译器优化的依据。填充位不承载值，所以编译器复制结构体时可以不复制填充（例如逐成员复制，或用更宽的寄存器），也可以在填充里留下任意垃圾。因此把结构体按字节写入文件或网络，可能泄露内存中的旧数据；安全敏感的代码常先对整个结构体 `memset`，再填写成员。

## 不完整类型（¶3–¶5）

¶3 先定义**不完全定义的对象类型**（incompletely-defined object type），共三种：

1. 已声明但未定义的类；
2. 某些上下文中的枚举类型（见下文）；
3. 未知边界的数组，或元素类型不完整的数组。

不完全定义的对象类型加上 cv `void`，合称**不完整类型**（incomplete types）。脚注说明了实质：不完整类型的实例大小和布局未知。凡是需要知道大小或布局的操作，如定义对象、`sizeof`、`new`、指针算术、访问成员、作为基类、作为非静态数据成员，都要求完整类型。哪些上下文禁止不完整类型，由各条声明和表达式规则分别规定（¶5 的注），本节只给出概念。

!!! note "枚举什么时候不完整"
    按 [[dcl.enum#6]]，底层类型固定的枚举在其 *enum-base* 之后立即变得完整，所以在 `enum class E : int;` 这种不透明声明之后 `E` 就已完整，可以用 `sizeof(E)`。底层类型不固定的枚举直到其 `enum-specifier` 的右花括号 `}` 才完整，因为在那之前编译器还不知道所有枚举值，无法选定底层类型。

### 完整化：同一个类型 vs 不同类型（¶4）

¶4 区分了两种后来变完整的情况，这一点很容易混淆：

- 类：`class X;` 时不完整，`class X { ... };` 之后完整，**前后是同一个类型**。因元素类型不完整而不完整的数组（`X` 还未定义时的 `X arr[3]`）也随 `X` 的完成而完整，前后也是同一个类型。
- 未知边界数组：`extern int arr[];` 的类型是 `int` 的未知边界数组。之后用 `int arr[10];` 重新声明，此时 `arr` 的类型变为 10 个 `int` 的数组，**这是两个不同的类型**。被完整化的是对象的声明类型，而不是那个类型本身。

由此得到注 3：指向未知边界数组的指针或引用永远指向不完整类型；用 typedef 命名的未知边界数组也永远不完整，类型 `int[]` 本身是无法完成的。

改编自标准 Example 1：

```cpp run error
class X;                 // X 是不完整类型
extern X* xp;            // 指向不完整类型的指针：OK
extern int arr[];        // arr 的类型不完整
typedef int UNKA[];      // UNKA 是不完整类型
UNKA* arrp;              // 指向不完整类型的指针
UNKA** arrpp;

void foo() {
  xp++;                  // error: X 不完整，不知道步长
  arrp++;                // error: 不完整类型
  arrpp++;               // OK: sizeof(UNKA*) 已知
}

struct X { int i; };     // 现在 X 完整了
int arr[10];             // 现在 arr 的（声明）类型完整了

X x;
void bar() {
  xp = &x;               // OK: 类型是 "pointer to X"
  arrp = &arr;           // OK: int(*)[10] → int(*)[]，限定转换 [conv.qual]
  xp++;                  // OK: X 已完整
  arrp++;                // error: UNKA 永远无法完成
}
```

注意 `arrp = &arr;`：从 `int(*)[10]` 到 `int(*)[]` 的转换在 C++20 之前是不允许的，现在作为限定转换的一部分（[[conv.qual]]）得到允许。

### 完整与否取决于程序点

类在何处完整，[[class.mem.general#11]] 给出了精确定义：在程序点 P，如果 C 的定义从 P 可达，或者 P 位于 C 的**完整类上下文**（complete-class context，[[class.mem.general#10]]：函数体、默认实参、默认模板实参、*noexcept-specifier*、函数契约说明符 {{c++26}}、默认成员初始化器）中，则 C 在 P 处完整。所以在类内成员函数体里可以使用后面才声明的成员，也可以写 `sizeof(*this)`：

```cpp run ok
struct S {
  int f() { return sizeof(S) + g(); }   // OK: 函数体是完整类上下文
  int g() { return n; }
  int n = sizeof(S);                     // OK: 默认成员初始化器也是
  // S member;                           // error: S 在此处不完整
  S* next;                               // OK: 指向不完整类型的指针
};

int main() { return S{}.f() > 0 ? 0 : 1; }
```

### `delete` 不完整类型 {{c++26}}

对指向不完整类类型的指针做 `delete` 是一个经典陷阱。在 C++23 及之前，如果该类有非平凡析构函数或类专属的释放函数，行为未定义，而编译器只能给出警告。C++26 起，[[expr.delete#4]] 规定：如果被删除对象在删除点具有不完整类类型，**程序非良构**。

```cpp run error
struct Impl;                          // 不完整
void destroy(Impl* p) { delete p; }   // error（C++26）：删除不完整类型；C++23 中可能是 UB
```

Clang 23 在 `-std=c++2c` 下报错，在 `-std=c++23` 下给出 `-Wdelete-incomplete` 警告。pimpl 惯用法中 `std::unique_ptr<Impl>` 的析构函数必须定义在 `Impl` 完整之处，根源就在这里。

## 对象类型（¶6）

¶6 规定：**对象类型**（object type）是（可能 cv 限定的）既不是函数类型、也不是引用类型、也不是 cv `void` 的类型。

所以不完整的类类型和未知边界数组也是对象类型，只是不完整的对象类型。这个定义有意不排除不完整性，因为指向对象类型的指针（[[basic.compound#3]]）需要涵盖 `X*`（`X` 尚未定义）。

```cpp run ok
#include <type_traits>
struct Incomplete;
static_assert( std::is_object_v<int>);
static_assert( std::is_object_v<int[]>);          // 不完整，但仍是对象类型
static_assert( std::is_object_v<int* const>);
static_assert(!std::is_object_v<int&>);
static_assert(!std::is_object_v<void>);
static_assert(!std::is_object_v<int(int)>);
int main() {}
```

## 四个类型大类（¶7）

¶7 连续定义了四个类别。它们都以标量类型为基础，再加上某种类、数组以及 cv 版本：

### 标量类型

**标量类型**（scalar types）：算术类型、枚举类型、指针类型、成员指针类型、`std::meta::info` {{c++26}}、`std::nullptr_t`，以及它们的 cv 限定版本。

直观地说，标量就是一个不可再分的值，没有子对象。C++26 把反射值的类型 `std::meta::info` 加入了标量类型（静态反射，[[P2996R13]]），因此它可以作为非类型模板实参的类型，也可以在常量表达式中自由传递。C++23 及之前不存在这个类型。

### 平凡可复制类型

**平凡可复制类型**（trivially copyable types）：标量类型、平凡可复制类类型、它们的数组，以及 cv 版本。

平凡可复制类的定义在 [[class.prop#1]]：至少有一个合格（eligible）的复制/移动构造函数或复制/移动赋值运算符；每个合格的复制/移动构造与赋值都是平凡的；析构函数平凡且未被删除。

这一类型的意义完全体现在 [[basic.types.trivial]]：把底层字节复制到 `char`/`unsigned char`/`std::byte` 数组再复制回来，或在两个同类型对象之间复制，值也随之传递。换句话说，**对平凡可复制类型，`memcpy` 就是复制；对其他类型，它什么也不保证**。`std::bit_cast` 也要求源与目标都是平凡可复制的。

```cpp run ok
#include <type_traits>
#include <string>

struct A { int x; double y; };                 // 平凡可复制
struct B { int x; B(const B&) {} };            // 用户提供的复制构造 → 不是
struct C { int x; ~C() {} };                   // 非平凡析构 → 不是
struct D { std::string s; };                   // 成员不平凡 → 不是
struct E { const int x; };                     // 复制构造平凡，赋值被删除：仍是
struct F { int x; F& operator=(F&&) = delete; }; // 判定见下文"陷阱"

static_assert( std::is_trivially_copyable_v<A>);
static_assert(!std::is_trivially_copyable_v<B>);
static_assert(!std::is_trivially_copyable_v<C>);
static_assert(!std::is_trivially_copyable_v<D>);
static_assert( std::is_trivially_copyable_v<E>);
static_assert( std::is_trivially_copyable_v<const volatile int[4]>);
int main() {}
```

`F` 的判定留到陷阱一节讨论（标准与 Clang 在这里有分歧）。

### 标准布局类型

**标准布局类型**（standard-layout types）：标量类型、标准布局类类型、它们的数组，以及 cv 版本。

标准布局类的七条要求在 [[class.prop#2]]：没有非标准布局成员或引用成员；没有虚函数和虚基类；所有非静态数据成员的访问控制相同；没有非标准布局基类；同一类型的基类子对象至多一个；所有非静态数据成员（和位域）都首次声明于同一个类；基类不能与可能位于偏移 0 的成员类型集合 M(S) 中的类型相同。

标准布局提供的保证集中在 [[class.mem.general]]。对象地址与第一个非静态数据成员（非位域）的地址相同，也与所有基类子对象的地址相同（[[class.mem.general#31]]），因此二者**指针可互转**（[[basic.compound#7]]）；只有标准布局类才能可靠地使用 `offsetof`（[[support.types.layout]]）；联合体中共同初始序列的读取规则（[[class.mem.general#30]]）也只对标准布局结构有效。这些规定的目的是与 C 的内存模型兼容（¶2 脚注）。

```cpp run ok
#include <type_traits>

struct B { int i; };
struct C : B { };                 // 标准布局：所有数据成员都在 B 中
struct D : B { int j; };          // 不是：数据成员分散在 B 和 D 两个类中
struct E { int a; private: int b; };  // 不是：访问控制不同
struct V { virtual void f(); };   // 不是：有虚函数

static_assert( std::is_standard_layout_v<C>);
static_assert(!std::is_standard_layout_v<D>);
static_assert(!std::is_standard_layout_v<E>);
static_assert(!std::is_standard_layout_v<V>);
int main() {}
```

平凡可复制与标准布局是**两个独立的维度**（[[class.prop#6]] 的例子）：`E` 平凡可复制但不是标准布局；带用户析构函数的 `struct SL { int i; ~SL(); }` 是标准布局但不是平凡可复制。两者都满足的，大致就是旧称的 POD。

### 隐式生存期类型

**隐式生存期类型**（implicit-lifetime types）：标量类型、隐式生存期类类型、所有数组类型，以及 cv 版本。

隐式生存期类的定义在 [[class.prop#8]]：要么是析构函数非用户提供的聚合体，要么至少有一个平凡的合格构造函数，且析构函数平凡、未删除。

这个类别是 C++20 引入的（[[P0593R6]]），用来给一大批 C 风格代码补上合法的依据。在 C++17 中，

```cpp
#include <cstdlib>
struct X { int a, b; };
void f() {
  X* p = (X*)std::malloc(sizeof(X));
  p->a = 1;    // C++17：没有任何 X 对象被创建，严格说是 UB；C++20 起 OK
}
```

现在 [[intro.object#13]] 规定：某些操作（`malloc`/`operator new`/`memcpy`/`std::bit_cast`、开始 `unsigned char`/`std::byte` 数组的生存期等）会在指定存储中隐式创建零个或多个隐式生存期类型的对象并开始其生存期，只要这样做能让程序具有定义的行为。隐式生存期类型就是可以这样凭空创建的类型：创建它们不需要运行任何代码（没有非平凡构造），销毁它们也不需要（没有非平凡析构），所以假定它们已经存在不会改变程序的可观察行为。

注意**所有数组类型**都是隐式生存期类型，即使元素类型不是。创建一个数组对象并不创建它的元素：`NI arr[3]` 这个数组本身可以隐式出现，元素仍需另行构造（例如用 placement new）。分配一块内存当作 `T[N]`、再逐个构造元素的容器实现，由此有了合法依据。

```cpp run ok
#include <cstdlib>
#include <new>
#include <type_traits>

struct X  { int a, b; };
struct NI { NI() {} ~NI() {} };          // 非平凡构造/析构
struct Agg { int a; NI n; };             // 聚合体，析构函数非用户提供

static_assert( std::is_implicit_lifetime_v<X>);
static_assert(!std::is_implicit_lifetime_v<NI>);
static_assert( std::is_implicit_lifetime_v<NI[3]>);  // 数组总是
static_assert( std::is_implicit_lifetime_v<Agg>);    // 聚合体：即使成员不平凡

int main() {
  X* p = static_cast<X*>(std::malloc(sizeof(X)));    // malloc 隐式创建 X
  p->a = 1; p->b = 2;                                // OK（C++20 起）
  int r = p->a + p->b;
  std::free(p);
  return r == 3 ? 0 : 1;
}
```

`Agg` 那一行常常出人意料：聚合体即使含有非平凡成员，也算隐式生存期类。原因是聚合初始化本身不调用 `Agg` 的任何构造函数，隐式创建一个 `Agg` 只开始 `Agg` 的生存期，其子对象 `n` 并不因此被构造（它的生存期要另外开始）。C++23 补上了对应的 trait `std::is_implicit_lifetime`（[[P2674R1]]）和显式工具 `std::start_lifetime_as`（[[obj.lifetime]]）。

## 字面量类型（¶8）

**字面量类型**（literal type）是：

- ¶8.1 cv `void`；
- ¶8.2 标量类型；
- ¶8.3 引用类型；
- ¶8.4 字面量类型的数组；
- ¶8.5 满足以下全部条件的（可能 cv 限定的）类类型：
    - ¶8.5.1 有 `constexpr` 析构函数（[[dcl.constexpr]]）；
    - ¶8.5.2 所有非变体非静态数据成员和基类都是非 volatile 的字面量类型；
    - ¶8.5.3 并且它是以下之一：闭包类型（¶8.5.3.1）；没有变体成员或至少有一个非 volatile 字面量类型变体成员的聚合联合体（¶8.5.3.2）；每个匿名联合成员都满足前述联合条件的非联合聚合体（¶8.5.3.3）；或至少有一个不是复制/移动构造函数的 `constexpr` 构造函数或构造函数模板（可以是继承来的）（¶8.5.3.4）。

直观地说，字面量类型就是有可能在常量求值中创建对象的类型：要么像聚合体一样无需构造函数就能初始化，要么至少有一个 `constexpr` 构造函数可以从无到有造出一个对象。复制/移动构造不算，因为它们需要已有的对象。析构也必须能在编译期进行。

!!! std
    "A literal type is one for which it might be possible to create an object within a constant expression."
    —— Note 5：只是说可能，既不保证真的能创建，也不保证该类型的对象可用于常量表达式。

字面量类型的直接用途是 [[dcl.constexpr]] 对 `constexpr` 变量的要求：`constexpr` 变量的类型必须是字面量类型。此外，lambda 闭包类型从 C++17 起是字面量类型，所以可以写 `constexpr auto f = []{...};`。

```cpp run error
struct L  { constexpr L(int) {} };          // 字面量类型：有非复制的 constexpr 构造函数
struct NL { NL(int) {} };                   // 不是：没有 constexpr 构造函数
struct NL2 { constexpr NL2(const NL2&) = default; int x; }; // 不是聚合体（有用户声明的构造函数），
                                            // 唯一的 constexpr 构造函数是复制构造 → 非字面量
struct VM { volatile int x; };              // 不是：成员是 volatile

constexpr L  a(1);    // OK
constexpr NL b(1);    // error: NL 不是字面量类型
constexpr VM c{1};    // error: VM 不是字面量类型
```

`NL2` 处在 ¶8.5.3.4 的边界上：只有复制/移动构造函数是 `constexpr` 还不够，因为无法从无到有造出第一个对象。

### C++20/23 对字面量类型的放宽

- **C++20**：允许 `constexpr` 析构函数（因而 `std::string`、`std::vector` 成为字面量类型），¶8.5.1 从要求平凡析构改为要求 `constexpr` 析构；虚函数可以是 `constexpr`，所以有虚函数的类也可以是字面量类型。
- **C++23**（[[P2448R2]]）：`constexpr` 函数的参数和返回类型不再要求是字面量类型，函数体也不再要求至少有一组实参能产生常量表达式，违反只在真正进行常量求值时才报错。于是字面量类型这个概念在语言中的分量大大降低，目前主要还用于 `constexpr` 变量的类型、常量表达式中能创建的对象，以及结构化类型（[[temp.param]]）等定义的前提。
- `std::is_literal_type` 在 C++17 中弃用，C++20 中移除。理由正是 Note 5：是字面量类型并不意味着能在编译期用它做什么有用的事，这个 trait 回答的问题几乎没有实际意义。

## 布局兼容类型（¶9）

¶9 规定，两个类型 *cv1* `T1` 与 *cv2* `T2` 在下列情况下是**布局兼容类型**（layout-compatible types）：

- 是同一类型（cv 可以不同，`int` 与 `const volatile int` 布局兼容），或
- 是布局兼容的枚举（[[dcl.enum]]：底层类型相同），或
- 是布局兼容的标准布局类类型（[[class.mem.general#28]]：共同初始序列覆盖两个类的全部成员；联合体见 [[class.mem.general#29]]）。

注意**不同的标量类型从不布局兼容**，哪怕大小和表示完全相同。`int` 与 `unsigned int`、`int` 与 `long`（在 LP64 上 `long` 是 64 位，在 LLP64 上与 `int` 同为 32 位）、`char` 与 `signed char` 都不是。数组也只有在类型完全相同时才布局兼容。

布局兼容的用处：

1. 联合体中共同初始序列的定义要求对应成员布局兼容（[[class.mem.general#27]]），从而允许通过非活动成员读取共同前缀；
2. 按 [[basic.compound#3]]，指向布局兼容类型的指针具有相同的值表示和对齐要求。

```cpp run ok
struct A { int a; char b; };
struct B { int x; char y; };     // 与 A 布局兼容：共同初始序列覆盖全部成员
struct C { int x; unsigned char y; };   // 与 A 不布局兼容：char 与 unsigned char 不同
enum E1 : int {};
enum class E2 : int {};

// libc++ 尚未提供 std::is_layout_compatible（C++20），这里用 Clang 内建
static_assert( __is_layout_compatible(int, const int));
static_assert(!__is_layout_compatible(int, unsigned));
static_assert( __is_layout_compatible(A, B));
static_assert(!__is_layout_compatible(A, C));
static_assert( __is_layout_compatible(E1, E2));
int main() {}
```

!!! note
    `std::is_layout_compatible` 是 C++20 加入的 trait。写作时本机 libc++（随 Clang 23）尚未提供 `std::is_layout_compatible_v`，所以示例使用 Clang 和 GCC 都支持的内建 `__is_layout_compatible`。

## 实现视角

!!! impl "ABI 所说的平凡与标准的平凡可复制不是一回事"
    Itanium C++ ABI（Linux/macOS 上的 GCC、Clang）在决定类类型参数能否放在寄存器里传递时，用的是对调用而言非平凡（non-trivial for the purposes of calls）这一概念：有非平凡的复制构造、移动构造或析构函数，或者所有复制/移动构造都被删除。它与标准的平凡可复制相近但不相同。例如复制赋值是否平凡并不影响参数传递，却影响 `is_trivially_copyable`。Clang 提供 `[[clang::trivial_abi]]`，让带非平凡析构的类型（如某些智能指针）也按寄存器传递。MSVC 的 x64 ABI 有自己的一套判定规则，与 Itanium 不同。

!!! impl "尾部填充复用"
    Itanium ABI 在布局派生类时，会把派生类成员放进非 POD（按 ABI 的定义）基类的尾部填充里。这正是 [[basic.types.trivial#3]] 要排除潜在重叠子对象的原因：对基类子对象做 `memcpy(dst, src, sizeof(Base))` 可能覆盖派生类成员。

!!! impl "Clang 的分歧：全部删除的复制/移动操作"
    按 [[class.prop#1]]，如果一个类的复制/移动构造函数和复制/移动赋值运算符全部被删除，它就没有任何合格的此类函数，因此**不是**平凡可复制的（这是 C++20 引入合格概念后的规则）。Clang 23 的 `__is_trivially_copyable` 对这种类型仍返回 `true`，与标准不一致。写可移植代码时不要依赖这种边界情况。

## 历史与演进

!!! history
    - **C++98/03**：只有 POD（plain old data）一个概念，同时承担可 `memcpy`、与 C 布局兼容、可静态初始化三重职责，条件苛刻（例如任何用户声明的构造函数都会破坏 POD 性）。
    - **C++11**：把 POD 拆成两个正交概念，即平凡（trivial，进而平凡可复制）与标准布局，POD = 平凡 ∧ 标准布局。引入 `constexpr` 与字面量类型。
    - **C++14/17**：字面量类型的条件逐步放宽；C++17 闭包类型成为字面量类型；`std::is_literal_type` 弃用。
    - **C++20**：引入合格特殊成员函数，平凡可复制的定义改写为“至少一个合格的…，且全部合格的都平凡”；引入隐式生存期类型与隐式对象创建（[[P0593R6]]）；`constexpr` 析构函数进入字面量类型的定义；`std::is_pod` 弃用、`std::is_literal_type` 移除；`std::is_layout_compatible` 加入。
    - **C++23**：`constexpr` 函数不再要求字面量类型的参数/返回值（[[P2448R2]]）；新增 `std::is_implicit_lifetime`（[[P2674R1]]）与 `std::start_lifetime_as`。
    - **C++26**：`std::meta::info` 成为标量类型 {{c++26}}（[[P2996R13]]）；平凡类型/平凡类的概念连同 `std::is_trivial` 一起移入附录 D 弃用（[[P3247R2]]，见 [[depr.meta.types]]），因为平凡把平凡可复制和平凡默认构造捆在一起，而几乎没有代码真正需要这个组合；`delete` 不完整类类型从 UB 变为非良构。

## 陷阱

!!! pitfall "不要混用四个平凡"
    - `is_trivially_copyable<T>`：可以 `memcpy`。绝大多数代码真正需要的是这一个。
    - `is_trivial<T>`（C++26 弃用）：平凡可复制，**且**有平凡默认构造。`struct S { int x = 0; };` 有默认成员初始化器，默认构造不平凡，所以 `S` 不是平凡类型，但完全可以 `memcpy`。
    - `is_standard_layout<T>`：与 C 布局兼容、可 `offsetof`。与能否 `memcpy` 无关。
    - `is_pod<T>`（C++20 弃用）：前两者的合取，早已不该用来做任何判断。

!!! pitfall "`is_trivially_copyable` 为真 ≠ 可以 `memcpy` 到任何该类型的对象"
    [[basic.types.trivial#3]] 只对非潜在重叠的子对象保证 `memcpy` 的语义。基类子对象和 `[[no_unique_address]]` 成员可能与其他对象共享尾部填充，按 `sizeof` 整块复制会覆盖相邻数据。

!!! pitfall "删除了移动赋值的类"
    再看上文的 `struct F { int x; F& operator=(F&&) = delete; };`。用户声明了移动赋值（即使是删除的），所以隐式的复制构造和复制赋值被定义为删除（[[class.copy.ctor]]、[[class.copy.assign]]），移动构造则不会隐式声明。被删除的函数不合格（[[special]]），于是 `F` 没有任何合格的复制/移动操作，按 [[class.prop#1.1]] **不是**平凡可复制的。Clang 23 对此报告 `true`。这个例子还说明，`is_trivially_copyable` 与能否复制无关：`E { const int x; }` 不可赋值，却是平凡可复制的。

!!! pitfall "在不完整类型上用 trait"
    绝大多数类型 trait 要求实参是完整类型、cv `void` 或未知边界数组（见 [[meta.unary.prop]] 表中的前置条件），否则行为未定义。更隐蔽的是，同一个模板特化在类型完整前后实例化会得到不同结果，违反 ODR（[[basic.def.odr]]）。

## 思考题

!!! question "1. 下面哪些是隐式生存期类型？"
    ```cpp
    struct A { int x; A() = default; };
    struct B { int x; B() {} };
    struct C { std::string s; };     // 聚合体
    struct D { D() = default; ~D() {} };
    using E = std::string[2];
    ```

<details markdown="1">
<summary>答案</summary>

- `A`：默认构造平凡、析构平凡 → 是（也是聚合体）。
- `B`：有用户提供的构造函数，不是聚合体；唯一的默认构造非平凡。但复制/移动构造是平凡且合格的，[[class.prop#8.2]] 只要求至少一个平凡的合格构造函数，复制构造也算；析构也平凡 → **是**。这一点常被忽略：只要有一个平凡构造（哪怕是复制构造），对象就可以通过复制字节的方式产生。
- `C`：聚合体，析构函数不是用户提供的 → 是（即使 `std::string` 不是）。
- `D`：有用户提供的析构函数（`~D() {}` 是用户提供的），既不满足 8.1 也不满足 8.2 → 不是。
- `E`：数组类型 → 总是。
</details>

!!! question "2. `extern int a[]; int a[10];` 之后，`decltype(a)` 是什么？指向它的 `int (*p)[] = &a;` 能否 `p + 1`？"

<details markdown="1">
<summary>答案</summary>

重新声明后 `a` 的类型是 `int[10]`，`decltype(a)` 为 `int[10]`（¶4：两处的数组类型是不同类型，后者完整）。`int (*p)[] = &a;` 合法（C++20 起的限定转换），但 `p` 指向的类型 `int[]` 永远不完整，`p + 1` 需要知道 `sizeof(int[])`，所以非良构。
</details>

!!! question "3. 为什么 ¶7 把 cv 限定版本显式列入每一个类别？`const int` 难道不是自动属于标量类型吗？"

<details markdown="1">
<summary>答案</summary>

算术类型等基础类别在某些定义里本身就包含 cv 版本（如整型、浮点类型），但枚举、指针、成员指针、`nullptr_t` 这些名称在标准中指的是 cv 无限定的类型，类类型也是。如果不显式列入，`const MyEnum`、`int* const`、`const std::nullptr_t` 就会被排除在标量、平凡可复制等类别之外。标准选择在类别定义处统一对 cv 封闭，于是 trait 对 `T` 与 `cv T` 的结果一致。
</details>

## 小结

!!! summary
    - 类型 = 基础类型 ⊎ 复合类型；[[g:object-type|对象类型]]是除函数、引用、cv `void` 之外的一切（包括不完整的类和数组）。
    - [[g:object-representation|对象表示]]是 `sizeof(T)` 个字节，[[g:value-representation|值表示]]是其中承载值的位，其余为[[g:padding-bits|填充位]]；同一值可有多种对象表示，所以字节比较和哈希需要 `has_unique_object_representations`。
    - [[g:incomplete-type|不完整类型]]：未定义的类、定义完成前的枚举、未知边界数组、元素不完整的数组、cv `void`。类完成后仍是同一类型；`int[]` → `int[10]` 是不同类型，`int[]` 本身永远不完整。
    - 以标量为基础的四个类别：[[g:trivially-copyable-type|平凡可复制]]（`memcpy` 语义）、[[g:standard-layout-type|标准布局]]（C 兼容布局）、[[g:implicit-lifetime-type|隐式生存期]]（可隐式创建，所有数组都算），以及 [[g:literal-type|字面量类型]]（可能在常量求值中创建）。
    - [[g:layout-compatible-types|布局兼容]]只承认同一类型（忽略 cv）、底层类型相同的枚举、成员一一布局兼容的标准布局类；`int` 与 `unsigned` 从不布局兼容。
    - C++26：`std::meta::info` 是标量；平凡类型弃用；`delete` 不完整类非良构。
