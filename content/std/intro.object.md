---
title: 对象模型
summary: 哪些构造会创建对象；子对象、完整对象与最派生对象；字节数组怎样为其他对象提供存储；对象的大小与地址何时可以重叠；malloc、memcpy 等操作怎样隐式创建对象。
status: done
papers: P0593R6, P2590R2, P0137R1, P2752R3
related: basic.life, basic.types, basic.lval, basic.compound, expr.new, class.union
tags: 对象模型, 隐式对象创建, UB, no_unique_address
updated: 2026-10-19
---

!!! tldr
    - 在 C++ 里，有字节不等于有对象。对象只能由定义、`new`、隐式创建对象的操作、切换联合体成员、创建临时对象这五种方式产生，`reinterpret_cast` 不在其中。
    - 只有 `unsigned char` 和 `std::byte` 数组能为在其中创建的对象提供存储，这样做不会结束数组本身的生命周期；`char` 数组不行。
    - 生命周期重叠的两个对象一般地址不同，例外是一个嵌套在另一个里、零大小的子对象，以及字符串字面量这类可以合并的对象。两个同类型的子对象永远不同址。
    - `malloc`、`memcpy`、`operator new`、字节数组的生命周期开始，会在需要时隐式创建隐式生存期类型的对象，让 C 风格的代码在 C++20 起有定义的行为。
    - 字节数组里隐式创建的对象，要用 `std::launder` 或 C++23 的 `std::start_lifetime_as` 才能拿到指向它的指针，单靠 `reinterpret_cast` 不够。

## 对象从哪里来（¶1）

很多从 C 转过来的程序员心里的模型是：内存里有一些字节，用什么类型的指针去看，它就是什么类型的对象。C++ 的模型不是这样。对象是由特定构造创建出来的实体，有确定的类型、存储和生命周期；字节只是承载对象的介质，指针指向的是对象，而不只是一个地址。

!!! std
    An *object* is created by a definition, by a *new-expression*, by an operation that implicitly creates objects (see below), when implicitly changing the active member of a union, or when a temporary object is created.

¶1 这是一份封闭的清单：

```cpp run title="creation.cpp" ok
#include <new>
#include <cstdlib>

union U { int i; float f; };
struct P { int x, y; };

int g;                                   // 1. 定义

int main() {
    int* p = new int(42);                // 2. new 表达式
    delete p;

    P* q = static_cast<P*>(std::malloc(sizeof(P)));   // 3. malloc 隐式创建 P（见下文 ¶13）
    q->x = 1;
    std::free(q);

    U u{};                               // u.i 是活跃成员
    u.f = 1.0f;                          // 4. 赋值切换活跃成员，创建 float 对象

    int n = P{1, 2}.x;                   // 5. P{1, 2} 物化为临时对象
    (void)n;
}
```

| 方式 | 例子 | 详见 |
|---|---|---|
| 定义 | `int x;`、`static S s;` | [[basic.def]] |
| new 表达式 | `new T`、`::new (p) T(args)` | [[expr.new]] |
| 隐式创建对象的操作 | `std::malloc`、`std::memcpy`、调用 `operator new`、字节数组的生命周期开始 | 下文 ¶13–¶16 |
| 隐式切换联合体的活跃成员 | `u.f = 1.0f;` | [[class.union]] |
| 创建临时对象 | `f(T{})` 里物化出来的 `T` | [[conv.rval]]、[[class.temporary]] |

不在清单里的操作不会创建对象。`reinterpret_cast<T*>(p)` 只改变指针的类型，指针指向哪个对象一般不变（[[expr.reinterpret.cast]]）。`extern int x;` 这样的非定义声明不创建对象。注 1 说明，函数不是对象，即使它的代码也占据存储。

