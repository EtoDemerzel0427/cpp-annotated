---
title: 对象模型
summary: 什么构造会创建对象；子对象、完整对象、最派生对象；提供存储与嵌套；对象地址的唯一性与零大小子对象；隐式对象创建与"合适的已创建对象"
status: done
papers: P0593R6, P2590R2, P0137R1
related: basic.life, basic.types, basic.lval, basic.compound, expr.new, class.union
tags: 对象模型, 隐式对象创建, UB, no_unique_address
updated: 2026-10-17
---

这一页回答 C++ 里最基础、也最常被误解的问题：**对象是什么，从哪里来**。

很多程序员（尤其是从 C 过来的）心中的模型是："内存里有一些字节，我用什么类型的指针去看，它就是什么类型的对象。"这**不是** C++ 的模型。在 C++ 抽象机里，对象是一个**由特定构造创建出来的实体**：它有确定的类型、确定的存储、确定的生命周期；字节只是对象的"载体"。指针指向的是**对象**，而不仅仅是一个地址。

这个模型带来的直接后果是：

- 光有正确大小、正确对齐、内容"看起来对"的字节，**不等于**那里有一个对象。在没有对象的地方读写，是未定义行为。
- 因此 C++ 需要一套规则来说明"哪些操作会创建对象"——本节 ¶1 是总纲，¶13–¶16 的**隐式对象创建**（implicit object creation）则是 C++20 为了让大量"C 风格"代码合法化而补上的关键一块。

阅读本页之前最好了解：[[basic.types]]（对象表示、隐式生存期类型）、[[basic.lval]]（glvalue/prvalue）。阅读之后请接着读 [[basic.life]]。

## 对象如何被创建（¶1）

!!! std
    An *object* is created by a definition, by a *new-expression*, by an operation that implicitly creates objects (see below), when implicitly changing the active member of a union, or when a temporary object is created.

    对象由以下五种方式创建：定义；*new-expression*；隐式创建对象的操作；隐式改变联合体的活跃成员；创建临时对象。

这是一份**封闭清单**。没有列在这里的方式不会创建对象。逐条看：

| # | 方式 | 例子 | 详见 |
|---|---|---|---|
| 1 | **定义**（definition） | `int x;`、`static S s;` | [[basic.def]] |
| 2 | ***new-expression*** | `new T`、`::new (p) T(args)` | [[expr.new]] |
| 3 | **隐式创建对象的操作** | `std::malloc`、`std::memcpy`、`operator new` 调用、`unsigned char` 数组生命周期开始、`std::start_lifetime_as`… | 本页 ¶13–¶16 |
| 4 | **隐式改变联合体活跃成员** | `u.k = 4;` 让 `u.k` 成为活跃成员 | [[class.union]] |
| 5 | **临时对象** | `f(T{})` 中物化出来的 `T` | [[conv.rval]]、[[class.temporary]] |

注意几件**不在**清单里的事：

- `reinterpret_cast<T*>(p)` **不创建对象**。它只是换了一个指针类型，指针的值（指向哪个对象）一般不变（[[expr.reinterpret.cast]]、[[expr.static.cast]]）。
- 声明（非定义）如 `extern int x;` 不创建对象。
- 函数不是对象，即使它的代码占据存储（注 1）。

¶1 后半段列出对象的基本属性：对象在**构造期间、生命周期内、析构期间**占据一段存储（构造/析构期间的特殊规则见 [[class.cdtor]]）；对象的属性在**创建时确定**；对象可以有名字（[[basic.pre]]）、有存储期（[[basic.stc]]）、有类型（[[basic.types]]）。注 2 说多态对象带有实现生成的运行时类型信息——这就是 vptr 的标准说法，它让 `typeid` 和 `dynamic_cast` 能工作。

"属性在创建时确定"这句话分量很重：一个对象的**类型**一旦确定就不会变。你不能把一个 `int` 对象"变成" `float` 对象；你能做的只是**结束**旧对象的生命周期，在同一块存储上**创建**一个新的 `float` 对象（[[basic.life]]）。

```cpp run title="creation.cpp" ok
#include <new>
#include <cstdlib>

union U { int i; float f; };
struct P { int x, y; };

int g;                                   // 1. 定义创建对象（静态存储期）

int main() {
    int* p = new int(42);                // 2. new-expression
    delete p;

    P* q = static_cast<P*>(std::malloc(sizeof(P)));   // 3. malloc 隐式创建 P（见 ¶13）
    q->x = 1;
    std::free(q);

    U u{};                               // u.i 是活跃成员
    u.f = 1.0f;                          // 4. 赋值隐式切换活跃成员，创建 float 对象

    int n = P{1, 2}.x;                   // 5. P{1,2} 物化为临时对象
    (void)n;
}
```

## 子对象与完整对象（¶2）

对象可以包含别的对象，称为**子对象**（subobject）。子对象只有三种：

- **成员子对象**（member subobject）：非静态数据成员（[[class.mem]]）；
- **基类子对象**（base class subobject）（[[class.derived]]）；
- **数组元素**。

不是任何对象的子对象的对象，叫**完整对象**（complete object）。

