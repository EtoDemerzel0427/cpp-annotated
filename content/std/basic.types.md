---
title: 类型
summary: 类型怎样分类；对象在内存里占哪些字节、哪些位承载值；什么是不完整类型；平凡可复制、标准布局、隐式生存期、字面量、布局兼容这几个类别分别保证什么。
status: draft
covers: basic.types.general
papers: P0593R6, P2448R2, P2674R1, P3247R2, P2996R13
related: basic.types.trivial, basic.fundamental, basic.compound, basic.type.qualifier, conv.rank, class.prop, intro.object, basic.lval
tags: 类型系统, 对象模型
updated: 2026-10-19
---

!!! tldr
    - 对象占 `sizeof(T)` 个字节，这些字节叫对象表示；其中真正承载值的位是值表示，其余是填充位。所以相等的两个对象，字节可以不同。
    - 不完整类型（已声明未定义的类、未知边界的数组、`void` 等）的大小未知，不能用来定义对象、求 `sizeof` 或做指针算术。
    - 平凡可复制类型可以用 `memcpy` 复制；标准布局类型的布局与 C 兼容；隐式生存期类型的对象可以由 `malloc` 之类的操作凭空创建。三者是互相独立的性质。
    - 字面量类型只表示可能在常量求值中创建对象，C++23 起这个概念的用处已经很小。
    - 不同的标量类型从不布局兼容，即使 `int` 和 `long` 的大小与表示完全相同。

[[basic.types]]（6.9）不讲怎样声明类型，那是 [[dcl]] 和 [[class]] 的事。它回答更底层的问题：类型有哪几类，一个对象在内存里占哪些字节，哪些类型可以按字节复制、可以凭空出现在 `malloc` 来的内存里。后面的别名规则 [[basic.lval]]、生存期 [[basic.life]]、常量求值 [[expr.const]] 和 `<type_traits>` 都建立在这些术语上。

本页讲 6.9.1 [[basic.types.general]]。其余子条款各有一页：[[basic.types.trivial]]（`memcpy` 的保证）、[[basic.fundamental]]（整数、字符、浮点等，含 6.9.4 扩展浮点类型）、[[basic.compound]]（指针、数组、引用等）、[[basic.type.qualifier]]（const 与 volatile）、[[conv.rank]]（转换等级）。

## 类型的分类

¶1 是一个注：类型分为**基础类型**（fundamental type，语言内建的整数、浮点、`void` 等，见 [[basic.fundamental]]）和**复合类型**（compound type，由其他类型构造出来的数组、指针、类等，见 [[basic.compound]]）。类型描述的是对象、引用或函数。

引用和函数都不是对象（[[intro.object]]），但都有类型。所以标准后面要单独定义对象类型（¶6），因为 `sizeof`、`new`、数组元素这些规则只对对象类型有意义。

`<type_traits>` 的主类别 trait 把每个类型恰好归入下面树中的一个叶子（[[meta.unary.cat]]）：

```text
类型
├── 基础类型                                is_fundamental
│   ├── 算术类型                            is_arithmetic
│   │   ├── 整型：bool、字符类型、有/无符号整数  is_integral
│   │   └── 浮点类型                        is_floating_point
│   ├── cv void                             is_void
│   ├── std::nullptr_t                      is_null_pointer
│   └── std::meta::info  (C++26)            is_reflection
└── 复合类型                                is_compound
    ├── 数组                                is_array
    ├── 函数                                is_function
    ├── 指针                                is_pointer
    ├── 左值引用 / 右值引用                  is_lvalue_reference / is_rvalue_reference
    ├── 类（非联合） / 联合                   is_class / is_union
    ├── 枚举                                is_enum
    └── 数据成员指针 / 成员函数指针           is_member_object_pointer / is_member_function_pointer
```