¶1 后半段列出对象的基本属性。对象在构造期间、生命周期内和析构期间占据一段存储（构造和析构期间的特殊规则见 [[class.cdtor]]）。对象可以有名字（[[basic.pre]]），有存储期（[[basic.stc]]）和类型（[[basic.types]]）。注 2 说，实现为多态对象生成运行时类型信息，这就是 vptr 在标准里的说法，`typeid` 和 `dynamic_cast` 靠它工作。

对象的属性在创建时就确定了，类型以后不会改变。不能把一个 `int` 对象变成 `float` 对象，只能结束旧对象的生命周期，再在同一块存储上创建一个新的 `float` 对象（[[basic.life]]）。

## 子对象与完整对象（¶2、¶5–¶6）

¶2 对象可以包含别的对象，称为**子对象**（subobject）。子对象只有三种：成员子对象（非静态数据成员，[[class.mem]]）、基类子对象（[[class.derived]]）和数组元素。不是任何对象的子对象的对象叫**完整对象**（complete object）。

¶5 每个对象 x 都有一个**完整对象**：如果 x 本身是完整对象，就是它自己；否则是包含 x 的那个对象的完整对象。沿着子对象关系一直向上，就能找到它。

¶6 完整对象、成员子对象或数组元素如果是类类型，它的类型叫**最派生类**（most derived class），以区别于基类子对象的类型。最派生类类型的对象和非类类型的对象叫**最派生对象**（most derived object）。换句话说，只有基类子对象不是最派生对象。

最派生对象这个概念在别处经常用到：表达式的动态类型是它所指的最派生对象的类型（[[defns.dynamic.type]]）；`dynamic_cast<void*>(p)` 返回指向最派生对象的指针（[[expr.dynamic.cast]]）；虚基类由最派生类的构造函数初始化（[[class.base.init]]）。

### 在子对象的位置上重新创建对象

在成员 `a.x` 的位置上 placement new 一个新的 `int`，新对象是 `a` 的成员，还是一个独立的完整对象？

```cpp run title="subobject-replace.cpp" ok
#include <memory>
#include <new>

struct A { int x; int y; };

int main() {
    A a{1, 2};
    std::destroy_at(&a.x);     // 结束 a.x 的生命周期
    ::new (&a.x) int(3);       // 新的 int 成为 a 的子对象
    return a.x;                // OK：a.x 指的是新对象，值为 3
}
```

¶2 后半段规定，设 e 是一个子对象（此刻在不在生命周期内都可以），在 e 的存储里创建了一个新对象。如果下面四条都成立，新对象就是 e 所在对象的子对象：

- ¶2.1 包含 e 的对象在生命周期内；
- ¶2.2 新对象的存储恰好覆盖 e 的存储；
- ¶2.3 e 不是潜在重叠子对象（见下文 ¶7）；
- ¶2.4 新对象与 e 的类型相同（忽略 cv 限定）。