!!! note "被“提供存储”的对象不是子对象"
    在一个 `unsigned char` 数组里用 placement new 创建的对象**不是**该数组的子对象——它是一个完整对象，只是被"嵌套"在数组里（¶3–¶4）。子对象关系只来自类成员、基类和数组元素这三种语法结构。

### 在子对象的存储里重新创建对象

¶2 后半段处理一个微妙的问题：如果我在一个成员子对象的位置上 placement new 一个新对象，这个新对象是谁的子对象？还是一个独立的完整对象？

标准说：设 *e* 是一个子对象（不论它此刻是否在生命周期内），在 *e* 的存储中创建了一个新对象，那么当以下四个条件**全部**满足时，新对象成为 *e* 所在对象的子对象：

- ¶2.1 *e* 的外层对象（containing object）的生命周期已开始且未结束；
- ¶2.2 新对象的存储**恰好覆盖**（exactly overlays）*e* 的存储位置；
- ¶2.3 *e* 不是**潜在重叠子对象**（potentially-overlapping subobject，见 ¶7）；
- ¶2.4 新对象与 *e* 类型相同（忽略 cv 限定）。

此时 *e* 与新对象称为**对应的直接子对象**（corresponding direct subobjects）。这个术语在 [[basic.life#9]] 中被用来定义"透明可替换"：只有这样，原来的名字 `a.x` 才能自动指向新对象。

```cpp run title="subobject-replace.cpp" ok
#include <memory>
#include <new>

struct A { int x; int y; };

int main() {
    A a{1, 2};
    std::destroy_at(&a.x);     // 伪析构：结束 a.x 的生命周期（C++20 起对标量也如此）
    ::new (&a.x) int(3);       // 满足 ¶2.1–¶2.4：新 int 是 a 的子对象，与旧 a.x 是对应的直接子对象
    return a.x;                // OK: a.x 透明地指向新对象，值为 3
}
```

为什么要求 ¶2.3（不是潜在重叠子对象）？因为基类子对象和 `[[no_unique_address]]` 成员的"存储位置"可能与别的子对象重叠或者大小为零，"恰好覆盖"在那里不是一个可靠的判断依据，而且尾部填充可能被别的成员复用。在这种子对象上 placement new 一个完整类型的对象，可能会覆盖掉相邻成员（因为完整对象的 `sizeof` 包括尾部填充，而潜在重叠子对象的尾部填充可能已经被别人占用），所以标准不承认它是替换。

## 提供存储（¶3）

¶3 定义了一个特权：**`unsigned char` 数组和 `std::byte` 数组可以为其他对象"提供存储"**（provides storage）。

!!! std
    If a complete object is created in storage associated with another object *e* of type "array of N unsigned char" or of type "array of N std::byte", that array *provides storage* for the created object if…

    如果在一个 `unsigned char[N]` 或 `std::byte[N]` 对象 *e* 的存储中创建了一个完整对象，并满足下列条件，则称该数组为新对象提供存储。

条件：

- ¶3.1 *e* 的生命周期已开始且未结束；
- ¶3.2 新对象的存储**完全落在** *e* 之内；
- ¶3.3 *e* 内没有满足这些条件的、**更内层**的数组对象（即"提供存储"的是最内层的那个字节数组）。

为什么需要这个概念？因为**存储复用会结束原对象的生命周期**（[[basic.life#2]] 第 2.5 项）。如果没有这条特权，在 `unsigned char buf[16]` 里 placement new 一个 `int`，就会结束 `buf` 的生命周期——buf 是一个局部变量，作用域结束时它还会被"销毁"，而且对它的后续访问都变成 UB。有了"提供存储"，新对象被视为**嵌套于**（nested within）`buf` 之中（¶4），而 [[basic.life#2]] 明确说：被**嵌套于** *o* 之内的对象复用存储，不结束 *o* 的生命周期。于是：

- `buf` 依然活着；
- 新对象在 `buf` 里活着；
- 若同一位置再创建另一个对象，只有前一个**被嵌套的**对象生命周期结束（注 3）。

这正是 `std::optional`、`std::variant`、各种 small-buffer optimization 和内存池的实现基础。只有 `unsigned char` 和 `std::byte` 享有这一特权——`char` 数组**不行**，`signed char` 数组也不行。

```cpp run title="provides-storage.cpp" ok
#include <new>
#include <cstddef>

template<class T, class U>
struct AlignedUnion {
    alignas(T) alignas(U) unsigned char data[sizeof(T) > sizeof(U) ? sizeof(T) : sizeof(U)];
};

int f() {
    AlignedUnion<int, char> au;
    int*  p = ::new (au.data) int;        // OK: au.data 为 *p 提供存储
    char* c = ::new (au.data) char();     // OK: 复用存储，结束 *p 的生命周期；au.data 仍然活着
    char* d = ::new (au.data + 1) char();
    return *c + *d;                       // OK
}

struct A { unsigned char a[32]; };
struct B { unsigned char b[16]; };
alignas(int) A a;
B*   b = ::new (a.a + 8) B;               // a.a 为 *b 提供存储
int* p = ::new (b->b + 4) int;            // b->b 为 *p 提供存储（¶3.3：最内层数组）
                                          // a.a 不直接为 *p 提供存储，但 *p 嵌套于 a 之内

int main() { return f(); }
```

!!! pitfall "`char` 数组不能提供存储"
    ```cpp
    alignas(int) char buf[sizeof(int)];
    int* p = ::new (buf) int(1);
    ```
    这里 `int` 的创建**复用**了 `buf` 的存储，按 [[basic.life#2]] 它会结束 `buf`（及其元素）的生命周期。之后只要不再把 `buf` 当作 `char` 数组访问，程序未必有 UB，但它与"提供存储"的语义完全不同。写缓冲区时请一律用 `unsigned char` 或 `std::byte`。（自动存储期的 `char` 数组是平凡析构的，所以 [[basic.life#11]] 的"作用域退出时类型不对"规则不会触发。）

## 嵌套于（¶4）与完整对象（¶5）

¶4 定义**嵌套于**（nested within）：*a* 嵌套于 *b*，当且仅当

- ¶4.1 *a* 是 *b* 的子对象；或
- ¶4.2 *b* 为 *a* 提供存储；或
- ¶4.3 存在 *c*，使 *a* 嵌套于 *c*、*c* 嵌套于 *b*（传递闭包）。

"嵌套于"是比"子对象"更宽的关系，它同时涵盖了类的结构性包含和字节数组的存储性包含。它被用于：

- [[basic.life#2]]：被嵌套对象复用存储不结束外层对象的生命周期；
- ¶10：嵌套关系中的两个对象可以有相同地址；
- [[basic.compound]] 中"经由指针可达"（reachable through）的定义间接用到它；
- `std::launder` 的前置条件。

¶5 定义**某对象的完整对象**（complete object of *x*）：完整对象的完整对象是它自己；否则沿着"包含它的唯一对象"一路向上，直到完整对象。注意这里只沿**子对象**关系向上，不沿"提供存储"关系向上——在 `unsigned char` 数组里 placement new 出来的对象，它自己就是完整对象。

```cpp title="nested.cpp" ok
struct Inner { int v; };
struct Outer { Inner in; unsigned char buf[8]; };

Outer o;
// o.in.v 是 o.in 的子对象，o.in 是 o 的子对象 ⇒ o.in.v 嵌套于 o，o.in.v 的完整对象是 o
// 在 o.buf 中 placement new 的 int：o.buf 为其提供存储 ⇒ 嵌套于 o.buf 和 o，
// 但它自己是完整对象（它的完整对象就是它自己）
```

## 最派生类与最派生对象（¶6）

如果一个完整对象、成员子对象或数组元素是类类型，它的类型叫**最派生类**（most derived class）——用以与基类子对象的类型区分。最派生类类型的对象，以及非类类型的对象，叫**最派生对象**（most derived object）。

换句话说，**基类子对象是唯一不是最派生对象的对象**。这个概念贯穿整个标准：

- 对象的**动态类型**（dynamic type，[[defns.dynamic.type]]）是 glvalue 所指的最派生对象的类型；
- `dynamic_cast<void*>(p)` 返回指向最派生对象的指针（[[expr.dynamic.cast]]）；
- 虚基类由最派生类的构造函数初始化（[[class.base.init]]）；
- 只有最派生对象保证有完整对象的布局和大小，基类子对象可能更小（¶8，[[basic.align#2]]）。

## 潜在重叠子对象与对象大小（¶7–¶8）

¶7：**潜在重叠子对象**（potentially-overlapping subobject）是

- ¶7.1 基类子对象，或
- ¶7.2 声明了 `[[no_unique_address]]` 的非静态数据成员（[[dcl.attr.nouniqueaddr]]）{{c++20}}。

这类子对象的特点是：它们的存储可以与同一完整对象中的**其他子对象重叠**——尤其是可以占用**零字节**，或者把自己的尾部填充让给别的成员使用。

¶8 规定什么时候对象大小非零。一个对象**必定有非零大小**，如果它满足以下任一条件：

- ¶8.1 不是潜在重叠子对象；
- ¶8.2 不是类类型；
- ¶8.3 类类型有虚函数或虚基类（需要 vptr 之类的东西）；
- ¶8.4 有非零大小的子对象，或有非零长度的无名位域。

否则（即：一个潜在重叠的、类类型的、无虚、所有子对象都是零大小的子对象——通俗说就是"空类"类型的潜在重叠子对象）：

- 如果它是**标准布局类类型、无非静态数据成员**的**基类子对象**，它**保证**大小为零——这就是标准保证的**空基类优化**（EBO）；
- 其他情况（如 `[[no_unique_address]]` 成员）是否为零大小是**实现定义**的。

!!! std
    Unless it is a bit-field, an object with nonzero size shall occupy one or more bytes of storage, including every byte that is occupied in full or in part by any of its subobjects.

    除位域外，非零大小的对象占据一个或多个字节，包括其任何子对象（哪怕只是部分）占据的每个字节。

最后一句：平凡可复制或标准布局类型的对象必须占据**连续**字节。这保证了 `memcpy` 整个对象和 `offsetof` 有意义；反之，带虚基类的非标准布局对象理论上可以不连续（虚基类子对象在别处），尽管主流实现都是连续的。

```cpp run title="empty-base.cpp" impl
#include <cstdio>

struct Empty {};
struct D : Empty { int x; };                                   // Empty 基类子对象：标准保证零大小
struct M { [[no_unique_address]] Empty e; int x; };            // 零大小与否：实现定义
struct N { Empty e; int x; };                                  // 普通成员：必定非零大小

int main() {
    std::printf("%zu %zu %zu\n", sizeof(D), sizeof(M), sizeof(N));
    // Itanium ABI（GCC/Clang）通常输出：4 4 8
    // MSVC 忽略标准 [[no_unique_address]]（需写 [[msvc::no_unique_address]]），M 通常为 8
}
```

## 潜在非唯一对象（¶9）{{c++26}}

¶9 定义**潜在非唯一对象**（potentially non-unique object）：

- ¶9.1 字符串字面量对象（[[lex.string]]）；
- ¶9.2 初始化列表的**后备数组**（backing array，[[dcl.init.ref]]、[[dcl.init.list]]）；
- ¶9.3 数组类型的模板参数对象（由 `std::define_static_array` 等反射设施产生，[[meta.define.static]]）；
- ¶9.4 上述对象的子对象。

这些对象有一个共同点：它们的内容是编译期已知的常量，实现很想把相同内容的实例**合并**（就像字符串字面量合并一直以来那样）。¶10.4 允许两个潜在非唯一对象有相同地址。在 C++23 及以前，只有字符串字面量享有"可能不唯一"的待遇（以另一种措辞表述）；`std::initializer_list` 的后备数组被视为普通临时数组，每次求值都得是不同的对象，实现不能把它放进只读数据段共享。C++26 把后备数组也纳入这一类，使 `{1, 2, 3}` 这种常量初始化列表可以像字符串字面量一样静态存储、共享。

## 对象地址（¶10）

!!! std
    Unless an object is a bit-field or a subobject of zero size, the address of that object is the address of the first byte it occupies.

    除位域和零大小子对象外，对象的地址就是它占据的第一个字节的地址。

关键规则：**生命周期重叠的两个非位域对象，必须有不同的地址、占据不相交的字节**——除非属于以下四种例外之一：

| 例外 | 含义 | 典型例子 |
|---|---|---|
| ¶10.1 一个嵌套于另一个 | 外层对象与其首成员、字节数组与其中 placement new 出的对象 | `struct S { int x; } s;` 中 `&s` 与 `&s.x` 地址相同 |
| ¶10.2 都嵌套于完整对象 *o*，恰好一个是 *o* 的子对象且大小为零 | 零大小的子对象可以与"借住"在同一完整对象里的其他对象同址 | 空基类与在 *o* 的字节数组中创建的对象 |
| ¶10.3 都是同一完整对象的子对象，至少一个大小为零，且类型**不相似** | EBO：空基类与第一个成员同址；`[[no_unique_address]]` 空成员与相邻成员同址 | `struct D : Empty { int x; }` 中 `Empty` 基类与 `x` 同址 |
| ¶10.4 都是潜在非唯一对象 | 字符串字面量、初始化列表后备数组可以合并 | `"x" == "x"` 结果未指定 |

¶10.3 的"不相似类型"（[[conv.qual]]）限制是关键：**两个同类型的子对象永远不同址**。这是为了保证"同类型的不同对象地址不同"这一不变式——很多代码（例如以 `this` 判断自赋值）依赖它。

```cpp run title="no-unique-address.cpp" ok
struct E {};

struct T {
    [[no_unique_address]] E a;
    [[no_unique_address]] E b;   // 与 a 类型相同 ⇒ 不能同址
    int x;
};

struct S : E {
    E e;                         // 普通成员，与基类 E 类型相同 ⇒ 不能同址
};

int main() {
    T t;
    S s;
    bool b1 = &t.a != &t.b;                                    // 必为 true
    bool b2 = static_cast<E*>(&s) != &s.e;                     // 必为 true
    // (void*)&t.a == (void*)&t.x 的结果：未指定（取决于实现是否把 a 放在零大小位置上）
    return (b1 && b2) ? 0 : 1;
}
```

标准例 2 关于常量和字符串字面量（改编并加注）：

```cpp run title="address-identity.cpp" ok
#include <initializer_list>

static const char test1 = 'x';
static const char test2 = 'x';
const bool b = &test1 != &test2;        // 恒为 true：两个普通对象，生命周期重叠，必须不同址

static const char (&r)[2] = "x";
static const char* s = "x";
static std::initializer_list<char> il = {'x'};
const bool b2 = r != il.begin();        // 未指定：二者都是潜在非唯一对象（¶10.4）
const bool b3 = r != s;                 // 未指定：两个字符串字面量对象可能合并
const bool b4 = il.begin() != &test1;   // 恒为 true：test1 不是潜在非唯一对象
const bool b5 = r != &test1;            // 恒为 true

int main() {}
```

¶10 最后一句：零大小子对象的地址是其完整对象占据的**某个未指定字节**的地址。也就是说零大小子对象仍然有地址（可以取 `&`），只是不能指望它与谁同址或不同址（除了 ¶10.3 的同类型限制）。

## 联合体元素子对象与组成值（¶11–¶12）{{c++26}}

这两段是为**常量求值**服务的定义：

- ¶11 **联合体元素子对象**（union elemental subobject）：联合体的直接成员，或者本身是联合体元素子对象的数组的元素。**非活跃的**（inactive）联合体元素子对象是不在生命周期内的那些。
- ¶12 对象的**组成值**（constituent values）：标量对象是其值本身；否则是除非活跃联合体元素子对象之外所有直接子对象的组成值。**组成引用**（constituent references）类似：直接引用成员，加上子对象（同样跳过非活跃联合体元素）的组成引用。

[[expr.const]] 要求常量表达式的结果对象的组成值和组成引用都满足一定条件（例如不能是不确定值、错误值，不能指向临时对象）。"跳过非活跃联合体元素"让 `constexpr` 联合体只需要它的活跃部分被初始化；而联合体**数组成员**中只有部分元素活着时（借助 C++26 新增的 `std::start_lifetime`，[[obj.lifetime]]），只检查活着的元素。

```cpp
struct A {
    struct X { int i; int j; };
    struct Y { X x1; X x2; };
    union { int i; int arr[4]; Y y; };
};

constexpr A v1;          // OK: 没有活跃成员，没有组成值
constexpr A v2{.i = 1};  // OK: 组成值为 {v2.i}
constexpr A v4 = [] {
    A a;
    a.y.x1.i = 1;        // 隐式切换活跃成员为 y（[class.union]）
    a.y.x2.j = 2;
    return a;
}();                     // error: 组成值包含未初始化的 v4.y.x1.j 和 v4.y.x2.i（它们有错误值）
```

（标准例 3 中还有一个用 `std::start_lifetime(a.arr)` 让数组成为活跃成员、只初始化 `arr[1]` 和 `arr[2]` 的例子；截至写作时本机 libc++ 尚未提供 `std::start_lifetime`，故未附可运行版本。上面的代码块不加判定，原因值得一说：标准例子标注 `v1` 为 OK、`v4` 为 error。Clang 23 对 `v4` 的诊断与之一致，但它还拒绝 `v1`，理由是 const 对象的默认初始化要求类型是 const-default-constructible。查 [[dcl.init.general#7]]：匿名联合体成员的类型须是 const-default-constructible，而联合体须"恰有一个变体成员带默认成员初始化器"——`A` 的匿名联合体不满足。也就是说，**按规范性文字，Clang 拒绝 `v1` 是对的**，标准例子（例子不具规范效力）在这一点上与 [dcl.init] 不一致，可能是草案的疏漏。）

## 隐式对象创建（¶13–¶16）{{c++20}}

这是本页最重要的部分，也是 C++20 对对象模型最深刻的修补（[[P0593R6]]，并作为对之前标准的缺陷修复）。

### 问题：C 风格代码在 C++17 中是 UB

```cpp
struct X { int a, b; };
X* make_x() {
    X* p = (X*)std::malloc(sizeof(X));
    p->a = 1;      // C++17：UB！malloc 不创建对象，p 不指向任何 X
    p->b = 2;
    return p;
}
```

按 C++17 的 ¶1，对象只能由定义、*new-expression*、联合体成员切换和临时对象创建。`malloc` 不在其中，所以 `p` 指向的存储里**没有** `X` 对象，`p->a` 是访问一个不存在的对象的成员——UB。同理，用 `memcpy` 把字节拷进一块原始缓冲区再当 `struct` 用、`mmap` 文件再当结构体用、自己写的内存池里用 `reinterpret_cast`……全都是 UB。这与几十年的实践严重冲突，而且连 `std::vector` 的典型实现（`allocator::allocate` 后对元素做指针算术）都是 UB——因为那里没有**数组**对象。

### 解法：在需要时，对象"自动"出现

¶13 的规则：

!!! std
    For each operation that is specified as implicitly creating objects, that operation implicitly creates and starts the lifetime of zero or more objects of implicit-lifetime types in its specified region of storage if doing so would result in the program having defined behavior.

    每个被规定为"隐式创建对象"的操作，会在其指定的存储区域中隐式创建零个或多个**隐式生存期类型**的对象并开始其生命周期——只要这样做能让程序具有定义行为。

几个要点：

1. **只针对隐式生存期类型**（implicit-lifetime types，[[basic.types.general]]）：标量类型、隐式生存期类类型、数组类型及其 cv 版本。隐式生存期类（[[class.prop]]）是：析构函数非用户提供的聚合类，或者至少有一个平凡的合格构造函数且析构函数平凡、未删除的类。`std::string` 不是，`struct { int a, b; }` 是，任何数组类型都是（即使元素类型不是——但注 4 说，元素/子对象本身若不是隐式生存期类型，其生命周期不会被开始）。
2. **"如果这样做能让程序有定义行为"**：这是一种"天使般的非确定性"（angelic nondeterminism）——抽象机在执行到 `malloc` 时，"预见"到程序后面会怎样使用这块存储，并恰好创建出能让那些使用合法的对象集合。这个选择可以依赖**之后**发生的事。
3. 如果**不存在**任何对象集合能让程序有定义行为，则程序有 UB；如果**有多个**，则创建哪一个**未指定**。
4. 创建的对象可以是零个——如果程序根本不使用这块内存。

¶14 补充：有些操作还被规定为**产生一个指向"合适的已创建对象"的指针**（a pointer to a *suitable created object*）：从隐式创建的、地址恰好在区域起始处的对象中选一个，返回指向它的指针，同样以"能让程序有定义行为"为准则。这一步解决的是"`malloc` 返回的 `void*` 指向谁"：它指向那个被隐式创建的 `X`，于是 `(X*)p` 得到的确实是指向 `X` 对象的指针。

```cpp run title="malloc-x.cpp" ok
#include <cstdlib>

struct X { int a, b; };

X* make_x() {
    // malloc 隐式创建一个 X 对象（及其子对象 a、b），
    // 并返回指向该 X 的指针——因为只有这样后面的成员访问才有定义行为
    X* p = static_cast<X*>(std::malloc(sizeof(X)));
    p->a = 1;
    p->b = 2;
    return p;
}

int main() {
    X* p = make_x();
    int r = p->a + p->b;
    std::free(p);
    return r == 3 ? 0 : 1;
}
```

```cpp run title="no-valid-set.cpp" ub
#include <cstdlib>

int main() {
    void* p = std::malloc(sizeof(int));
    *static_cast<int*>(p) = 1;
    float f = *static_cast<float*>(p);   // UB: 同一地址不可能同时有 int 和 float 对象；
                                         // 不存在任何能让两次访问都有定义的对象集合
    std::free(p);
    return static_cast<int>(f);
}
```

### 哪些操作隐式创建对象

¶16 规定了语言层面的两类：

- **`unsigned char` 或 `std::byte` 数组的生命周期开始**时，会在数组占据的存储中隐式创建对象（数组为这些对象提供存储，注 5）。
- 对名为 `operator new` 或 `operator new[]` 的函数的**任何显式或隐式调用**，在返回的存储中隐式创建对象，并返回指向合适的已创建对象的指针。

两者都有"常量求值期间除外"的限定——常量求值器要精确追踪每个对象，不允许"天使般"的猜测。

注 6 列出标准库中隐式创建对象的函数：

| 函数 | 条款 | 说明 |
|---|---|---|
| `std::malloc`、`calloc`、`realloc`、`aligned_alloc` | [[c.malloc]] | 在返回的存储中隐式创建，返回指向合适的已创建对象的指针 |
| `std::memcpy`、`std::memmove` | [[cstring.syn]] | 复制**之前**在目标区域隐式创建对象 |
| `std::bit_cast` | [[bit.cast]] | 结果中的隐式生存期子对象 |
| `std::allocator<T>::allocate` | [[allocator.members]] | 创建 `T[n]` 数组对象，但**不**开始元素的生命周期 |
| `std::pmr::memory_resource::allocate` | [[mem.res.public]] | 同 `operator new` |
| `std::start_lifetime_as`、`start_lifetime_as_array` {{c++23}} | [[obj.lifetime]] | 在**已有内容**的存储上创建对象并保留字节 |

### 字节缓冲区 + `reinterpret_cast` 的陷阱

`unsigned char` 数组开始生命周期时会隐式创建对象，但**`reinterpret_cast` 不会给你一个指向它的指针**：

```cpp run title="buffer-launder.cpp" ok
#include <new>

struct P { int x, y; };

int main() {
    alignas(P) unsigned char buf[sizeof(P)];   // buf 的生命周期开始 ⇒ 隐式创建对象（如一个 P）

    // P* bad = reinterpret_cast<P*>(buf);
    // bad->x = 1;   // UB（按标准）：bad 的值仍然指向 buf[0]（一个 unsigned char），
    //               // 而不是指向隐式创建的 P —— P 与 unsigned char 数组不可指针互转

    P* p = std::launder(reinterpret_cast<P*>(buf));  // OK: launder 返回指向位于该地址的 P 的指针
    p->x = 1;
    p->y = 2;
    return p->x + p->y == 3 ? 0 : 1;
}
```

!!! lawyer "为什么 malloc 不需要 launder，而 buf 需要？"
    因为 ¶14 只对**特定操作**（`operator new`、`malloc` 等）承诺"返回指向合适的已创建对象的指针"。`unsigned char` 数组的生命周期开始虽然隐式创建了对象，但没有任何"返回值"可言；你手里的指针是从 `buf` 退化而来的，指向 `buf[0]`。`reinterpret_cast`（等价于经由 `void*` 的两次 `static_cast`）只有在源与目标对象**指针可互转**（[[basic.compound]]）时才改变指向；`unsigned char` 数组与 `P` 不是可互转的，所以指针值不变。要拿到指向 `P` 的指针，就需要 `std::launder`（[[ptr.launder]]）。
    
    实践中所有主流编译器对省略 `launder` 的版本都生成"预期"的代码，但这属于"碰巧能用"，不是标准保证。

### `std::start_lifetime_as`：保留字节的对象创建 {{c++23}}

`memcpy` 会隐式创建对象，但前提是你要**拷贝**一遍字节。如果字节已经在那里了（从网络收到、`mmap` 进来、DMA 写入），怎么在**不拷贝**的情况下把它们"认作"一个对象？

在 C++20 中，唯一的办法是 `std::memmove(p, p, n)`（自己拷给自己）——它隐式创建对象并保留内容，编译器通常能把它优化掉。C++23 引入 `std::start_lifetime_as<T>(p)`（[[P2590R2]]，[[obj.lifetime]]）把这个惯用法变成一个有名字的函数：它在 `p` 处隐式创建一个 `T` 对象（及嵌套对象），对象表示就是调用前存储的内容，并返回指向它的指针。

```cpp title="start-lifetime-as.cpp" ok
#include <memory>
#include <cstddef>
#include <cstdint>

struct Header { std::uint32_t magic; std::uint32_t length; };

const Header* parse(const std::byte* packet) {
    // 前置条件：packet 处有 sizeof(Header) 字节已分配存储，且对齐满足 Header
    return std::start_lifetime_as<Header>(packet);   // 不拷贝，字节即对象表示
}
```

（截至写作时，本机 Clang 23 + libc++ 尚未提供 `std::start_lifetime_as`，此例未在本地编译验证。C++20 的替代写法是 `std::launder(static_cast<Header*>(std::memmove(p, p, sizeof(Header))))`。）

### 与 C 的"有效类型"模型对比

C 语言没有"对象被创建"的概念，它用**有效类型**（effective type，C17 6.5p6）来处理同样的问题：

| | C（有效类型） | C++（对象模型 + 隐式创建） |
|---|---|---|
| 声明的对象 | 有效类型 = 声明类型 | 定义创建对象，类型 = 声明类型 |
| `malloc` 的存储 | 没有声明类型；**第一次**以非字符类型左值写入时，有效类型变为该类型 | `malloc` 当时就隐式创建了"恰好合适"的对象 |
| `memcpy` 到 `malloc` 存储 | 目标的有效类型变为源的有效类型 | `memcpy` 在目标中隐式创建对象 |
| 改变类型 | 对 `malloc` 存储，用另一类型写入即可改变有效类型 | 必须创建新对象（placement new / 再次隐式创建），旧对象生命周期结束 |
| 类型的"粘性" | 每次写都可能改变 | 对象类型终身不变 |
| 非平凡类型 | 不存在 | 必须用 new-expression 显式构造 |

两者在"平凡数据"上的结论大体一致（`malloc` + 成员赋值在两种语言中都合法），但概念基础不同：C 是"写入定义类型"，C++ 是"对象先存在，然后被写入"。这一差别在 C++ 里表现为：**指针的值**（指向哪个对象）是有意义的，因此出现了 `std::launder` 这种 C 里没有的东西。

## 实现视角

!!! impl "编译器怎么看对象模型"
    - 对象模型在生成的机器码里几乎"看不见"——它的作用是**约束程序员**，从而**授权优化器**。例如别名分析（TBAA，基于类型的别名分析）依赖"一个 `int*` 和一个 `float*` 不会指向同一个对象"，这正是 ¶13 中"不存在合法的对象集合 ⇒ UB"那一类规则的落地。
    - 隐式对象创建对编译器几乎没有代码生成成本：`malloc`、`memcpy` 本来就被当作"可能写入任意类型"的操作处理。P0593 的作者明确把它定位为"给现有实践补上标准依据"。
    - `std::launder` 在 GCC/Clang 中实现为内建函数（`__builtin_launder`），作用是阻止优化器根据"该指针指向的对象未变"做的推断（尤其是 `const` 成员和 vptr 的值的缓存/去虚化）。
    - Itanium ABI 下，空基类在没有冲突时放在偏移 0，与第一个成员同址；当第一个成员是同类型的空类时，基类会被挪开以满足 ¶10.3。`[[no_unique_address]]` 在 GCC/Clang 上实现了零大小和尾部填充复用；MSVC 为了 ABI 稳定，对标准属性不做任何事，需要使用 `[[msvc::no_unique_address]]`。

## 历史与演进

!!! history "历史与演进"
    - **C++98/03**：对象被定义为"一段存储区域"（an object is a region of storage）。这个定义让"有存储就有对象"的理解看起来成立，留下大量歧义。
    - **C++11**：加入内存模型；对象定义基本未变。
    - **C++17**：[[P0137R1]] 重写对象模型——对象由列明的构造**创建**，引入"提供存储"、"嵌套于"、指针值"指向对象"的概念，并引入 `std::launder`。副作用是把 `malloc` + 赋值之类的 C 风格代码明确变成了 UB。
    - **C++20**：[[P0593R6]] 引入隐式对象创建和隐式生存期类型，修复上述问题（并作为对之前标准的缺陷修复）。同时 `[[no_unique_address]]` 引入"潜在重叠子对象"。
    - **C++23**：[[P2590R2]] 加入 `std::start_lifetime_as` / `start_lifetime_as_array`。
    - **C++26**：引入"潜在非唯一对象"（初始化列表后备数组可以合并、静态存储）、组成值/组成引用（服务于常量求值）、联合体元素子对象、`std::start_lifetime`；¶2 的子对象替换条件加入"非潜在重叠"并命名为"对应的直接子对象"。

## 陷阱

!!! pitfall "把 `reinterpret_cast` 当成“创建对象”"
    `reinterpret_cast<T*>(p)` 只改变指针类型。若 `p` 处没有 `T` 对象（或有，但 `p` 的值不指向它），通过结果访问就是 UB。正确做法：用 placement new 创建对象；或依赖隐式对象创建 + `std::launder`；或 C++23 的 `std::start_lifetime_as`；或干脆 `std::memcpy`/`std::bit_cast` 到一个局部变量。

!!! pitfall "以为隐式对象创建对所有类型有效"
    只对隐式生存期类型。`std::string* s = (std::string*)malloc(sizeof(std::string)); *s = "x";` 仍是 UB——`std::string` 有非平凡的构造和析构，不是隐式生存期类型，`malloc` 不会为它创建对象。必须 `::new (raw) std::string`。

!!! pitfall "以为同类型的两个空成员可以同址"
    ¶10.3 要求"不相似类型"。两个 `[[no_unique_address]] Empty` 成员不能同址，因此至少一个会占用实际字节。这常常让试图用多个同类型空成员（如多个 `std::allocator`）压缩大小的代码失望。

## 思考题

!!! question "思考题 1"
    下面的程序有定义行为吗？如果有，`malloc` 隐式创建了什么对象？

    ```cpp
    #include <cstdlib>
    int main() {
        int* p = static_cast<int*>(std::malloc(4 * sizeof(int)));
        for (int i = 0; i < 4; ++i) p[i] = i;
        int s = p[0] + p[3];
        std::free(p);
        return s;
    }
    ```

<details markdown="1">
<summary>答案</summary>

有定义行为。`p[i]` 是指针算术，[[expr.add]] 要求 `p` 指向一个**数组**的元素才能做 `p + i`（`i > 1` 时）。所以 `malloc` 必须隐式创建一个 `int[4]` 数组对象（数组类型是隐式生存期类型），以及其中的 `int` 元素（`int` 也是隐式生存期类型，注 4 不排除它们），并返回指向**数组首元素**的指针——这个指针值也是由 ¶14 的"合适的已创建对象"规则选择的（指向数组的指针与指向首元素的指针不可互转，但 `static_cast<int*>` 后的值要求它指向一个 `int`，所以"合适"的那个是首元素）。这正是 P0593 让 `std::vector` 风格代码合法化的机制。
</details>

!!! question "思考题 2"
    `struct A { unsigned char buf[8]; } a;` 在 `a.buf` 中 placement new 一个 `int`。之后 `a` 的生命周期结束了吗？如果换成 `struct B { char buf[8]; } b;` 呢？

<details markdown="1">
<summary>答案</summary>

`A`：没有。`a.buf` 为 `int` 提供存储（¶3），`int` 嵌套于 `a.buf` 进而嵌套于 `a`（¶4），[[basic.life#2]] 第 2.5 项 说"被不嵌套于 *o* 的对象复用"才结束 *o* 的生命周期，所以 `a` 和 `a.buf` 都还活着。

`B`：`char` 数组不能提供存储，新 `int` 不嵌套于 `b` 或 `b.buf`。它复用了 `b.buf` 中 4 个 `char` 元素的存储，按 [[basic.life#2]] 第 2.5 项结束了这些元素的生命周期；由于它也复用了 `b` 的一部分存储，**`b` 本身的生命周期也结束**。之后若再以 `b` 或 `b.buf` 访问，就会落入 [[basic.life#8]] 的 UB 清单。
</details>

!!! question "思考题 3"
    为什么 ¶10.3 要求零大小子对象与另一个子对象"类型不相似"才能同址？举出违反后会坏掉的代码。

<details markdown="1">
<summary>答案</summary>

很多代码假设"同类型的两个不同对象地址一定不同"，例如以 `this == &other` 判定自赋值、以地址作为对象身份放进 `std::set<const T*>`。若允许 `struct S { [[no_unique_address]] E a, b; }` 中 `&s.a == &s.b`，那么 `s.a = s.b` 会被误判为自赋值，以地址为键的容器会把两个对象当成一个。限制为"不相似类型"后，零大小优化只发生在不同类型之间，同类型对象的地址身份得以保留。
</details>

## 小结

| 概念 | 一句话 |
|---|---|
| 对象创建（¶1） | 五种方式：定义、new、隐式创建、联合体成员切换、临时对象。`reinterpret_cast` 不在其中 |
| 子对象（¶2） | 成员、基类、数组元素；在子对象存储上重建同类型对象可成为"对应的直接子对象" |
| 提供存储（¶3） | 仅 `unsigned char[N]` / `std::byte[N]`；不结束数组的生命周期 |
| 嵌套于（¶4） | 子对象关系 ∪ 提供存储关系，取传递闭包 |
| 最派生对象（¶6） | 除基类子对象外的所有对象；动态类型的基础 |
| 潜在重叠（¶7–¶8） | 基类、`[[no_unique_address]]`；空基类在标准布局下保证零大小 |
| 地址（¶10） | 生命周期重叠的对象地址不同，四种例外；同类型子对象永不同址 |
| 隐式创建（¶13–¶16） | 只创建隐式生存期类型；"能让程序有定义就创建"；`malloc`/`memcpy`/`operator new`/字节数组/`start_lifetime_as` |