本页 ¶6–¶9 定义的类别与这棵树交叉，例如标量类型同时包含基础类型里的算术类型和复合类型里的指针、枚举。主类别 trait 对 `T` 和 `const T` 给出相同的结果（[[meta.unary.cat#2]]），所以 `is_integral_v<const int>` 为真。

## 对象表示与值表示（¶2）

```cpp run ok
#include <type_traits>

struct P { char c; int i; };   // c 之后通常有 3 字节填充
struct Q { int a; int b; };    // 常见 ABI 上没有填充

static_assert(!std::has_unique_object_representations_v<P>);
static_assert( std::has_unique_object_representations_v<Q>);  // 取决于 ABI
static_assert( std::has_unique_object_representations_v<int>);
static_assert(!std::has_unique_object_representations_v<float>);

int main() {}
```

在常见 ABI 上 `sizeof(P) == 8`，可是 `P` 的值只由 5 个字节决定。两个相等的 `P` 对象，另外 3 个字节可以不同。标准用两个术语描述这种情况。

¶2 类型 `T` 的[[g:object-representation|对象表示]]（object representation）是 `T` 的一个完整对象所占据的 `sizeof(T)` 个 `unsigned char` 对象的序列。[[g:value-representation|值表示]]（value representation）是对象表示中参与表示值的那些位。不属于值表示的位叫做[[g:padding-bits|填充位]]（padding bits）。

位域单独定义：它的对象表示是它占据的那几位（位数等于位域宽度，[[class.bit]]），值表示是其中参与表示值的位。

同一个值可以有多种对象表示，原因有三种：

1. 类里的填充字节，如上面的 `P`。
2. 标量类型内部的填充位。x86-64 Linux 上的 80 位 `long double` 占 16 字节，其中 48 位是填充；`bool` 通常占 8 位，但只有两个值（[[basic.fundamental#10]]）。
3. 同一个值有多种位模式，或者一种位模式不对应唯一的值。IEEE 浮点的 `+0.0` 和 `-0.0` 比较相等但位不同，NaN 有很多种位模式。

所以 `memcmp` 和按字节哈希只对每个值恰好有一种对象表示的类型可靠。`std::has_unique_object_representations`（[[meta.unary.prop]]）回答的正是这个问题，上面的例子在本机 Clang 23 上通过。

`std::bit_cast` 在常量求值中也要看值表示：结果中如果有字节来自源对象的填充位，那个字节的值是不确定的，整个表达式不是常量表达式（[[bit.cast]]）。

```cpp run error
#include <bit>

struct P  { char c; int i; };
struct B8 { unsigned char b[8]; };

constexpr P  p{1, 2};
constexpr B8 bytes = std::bit_cast<B8>(p);   // error: b[1..3] 来自填充
```

!!! impl "填充字节里可能有旧数据"
    编译器复制结构体时可以不复制填充，也可以在填充里留下任意内容。把结构体按字节写进文件或网络包，可能泄露内存里的旧数据。安全敏感的代码通常先 `memset` 整个对象，再逐个填写成员。

## 不完整类型（¶3–¶5）

```cpp run error
class X;                 // X 是不完整类型
extern X* xp;            // OK：可以有指向不完整类型的指针
extern int arr[];        // arr 的类型不完整
typedef int UNKA[];      // UNKA 是不完整类型
UNKA* arrp;
UNKA** arrpp;

void foo() {
  xp++;                  // error: X 不完整，不知道步长
  arrp++;                // error: 不完整类型
  arrpp++;               // OK: sizeof(UNKA*) 已知
}

struct X { int i; };     // 现在 X 完整了
int arr[10];             // 现在 arr 的类型完整了

X x;
void bar() {
  xp = &x;               // OK
  arrp = &arr;           // OK: int(*)[10] → int(*)[]，限定转换
  xp++;                  // OK: X 已完整
  arrp++;                // error: UNKA 永远无法完成
}
```

这是标准 ¶4 的例 1。`xp++` 需要知道 `X` 的大小才能算出步长，所以要等 `X` 定义之后才合法。`arrp++` 却永远不合法，原因在下面。

¶3 以下三种叫**不完全定义的对象类型**（incompletely-defined object type）：已声明但未定义的类；某些上下文中的枚举；未知边界的数组，或元素类型不完整的数组。它们和 cv `void` 合称[[g:incomplete-type|不完整类型]]（incomplete type）。脚注说明了实质：这些类型的大小和布局未知。所以不能定义不完整类型的对象（注 2），也不能求 `sizeof`、`new`、做指针算术或访问成员。具体哪些上下文禁止不完整类型，由各条声明和表达式规则分别规定（¶5 的注 4）。

!!! note "枚举什么时候不完整"
    底层类型固定的枚举，在 *enum-base* 之后就是完整的，所以 `enum class E : int;` 之后就能用 `sizeof(E)`。底层类型不固定的枚举要到右花括号才完整，因为编译器要看到所有枚举项才能选定底层类型（[[dcl.enum#6]]）。

### 类变完整，类型不变；数组变完整，类型变了（¶4）

¶4 区分了两种后来变完整的情况：

- `class X;` 之后 `X` 不完整，`class X { ... };` 之后完整，前后是同一个类型。元素是 `X` 的数组 `X[3]` 也随之变完整，同样是同一个类型。
- `extern int arr[];` 中 `arr` 的类型是 `int[]`。之后 `int arr[10];` 重新声明，`arr` 的类型变成 `int[10]`。这是两个不同的类型：变完整的是变量 `arr` 的声明类型，`int[]` 这个类型本身并没有变化。

所以注 3 说，指向未知边界数组的指针或引用，以及用 typedef 命名的未知边界数组，永远是不完整类型。上例中 `arrp` 的类型是 `int(*)[]`，`int[]` 无法完成，`arrp++` 也就永远非良构。`arrp = &arr` 把 `int(*)[10]` 转成 `int(*)[]`，这是 C++20 起允许的限定转换（[[conv.qual]]）。

### 类在哪里算完整

一个类在它的定义之后完整。此外，在类的**完整类上下文**（complete-class context）里，类也算完整，即使类定义还没结束。完整类上下文包括成员函数体、默认实参、*noexcept-specifier*、默认成员初始化器等（[[class.mem.general#10]]、[[class.mem.general#11]]）。所以成员函数体里可以使用后面才声明的成员，也可以写 `sizeof(S)`：

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

```cpp run error
struct Impl;                          // 不完整
void destroy(Impl* p) { delete p; }   // error（C++26）
```

C++23 及以前，如果 `Impl` 有非平凡析构函数或类专属的释放函数，这样的 `delete` 是 UB，编译器只能给警告。C++26 起，[[expr.delete#4]] 规定删除点上被删除对象的类型不完整时程序非良构。本机 Clang 23 在 `-std=c++2c` 下报错，在 `-std=c++23` 下给出 `-Wdelete-incomplete` 警告。

pimpl 惯用法里，持有 `std::unique_ptr<Impl>` 的类必须把析构函数定义在 `Impl` 完整的源文件里，原因就在这里。

## 对象类型（¶6）

¶6 [[g:object-type|对象类型]]（object type）是除函数类型、引用类型和 cv `void` 之外的所有类型，cv 限定的也算。

这个定义不排除不完整类型。未定义的类、`int[]` 都是对象类型，只是不完整。这样指向对象类型的指针（[[basic.compound#3]]）才能涵盖 `X*`（`X` 尚未定义）这种情况。

```cpp run ok
#include <type_traits>
struct Incomplete;
static_assert( std::is_object_v<int>);
static_assert( std::is_object_v<int[]>);          // 不完整，但仍是对象类型
static_assert( std::is_object_v<Incomplete>);
static_assert(!std::is_object_v<int&>);
static_assert(!std::is_object_v<void>);
static_assert(!std::is_object_v<int(int)>);
int main() {}
```

## 标量与三个以它为基础的类别（¶7）

¶7 先定义[[g:scalar-type|标量类型]]（scalar type）：算术类型、枚举类型、指针类型、成员指针类型、`std::meta::info`、`std::nullptr_t`，以及它们的 cv 限定版本。直观地说，标量是一个不可再分的值，没有子对象。`std::meta::info` 是 C++26 静态反射中反射值的类型（[[P2996R13]]），它是标量，所以可以用作非类型模板形参的类型。

接下来的三个类别都按同一个模式定义：标量类型，加上满足某个条件的类，加上数组，再加上它们的 cv 版本。区别在于对类提出的条件。

| 类别 | 类的条件 | 数组 | trait | 保证什么 |
|---|---|---|---|---|
| 平凡可复制 | 平凡可复制类 | 元素也须属于此类别 | `is_trivially_copyable` | `memcpy` 等于复制 |
| 标准布局 | 标准布局类 | 元素也须属于此类别 | `is_standard_layout` | 布局与 C 兼容 |
| 隐式生存期 | 隐式生存期类 | 任何数组 | `is_implicit_lifetime` | 可以被隐式创建 |

这三个性质互相独立。各自对类的要求都在 [[class.prop]]。

### 平凡可复制类型

[[g:trivially-copyable-type|平凡可复制类型]]（trivially copyable type）的意义在 [[basic.types.trivial]]：把对象的字节复制到别处再复制回来，或者在两个同类型对象之间复制字节，值也跟着复制过去。对其他类型，`memcpy` 什么都不保证。`std::bit_cast` 也要求源和目标都是平凡可复制的。

平凡可复制类的条件（[[class.prop#1]]）要用到**合格**（eligible）这个词：一个特殊成员函数没有被删除、约束（如果有）得到满足、也没有被约束更强的同类函数取代，它就是合格的（[[special]]）。条件是：至少有一个合格的复制构造、移动构造、复制赋值或移动赋值；每个合格的这类函数都是平凡的；析构函数平凡且未删除。

```cpp run ok
#include <type_traits>
#include <string>

struct A { int x; double y; };        // 是
struct B { int x; B(const B&) {} };   // 不是：用户提供的复制构造
struct C { int x; ~C() {} };          // 不是：析构函数不平凡
struct D { std::string s; };          // 不是：成员不是
struct E { const int x; };            // 是：复制构造平凡，赋值被删除

static_assert( std::is_trivially_copyable_v<A>);
static_assert(!std::is_trivially_copyable_v<B>);
static_assert(!std::is_trivially_copyable_v<C>);
static_assert(!std::is_trivially_copyable_v<D>);
static_assert( std::is_trivially_copyable_v<E>);
static_assert( std::is_trivially_copyable_v<const volatile int[4]>);
int main() {}
```

`E` 不能赋值，却是平凡可复制的。这个性质只说按字节复制是否保留值，不说这个类型能不能复制。

### 标准布局类型

[[g:standard-layout-type|标准布局类型]]（standard-layout type）的类部分要求（[[class.prop#2]]）大致是：没有虚函数和虚基类；所有非静态数据成员的访问控制相同；所有非静态数据成员都首次声明在同一个类里；成员和基类也都是标准布局的；另外还有几条防止两个同类型子对象落在同一地址的限制。

```cpp run ok
#include <type_traits>

struct B { int i; };
struct C : B { };                     // 是：数据成员都在 B 中
struct D : B { int j; };              // 不是：数据成员分散在 B 和 D
struct E { int a; private: int b; };  // 不是：访问控制不同
struct V { virtual void f(); };       // 不是：有虚函数

static_assert( std::is_standard_layout_v<C>);
static_assert(!std::is_standard_layout_v<D>);
static_assert(!std::is_standard_layout_v<E>);
static_assert(!std::is_standard_layout_v<V>);
int main() {}
```

满足这些要求后，布局就和 C 的结构体一样可预测：对象的地址与第一个非静态数据成员（非位域）的地址相同，也与每个基类子对象的地址相同（[[class.mem.general#31]]），因此它们[[g:pointer-interconvertible|指针可互转]]，可以用 `reinterpret_cast` 互相转换（[[basic.compound#7]]）。`offsetof` 只对标准布局类有保证（[[support.types.layout]]），联合体通过非活动成员读取共同初始序列的规则也只适用于标准布局结构（[[class.mem.general#30]]）。

上例中的 `E` 平凡可复制但不是标准布局；带用户析构函数的 `struct SL { int i; ~SL(); };` 是标准布局但不是平凡可复制。两者都满足的类型，大致就是旧标准里的 POD。

### 隐式生存期类型

```cpp run ok
#include <cstdlib>

struct X { int a, b; };

int main() {
  X* p = static_cast<X*>(std::malloc(sizeof(X)));
  p->a = 1; p->b = 2;     // C++17 严格说是 UB：没有创建任何 X 对象
  int r = p->a + p->b;    // C++20 起 OK：malloc 隐式创建了 X
  std::free(p);
  return r == 3 ? 0 : 1;
}
```

这是 C 风格代码的常见写法。C++17 的对象模型里，对象只能由定义、`new` 表达式等方式创建，`malloc` 返回的内存里没有 `X` 对象，访问 `p->a` 严格说是 UB。C++20 通过 [[P0593R6]] 修正了这个问题。

[[intro.object#13]] 规定，`malloc`、`operator new`、`memcpy`、`std::bit_cast` 以及开始 `unsigned char` 或 `std::byte` 数组的生存期等操作，会在相应存储中**隐式创建对象**：只要创建某些对象能让程序具有定义的行为，就认为这些对象已经被创建了。能这样创建的只有[[g:implicit-lifetime-type|隐式生存期类型]]（implicit-lifetime type）。这些类型的对象的创建和销毁都不需要运行任何代码，所以假定它们已经存在不会改变程序的行为。

隐式生存期类的条件（[[class.prop#8]]）是二选一：它是析构函数不由用户提供的**聚合体**（aggregate，没有用户声明的构造函数、没有虚函数、没有私有或保护的直接非静态数据成员等，可以用花括号逐成员初始化的类，见 [[dcl.init.aggr]]）；或者它至少有一个平凡的合格构造函数，并且析构函数平凡且未删除。

```cpp run ok
#include <type_traits>

struct NI  { NI() {} ~NI() {} };    // 构造和析构都不平凡
struct Agg { int a; NI n; };        // 聚合体，析构函数不是用户提供的

static_assert(!std::is_implicit_lifetime_v<NI>);
static_assert( std::is_implicit_lifetime_v<NI[3]>);  // 数组总是
static_assert( std::is_implicit_lifetime_v<Agg>);    // 成员不平凡也是
int main() {}
```

两个结果常常出人意料：

- 任何数组类型都是隐式生存期类型，即使元素类型不是。隐式创建一个数组并不创建它的元素，元素仍要另行构造，例如用 placement new。容器先分配一块内存当作 `T[N]`，再逐个构造元素，依据就是这一条。
- 聚合体即使含有不平凡的成员也算。隐式创建一个 `Agg` 只开始 `Agg` 本身的生存期，成员 `n` 并没有因此被构造。

C++23 补上了对应的 trait `std::is_implicit_lifetime`（[[P2674R1]]），以及在已有字节上显式开始对象生存期的 `std::start_lifetime_as`（[[obj.lifetime]]）。

## 字面量类型（¶8）

[[g:literal-type|字面量类型]]（literal type）是 `constexpr` 变量必须具有的类型（[[dcl.constexpr]]）。¶8 列出的情况是：cv `void`、标量类型、引用类型、字面量类型的数组，以及满足下面全部条件的类类型：

- ¶8.5.1 有 `constexpr` 析构函数；
- ¶8.5.2 所有非变体的非静态数据成员和基类都是非 volatile 的字面量类型；
- ¶8.5.3 并且有办法在常量求值中从无到有造出一个对象：它是闭包类型（lambda 的类型）；或者是聚合体（联合体要求没有变体成员或至少有一个非 volatile 字面量类型的变体成员，非联合聚合体的匿名联合成员也要满足这一条）；或者至少有一个不是复制或移动构造函数的 `constexpr` 构造函数或构造函数模板，继承来的也算。

复制和移动构造函数不算，因为它们需要先有一个对象。

```cpp run error
struct L   { constexpr L(int) {} };   // 字面量类型
struct NL  { NL(int) {} };            // 不是：没有 constexpr 构造函数
struct NL2 {                          // 不是：唯一的 constexpr 构造函数
  constexpr NL2(const NL2&) = default; //       是复制构造函数
  int x;
};
struct VM  { volatile int x; };       // 不是：成员是 volatile

constexpr L  a(1);    // OK
constexpr NL b(1);    // error: NL 不是字面量类型
constexpr VM c{1};    // error: VM 不是字面量类型
```

!!! std
    A literal type is one for which it might be possible to create an object within a constant expression.

注 5 强调的是可能二字：是字面量类型，既不保证真的能在常量表达式里创建它的对象，也不保证它的对象能用在常量表达式里。

这个概念的分量一直在下降。C++20 允许 `constexpr` 析构函数，`std::string`、`std::vector` 因此成为字面量类型。C++23 的 [[P2448R2]] 取消了 `constexpr` 函数的参数和返回类型必须是字面量类型的要求。今天它主要还用于 `constexpr` 变量的类型，以及常量求值中能创建哪些对象。`std::is_literal_type` 正是因为回答的问题几乎没有实际用途，在 C++17 弃用、C++20 移除。

## 布局兼容类型（¶9）

¶9 两个类型 *cv1* `T1` 和 *cv2* `T2` 在以下情况下是[[g:layout-compatible-types|布局兼容类型]]（layout-compatible types）：

- 它们是同一个类型，cv 可以不同，所以 `int` 与 `const int` 布局兼容；
- 它们是布局兼容的枚举，即底层类型相同（[[dcl.enum]]）；
- 它们是布局兼容的标准布局类：两个类的共同初始序列（从第一个成员开始、类型逐个布局兼容的最长成员序列）覆盖了全部成员（[[class.mem.general#28]]；联合体见 [[class.mem.general#29]]）。

不同的标量类型从不布局兼容，哪怕大小和表示完全相同：`int` 与 `unsigned int`、`char` 与 `signed char`、Windows 上同为 32 位的 `int` 与 `long` 都不是。

```cpp run ok
struct A { int a; char b; };
struct B { int x; char y; };            // 与 A 布局兼容
struct C { int x; unsigned char y; };   // 与 A 不布局兼容
enum E1 : int {};
enum class E2 : int {};

// libc++ 尚未提供 std::is_layout_compatible，这里用 Clang 和 GCC 的内建
static_assert( __is_layout_compatible(int, const int));
static_assert(!__is_layout_compatible(int, unsigned));
static_assert( __is_layout_compatible(A, B));
static_assert(!__is_layout_compatible(A, C));
static_assert( __is_layout_compatible(E1, E2));
int main() {}
```

布局兼容有两个用处。一是联合体中两个结构体成员的共同初始序列，要求对应成员布局兼容，这样才能通过非活动成员读取共同的前缀（[[class.mem.general#27]]、[[class.mem.general#30]]）。二是指向布局兼容类型的指针具有相同的值表示和对齐要求（[[basic.compound#3]]）。

`std::is_layout_compatible` 是 C++20 加入的 trait，但本机 Clang 23 自带的 libc++ 还没有提供它。

## 实现视角

!!! impl "ABI 的平凡与标准的平凡可复制不是一回事"
    Itanium C++ ABI（Linux 和 macOS 上的 GCC、Clang）决定类类型参数能否放在寄存器里传递时，看的是这个类是否对调用而言非平凡：有非平凡的复制构造、移动构造或析构函数，或者所有复制和移动构造都被删除。复制赋值是否平凡不影响参数传递，却影响 `is_trivially_copyable`。Clang 的 `[[clang::trivial_abi]]` 可以让带非平凡析构的类型也按寄存器传递。MSVC 的 x64 ABI 另有一套规则。

!!! impl "Clang 对全部删除的复制和移动操作的判定"
    `struct F { int x; F& operator=(F&&) = delete; };` 声明了移动赋值，于是隐式的复制构造和复制赋值被定义为删除（[[class.copy.ctor]]、[[class.copy.assign]]），移动构造也不再隐式声明。被删除的函数不合格，`F` 没有任何合格的复制或移动操作，按 [[class.prop#1.1]] 不是平凡可复制的。但本机 Clang 23 的 `std::is_trivially_copyable_v<F>` 为 `true`，与标准不一致。可移植代码不要依赖这种边界情况。

## 历史与演进

!!! history
    - C++98 只有 POD（plain old data）一个概念，同时承担可以 `memcpy`、与 C 布局兼容、可以静态初始化三种职责，条件很严：任何用户声明的构造函数都会破坏 POD 性。
    - C++11 把 POD 拆成平凡（进而有平凡可复制）和标准布局两个独立的概念，POD 是两者的合取。同时引入 `constexpr` 和字面量类型。
    - C++20 引入合格特殊成员函数，平凡可复制改写为现在的定义；引入隐式生存期类型和隐式对象创建（[[P0593R6]]）；`std::is_pod` 弃用。
    - C++23 取消 `constexpr` 函数对字面量类型的要求（[[P2448R2]]），新增 `std::is_implicit_lifetime`（[[P2674R1]]）和 `std::start_lifetime_as`。
    - C++26 中 `std::meta::info` 成为标量类型；平凡类和 `std::is_trivial` 移入附录 D 弃用（[[P3247R2]]，见 [[depr.meta.types]]），因为平凡把可以 `memcpy` 和默认构造什么也不做两件事捆在一起，几乎没有代码需要这个组合；`delete` 不完整类类型从 UB 变为非良构。

## 常见误解

!!! pitfall "几个平凡分不清"
    - `is_trivially_copyable<T>`：可以 `memcpy`。大多数代码真正需要的是这一个。
    - `is_trivial<T>`（C++26 弃用）：平凡可复制，并且默认构造函数平凡。`struct S { int x = 0; };` 有默认成员初始化器，默认构造不平凡，所以不是平凡类型，但完全可以 `memcpy`。
    - `is_standard_layout<T>`：布局与 C 兼容、可以用 `offsetof`，与能否 `memcpy` 无关。
    - `is_pod<T>`（C++20 弃用）：前两者的合取，不应再用来做任何判断。

!!! pitfall "平凡可复制就可以 `memcpy` 到任何该类型的对象"
    [[basic.types.trivial#3]] 的保证不包括**潜在重叠子对象**（potentially-overlapping subobject），即基类子对象和带 `[[no_unique_address]]` 的成员（[[intro.object#7]]）。它们可能与其他对象共享尾部填充，按 `sizeof` 整块复制会覆盖相邻的数据，例子见 [[basic.types.trivial]]。

!!! pitfall "在不完整类型上使用 trait"
    大多数类型 trait 要求实参是完整类型、cv `void` 或未知边界数组（见 [[meta.unary.prop]] 的前置条件），否则行为未定义。同一个 trait 特化在类型完整前后实例化可能得到不同结果，这会违反 ODR（[[basic.def.odr]]）。

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

- `A` 是。C++20 起，用户声明的构造函数（即使是 `= default`）会使类不再是聚合体（[[dcl.init.aggr]]），所以 `A` 不满足 [[class.prop#8.1]]。但默认构造函数是平凡的，析构函数也平凡，满足 [[class.prop#8.2]]。
- `B` 是。它有用户提供的构造函数，不是聚合体，默认构造也不平凡。可是隐式声明的复制构造函数是平凡且合格的，¶8.2 只要求至少一个平凡的合格构造函数，复制构造也算。
- `C` 是。它是聚合体，析构函数不是用户提供的，与 `std::string` 是不是隐式生存期类型无关。
- `D` 不是。`~D() {}` 是用户提供的析构函数，不平凡，两个条件都不满足。
- `E` 是。所有数组类型都是。

本机 Clang 23 的 `std::is_implicit_lifetime_v` 对这五个类型给出同样的结论。
</details>

!!! question "2. `extern int a[]; int a[10];` 之后，`decltype(a)` 是什么？`int (*p)[] = &a;` 之后能否写 `p + 1`？"

<details markdown="1">
<summary>答案</summary>

重新声明后 `a` 的类型是 `int[10]`，`decltype(a)` 是 `int[10]`（¶4：两处的数组类型是不同的类型）。`int (*p)[] = &a;` 合法，这是 C++20 起允许的限定转换。但 `p` 指向的类型 `int[]` 永远不完整，`p + 1` 需要知道它的大小，所以非良构。
</details>

!!! question "3. ¶7 为什么在每个类别里都显式列出 cv 限定版本？"

<details markdown="1">
<summary>答案</summary>

整型、浮点类型这些类别的定义本身就包含 cv 版本，但在标准的用语里，枚举类型、指针类型、成员指针类型、`std::nullptr_t` 和类类型都指 cv 无限定的类型。不显式列出，`const MyEnum`、`int* const`、`const std::nullptr_t` 就会被排除在标量、平凡可复制等类别之外。在类别定义处统一包含 cv 版本，trait 对 `T` 和 `const T` 的结果才一致。
</details>