这时 e 与新对象称为**对应的直接子对象**（[[g:corresponding-direct-subobjects|corresponding direct subobjects]]）。[[basic.life#9]] 用这个概念定义透明替换：只有满足这些条件，原来的名字 `a.x` 才会自动指向新对象。

¶2.3 排除了基类子对象和 `[[no_unique_address]]` 成员。它们的存储可能与别的子对象重叠，尾部填充也可能已经被别的成员占用。在这样的位置上创建一个完整类型的对象，按完整对象的 `sizeof` 写入，可能覆盖相邻的成员，所以标准不把它当作替换。

## 字节数组提供存储（¶3–¶4）

如果在一个局部的字节数组里用 placement new 创建 `int`，会发生什么？按 [[basic.life#2]]，对象的存储被另一个对象复用时，它的生命周期结束。如果没有特别的规定，数组 `buf` 的生命周期就此结束，之后再访问它就有问题。

¶3 给了 `unsigned char` 数组和 `std::byte` 数组一项特权。在这样的数组 e 的存储里创建一个完整对象时，如果

- ¶3.1 e 在生命周期内，
- ¶3.2 新对象的存储完全落在 e 之内，
- ¶3.3 e 里面没有更内层的、也满足这些条件的数组，

就说 e 为新对象**提供存储**（[[g:provides-storage|provides storage]]）。

¶4 进一步定义**嵌套于**（[[g:nested-within|nested within]]）：a 嵌套于 b，是指 a 是 b 的子对象，或者 b 为 a 提供存储，或者经过若干步这样的关系相连（¶4.1–¶4.3）。

[[basic.life#2]] 规定，只有被不嵌套于 o 的对象复用存储时，o 的生命周期才结束。数组为新对象提供存储，新对象就嵌套于数组，于是：

- 数组仍在生命周期内；
- 新对象在数组里正常存在；
- 在同一位置再创建另一个对象，只结束前一个嵌套对象的生命周期（注 3）。

`std::optional`、`std::variant`、各种小缓冲区优化和内存池都以此为基础。下面是 ¶3 的例 1：

```cpp run title="provides-storage.cpp" ok
#include <new>

template<class T, class U>
struct AlignedUnion {
    alignas(T) alignas(U) unsigned char data[sizeof(T) > sizeof(U) ? sizeof(T) : sizeof(U)];
};

int f() {
    AlignedUnion<int, char> au;
    int*  p = ::new (au.data) int;        // OK：au.data 为 *p 提供存储
    char* c = ::new (au.data) char();     // OK：结束 *p 的生命周期，au.data 不受影响
    char* d = ::new (au.data + 1) char();
    (void)p;
    return *c + *d;                       // OK
}

struct A { unsigned char a[32]; };
struct B { unsigned char b[16]; };
alignas(int) A a;
B*   b = ::new (a.a + 8) B;               // a.a 为 *b 提供存储
int* p = ::new (b->b + 4) int;            // b->b 为 *p 提供存储（¶3.3：最内层的数组）
                                          // a.a 不直接为 *p 提供存储，但 *p 嵌套于 a

int main() { return f(); }
```

由数组提供存储的对象不是数组的子对象，它自己就是完整对象，只是嵌套于数组之中。¶5 找完整对象时只沿子对象关系向上，不沿提供存储的关系向上。

!!! pitfall "`char` 数组不能提供存储"
    ```cpp
    alignas(int) char buf[sizeof(int)];
    int* p = ::new (buf) int(1);
    ```
    只有 `unsigned char` 和 `std::byte` 数组享有这项特权，`char` 和 `signed char` 数组都没有。这里的 `int` 复用了 `buf` 的存储，又不嵌套于 `buf`，于是 `buf` 和它的元素的生命周期都结束了。只要之后不再把 `buf` 当作 `char` 数组使用，程序未必有 UB，但语义与提供存储完全不同。写缓冲区时应当一律用 `unsigned char` 或 `std::byte`。

## 对象的大小（¶7–¶8）

¶7 **潜在重叠子对象**（[[g:potentially-overlapping-subobject|potentially-overlapping subobject]]）有两种：基类子对象，以及声明了 `[[no_unique_address]]` 的非静态数据成员（[[dcl.attr.nouniqueaddr]]）。它们的存储可以与同一完整对象里的其他子对象重叠，特别是可以占零个字节，或者把自己的尾部填充让给别的成员。

¶8 满足下列任一条件的对象大小不为零：

- ¶8.1 不是潜在重叠子对象；
- ¶8.2 不是类类型；
- ¶8.3 是有虚函数或虚基类的类类型；
- ¶8.4 有大小不为零的子对象，或有宽度不为零的无名位域。

剩下的就是空类类型的潜在重叠子对象。如果它是一个没有非静态数据成员的标准布局类的基类子对象，大小保证为零，这就是标准保证的空基类优化（EBO）。其余情况，例如 `[[no_unique_address]]` 成员，是否为零大小由实现定义。

```cpp run title="empty-base.cpp" impl
#include <cstdio>

struct Empty {};
struct D : Empty { int x; };                                   // 基类子对象：保证零大小
struct M { [[no_unique_address]] Empty e; int x; };            // 是否零大小：实现定义
struct N { Empty e; int x; };                                  // 普通成员：大小不为零

int main() {
    std::printf("%zu %zu %zu\n", sizeof(D), sizeof(M), sizeof(N));
}
```

本机 Clang 23 输出 `4 4 8`。MSVC 忽略标准的 `[[no_unique_address]]`，要写 `[[msvc::no_unique_address]]`，那里的 `M` 通常是 8。

大小不为零的对象（位域除外）占据一个或多个字节，包括它的子对象全部或部分占据的每个字节。¶8 的最后一句要求，平凡可复制类型或标准布局类型的对象占据连续的字节，这是对整个对象做 `memcpy` 和使用 `offsetof` 的前提。

## 对象的地址（¶9–¶10）

!!! std
    Unless an object is a bit-field or a subobject of zero size, the address of that object is the address of the first byte it occupies.

¶10 两个生命周期重叠、都不是位域的对象，一般地址不同，占据的字节也不相交。例外只有四种：

| 例外 | 典型例子 |
|---|---|
| ¶10.1 一个嵌套于另一个 | `struct S { int x; } s;` 里 `&s` 与 `&s.x`；字节数组与其中创建的对象 |
| ¶10.2 都嵌套于完整对象 o，恰好一个是 o 的零大小子对象 | 空基类与在 o 的字节数组里创建的对象 |
| ¶10.3 是同一完整对象的子对象，至少一个大小为零，并且类型不相似 | 空基类与派生类的第一个成员；`[[no_unique_address]]` 空成员与相邻成员 |
| ¶10.4 都是潜在非唯一对象 | 两个内容相同的字符串字面量 |

¶10.3 要求类型不相似（[[conv.qual]]），所以两个同类型的子对象永远不同址。以 `this == &other` 判断自赋值、以地址作为对象身份，都依赖这一点。

```cpp run title="no-unique-address.cpp" ok
struct E {};

struct T {
    [[no_unique_address]] E a;
    [[no_unique_address]] E b;   // 与 a 类型相同，不能同址
    int x;
};

struct S : E {
    E e;                         // 与基类 E 类型相同，不能同址
};

int main() {
    T t;
    S s;
    bool b1 = &t.a != &t.b;                    // 必为 true
    bool b2 = static_cast<E*>(&s) != &s.e;     // 必为 true
    return (b1 && b2) ? 0 : 1;
}
```

`(void*)&t.a == (void*)&t.x` 的结果没有保证，本机 Clang 23 上为 true。零大小子对象的地址是其完整对象所占的某个未指定字节的地址（¶10 最后一句）。

### 潜在非唯一对象（¶9）

¶9 下面这些对象是**潜在非唯一对象**（[[g:potentially-non-unique-object|potentially non-unique object]]）：字符串字面量对象（[[lex.string]]）、初始化列表的后备数组（[[dcl.init.ref]]）、数组类型的模板参数对象（[[meta.define.static]]），以及它们的子对象。

它们的内容在编译期已知、不可修改，实现希望把内容相同的实例合并，就像一直以来合并字符串字面量那样。¶10.4 允许它们共享地址。把 `std::initializer_list` 的后备数组也纳入这一类，是 C++26 的 [[P2752R3]] 带来的：此前后备数组和普通临时数组一样，每次求值都得是不同的对象，`{1, 2, 3}` 不能放进只读数据段共享。

¶10 的例 2：

```cpp run title="address-identity.cpp" ok
#include <initializer_list>

static const char test1 = 'x';
static const char test2 = 'x';
const bool b = &test1 != &test2;        // 恒为 true：两个普通对象

static const char (&r)[2] = "x";
static const char* s = "x";
static std::initializer_list<char> il = {'x'};
const bool b2 = r != il.begin();        // 未指定：二者都是潜在非唯一对象
const bool b3 = r != s;                 // 未指定：两个字符串字面量可能合并
const bool b4 = il.begin() != &test1;   // 恒为 true：test1 不是潜在非唯一对象
const bool b5 = r != &test1;            // 恒为 true

int main() {}
```

## 隐式对象创建（¶13–¶16）{{c++20}}

### C 风格的代码在 C++17 中是 UB

```cpp
struct X { int a, b; };
X* make_x() {
    X* p = (X*)std::malloc(sizeof(X));
    p->a = 1;      // 按 C++17 的规则：UB，p 不指向任何 X 对象
    p->b = 2;
    return p;
}
```

按 C++17 的对象模型，对象只能由定义、new 表达式、联合体成员切换和临时对象创建。`malloc` 不在其中，`p` 所指的存储里没有 `X` 对象，`p->a` 访问的是一个不存在的对象。同样的道理，`memcpy` 到一块原始缓冲区再当结构体用、`mmap` 一个文件再当结构体用，都是 UB。就连 `std::vector` 的典型实现也有问题：`allocate` 之后对元素指针做算术，而那里并没有数组对象。

C++20 的 [[P0593R6]] 补上了这一块，并作为缺陷报告适用于之前的标准。

### 规则：需要时，对象自动出现

!!! std
    For each operation that is specified as implicitly creating objects, that operation implicitly creates and starts the lifetime of zero or more objects of implicit-lifetime types in its specified region of storage if doing so would result in the program having defined behavior.

¶13 被规定为**隐式创建对象**（[[g:implicitly-create-objects|implicitly creating objects]]）的操作，会在它的存储区域里创建零个或多个隐式生存期类型的对象并开始其生命周期，条件是这样做能让程序有定义的行为。

- 只创建**隐式生存期类型**（[[g:implicit-lifetime-type|implicit-lifetime type]]，[[basic.types.general]]）的对象：标量类型、隐式生存期类类型、数组类型，以及它们的 cv 版本。隐式生存期类大致是析构函数不是用户提供的聚合类，或者有一个平凡的合格构造函数和一个平凡且未删除的析构函数的类（[[class.prop]]）。`struct { int a, b; }` 是，`std::string` 不是。任何数组类型都是，但注 4 指出，元素本身不是隐式生存期类型时，元素的生命周期不会开始。
- 选择创建哪些对象，可以依赖之后才发生的事。可以想象成抽象机在 `malloc` 时预见了程序之后怎样使用这块存储，并恰好创建出能让这些使用合法的对象。
- 如果没有任何一组对象能让程序有定义的行为，行为未定义；如果有多组，创建哪一组是未指定的。
- 程序根本不使用这块存储时，可以一个对象也不创建。

¶14 有些操作还规定为产生一个指向**合适的已创建对象**（[[g:suitable-created-object|suitable created object]]）的指针：从隐式创建的、地址恰好是区域起点的对象中选一个，返回指向它的指针，选择的标准同样是能让程序有定义的行为。没有这样的指针值时行为未定义，有多个时选哪个是未指定的。

¶15 的例 4 就是开头的 `make_x`。现在 `malloc` 隐式创建了一个 `X` 和它的子对象 `a`、`b`，并返回指向这个 `X` 的指针：

```cpp run title="malloc-x.cpp" ok
#include <cstdlib>

struct X { int a, b; };

X* make_x() {
    X* p = static_cast<X*>(std::malloc(sizeof(X)));   // malloc 隐式创建 X，返回指向它的指针
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

反过来，如果后续的访问互相矛盾，就不存在合适的对象集合：

```cpp run title="no-valid-set.cpp" ub
#include <cstdlib>

int main() {
    void* p = std::malloc(sizeof(int));
    *static_cast<int*>(p) = 1;
    float f = *static_cast<float*>(p);   // UB：同一地址不可能同时有 int 和 float 对象
    std::free(p);
    return static_cast<int>(f);
}
```

### 哪些操作隐式创建对象

¶16 在语言层面规定了两种，都不适用于常量求值，因为常量求值必须精确追踪每个对象：

- `unsigned char` 或 `std::byte` 数组的生命周期开始时，在数组占据的存储里隐式创建对象，数组为它们提供存储（注 5）；
- 显式或隐式调用名为 `operator new` 或 `operator new[]` 的函数时，在返回的存储里隐式创建对象，并返回指向合适的已创建对象的指针。

注 6 列出标准库中隐式创建对象的函数：

| 函数 | 条款 | 效果 |
|---|---|---|
| `std::malloc`、`calloc`、`realloc`、`aligned_alloc` | [[c.malloc]] | 隐式创建对象，返回指向合适的已创建对象的指针 |
| `std::memcpy`、`std::memmove` | [[cstring.syn]] | 复制之前在目标区域隐式创建对象，返回指向合适的已创建对象的指针 |
| `std::bit_cast` | [[bit.cast]] | 在结果里隐式创建嵌套的对象 |
| `std::pmr::memory_resource::allocate` | [[mem.res.public]] | 与 `operator new` 相同 |
| `std::start_lifetime_as`、`start_lifetime_as_array` {{c++23}} | [[obj.lifetime]] | 在已有内容的存储上创建对象，保留原有的字节 |

`std::allocator<T>::allocate` 通过 `::operator new` 取得存储，并开始 `T[n]` 数组对象的生命周期，但不开始任何元素的生命周期（[[allocator.members]]）。

### 字节缓冲区需要 `std::launder`

字节数组的生命周期开始时会隐式创建对象，但 `reinterpret_cast` 不会给你一个指向这个对象的指针：

```cpp run title="buffer-launder.cpp" ok
#include <new>

struct P { int x, y; };

int main() {
    alignas(P) unsigned char buf[sizeof(P)];   // buf 的生命周期开始，隐式创建对象（如一个 P）

    // P* bad = reinterpret_cast<P*>(buf);
    // bad->x = 1;   // UB：bad 仍指向 buf[0]，而不是隐式创建的 P

    P* p = std::launder(reinterpret_cast<P*>(buf));  // OK：得到指向该地址上 P 的指针
    p->x = 1;
    p->y = 2;
    return p->x + p->y == 3 ? 0 : 1;
}
```

`malloc` 不需要 `launder`，因为 ¶14 规定它返回指向合适的已创建对象的指针。字节数组没有这样的返回值，手里的指针由 `buf` 退化而来，指向 `buf[0]`。`reinterpret_cast` 只在源对象和目标对象可以指针互转时才改变指向（[[basic.compound]]），`unsigned char` 数组和 `P` 不能互转，所以指针值不变，需要 `std::launder`（[[ptr.launder]]）。实际上主流编译器对省略 `launder` 的版本也生成预期的代码，但标准没有这个保证。

### `std::start_lifetime_as` {{c++23}}

字节已经在存储里了（从网络收到、`mmap` 进来、DMA 写入），怎样不拷贝就把它们当作一个对象？

C++20 的办法是让存储自己拷给自己：`std::memmove(p, p, n)` 隐式创建对象并保留内容，返回指向它的指针，编译器通常能把这次复制优化掉。C++23 的 [[P2590R2]] 把这个惯用法变成了一个有名字的函数：`std::start_lifetime_as<T>(p)` 在 `p` 处隐式创建一个 `T` 对象，其对象表示就是调用前存储里的内容，并返回指向它的指针（[[obj.lifetime]]）。

```cpp title="start-lifetime-as.cpp"
#include <memory>
#include <cstddef>
#include <cstdint>

struct Header { std::uint32_t magic; std::uint32_t length; };

const Header* parse(const std::byte* packet) {
    // 前提：packet 处有 sizeof(Header) 字节的存储，并且满足 Header 的对齐
    return std::start_lifetime_as<Header>(packet);   // 不拷贝，字节就是对象表示
}
```

截至写作时本机 libc++ 还没有提供 `std::start_lifetime_as`，这段代码没有经过编译验证，所以没有标注判定。

### 与 C 的有效类型规则对比

C 没有创建对象的概念，它用有效类型（effective type，C17 6.5p6）处理同样的问题：

| | C | C++ |
|---|---|---|
| `malloc` 得到的存储 | 没有声明类型，第一次用非字符类型写入时，有效类型变成写入的类型 | `malloc` 当时就隐式创建了恰好合适的对象 |
| 改变类型 | 用另一种类型写入即可 | 必须创建新对象，旧对象的生命周期结束 |
| 非平凡类型 | 不存在 | 必须用 new 表达式显式构造 |

对平凡的数据，两种语言的结论大体一致，`malloc` 后给成员赋值在两边都合法。但 C 是写入决定类型，C++ 是对象先存在、然后才被写入。在 C++ 里指针的值（指向哪个对象）有意义，所以才有了 C 里没有的 `std::launder`。

## 常量求值中的组成值（¶11–¶12）

这两段是 C++23 之后的新措辞，服务于常量表达式的检查（[[expr.const]]）。

¶11 联合体的直接成员，以及本身是这样的成员的数组的元素，叫**联合体元素子对象**（union elemental subobject）；不在生命周期内的联合体元素子对象是非活跃的。

¶12 对象的**组成值**（[[g:constituent-values|constituent values]]）：标量对象的组成值是它的值；其他对象的组成值是它所有直接子对象的组成值，但跳过非活跃的联合体元素子对象。**组成引用**（constituent references）的定义类似，是引用类型的直接成员加上子对象的组成引用。

[[expr.const]] 要求常量表达式结果的组成值和组成引用满足一定条件，例如不能是不确定值或错误值。因为跳过了非活跃的联合体元素，`constexpr` 联合体只需初始化活跃的部分。数组成员中只有部分元素在生命周期内时（借助 [[obj.lifetime]] 的 `std::start_lifetime`），也只检查这些元素。

```cpp
struct A {
    struct X { int i; int j; };
    struct Y { X x1; X x2; };
    union { int i; int arr[4]; Y y; };
};

constexpr A v2{.i = 1};  // OK：组成值为 {v2.i}
constexpr A v4 = [] {
    A a;
    a.y.x1.i = 1;        // 切换活跃成员为 y
    a.y.x2.j = 2;
    return a;
}();                     // error: 组成值包括未初始化的 v4.y.x1.j 和 v4.y.x2.i
```

这段代码改编自 ¶12 的例 3，没有标注判定，因为标准例子与规范性文字有出入。例 3 还有一行 `constexpr A v1;`，标注为 OK。本机 Clang 23 拒绝这一行：默认初始化 const 对象要求类型是 const-default-constructible 的，而 [[dcl.init.general#7]] 要求匿名联合体恰有一个成员带默认成员初始化器，`A` 不满足。按规范性文字，Clang 是对的。对 `v4`，Clang 的诊断与标准例子一致。例 3 里用 `std::start_lifetime(a.arr)` 的部分，本机 libc++ 尚未提供这个函数，这里省略。

## 实现视角

!!! impl "编译器怎么看对象模型"
    - 对象模型在机器码里几乎看不出来，它的作用是约束程序，从而给优化器留出空间。例如基于类型的别名分析（TBAA）假设 `int*` 和 `float*` 不会指向同一个对象，对应的正是上面不存在合适对象集合就是 UB 的情形。
    - 隐式对象创建几乎没有代码生成上的成本，编译器本来就把 `malloc`、`memcpy` 当作可能写入任意类型的操作。
    - GCC 和 Clang 用内建函数 `__builtin_launder` 实现 `std::launder`，它阻止优化器基于这个指针所指对象没有变化而做的推断，尤其是对 `const` 成员和 vptr 的缓存。
    - 在 Itanium ABI 下，空基类在没有冲突时放在偏移 0，与第一个成员同址；第一个成员是同类型的空类时，基类会被挪开，以满足 ¶10.3。

## 历史与演进

!!! history
    - C++98/03 把对象定义为一段存储区域（a region of storage），由此留下了有存储就有对象的理解和大量歧义。
    - C++17 的 [[P0137R1]] 重写了对象模型：对象由列明的构造创建，引入提供存储、嵌套于、指针指向对象等概念，以及 `std::launder`。副作用是 `malloc` 加成员赋值这样的 C 风格代码明确成了 UB。
    - C++20 的 [[P0593R6]] 引入隐式对象创建和隐式生存期类型，修复了上述问题，并作为缺陷报告适用于之前的标准。同时随 `[[no_unique_address]]` 引入了潜在重叠子对象。
    - C++23 的 [[P2590R2]] 加入 `std::start_lifetime_as` 和 `start_lifetime_as_array`。
    - C++26 的 [[P2752R3]] 让初始化列表的后备数组成为潜在非唯一对象。

## 常见误解

!!! pitfall "`reinterpret_cast` 会创建对象"
    `reinterpret_cast<T*>(p)` 只改变指针的类型。如果 `p` 处没有 `T` 对象，或者有但 `p` 不指向它，通过结果访问就是 UB。正确的做法是用 placement new 创建对象，依靠隐式对象创建再加 `std::launder`，用 `std::start_lifetime_as`，或者用 `std::memcpy`、`std::bit_cast` 复制到一个局部变量里。

!!! pitfall "隐式对象创建对所有类型都有效"
    它只创建隐式生存期类型的对象。`std::string* s = (std::string*)malloc(sizeof(std::string)); *s = "x";` 仍是 UB：`std::string` 有非平凡的构造函数和析构函数，`malloc` 不会为它创建对象，必须用 `::new (raw) std::string`。

!!! pitfall "两个同类型的空成员可以共享地址"
    ¶10.3 要求类型不相似。两个 `[[no_unique_address]] Empty` 成员不能同址。想用多个同类型的空成员（例如多个 `std::allocator`）压缩对象大小，常常达不到目的。

## 思考题

!!! question "思考题 1"
    下面的程序有定义的行为吗？如果有，`malloc` 隐式创建了哪些对象？

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

有定义的行为。`p[i]` 就是 `*(p + i)`，`i` 大于 1 时，[[expr.add]] 要求 `p` 指向某个数组的元素。所以 `malloc` 必须隐式创建一个 `int[4]` 数组对象（数组类型是隐式生存期类型）和其中的 4 个 `int` 元素。

返回的指针由 ¶14 选出。区域起点上有两个候选对象：数组本身和它的首元素。二者不能指针互转，而 `static_cast<int*>` 之后的值必须指向一个 `int`，所以合适的是首元素。`std::vector` 风格的代码正是靠这个机制变得合法的。
</details>

!!! question "思考题 2"
    `struct A { unsigned char buf[8]; } a;` 在 `a.buf` 里 placement new 一个 `int`，之后 `a` 的生命周期结束了吗？换成 `struct B { char buf[8]; } b;` 呢？

<details markdown="1">
<summary>答案</summary>

`A` 的情形没有结束。`a.buf` 为 `int` 提供存储（¶3），`int` 嵌套于 `a.buf`，进而嵌套于 `a`（¶4）。按 [[basic.life#2]] 第 2.5 项，只有被不嵌套于 o 的对象复用存储才结束 o 的生命周期，所以 `a` 和 `a.buf` 都还在生命周期内。

`B` 的情形结束了。`char` 数组不能提供存储，新的 `int` 不嵌套于 `b` 或 `b.buf`。它复用了 `b.buf` 里 4 个元素的存储，也复用了 `b` 的一部分存储，所以这些元素、`b.buf` 和 `b` 本身的生命周期都结束了。之后再通过 `b` 访问，就会落入 [[basic.life#8]] 列出的未定义行为。
</details>
