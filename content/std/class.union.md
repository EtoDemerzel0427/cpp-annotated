---
title: 联合体
summary: 联合体的活跃成员、对成员赋值隐式切换活跃成员的 S(E) 规则、带非平凡成员的联合体（C++26 平凡联合体）、公共初始序列读取特例、匿名联合体、类联合类与变体成员
status: draft
covers: class.union.general, class.union.anon
papers: P1330R0, P3074R7
related: basic.life, intro.object, class.mem, class.default.ctor, class.dtor, class.copy.ctor, dcl.init.aggr, expr.const.core, obj.lifetime
tags: 联合体, 对象模型, 生命周期, UB, constexpr
updated: 2026-10-17
---

**联合体**（union）是语言提供的一种工具，让同一块存储在不同时刻存放不同类型的对象。C 程序员往往把它理解为同一块内存的多个视图，例如写入 `float`、读出 `uint32_t` 来获取位模式。**在 C++ 里这种理解是错的**：C++ 的联合体在任一时刻至多有一个成员是**活跃的**（active），读取非活跃成员是未定义行为。C++ 的联合体本质上是一个由程序员手动管理生命周期的容器：标准规定了哪些操作会开始、结束某个成员的生命周期，其余一律交给程序员。

本页覆盖两个子条款：

- [class.union.general]：活跃成员、大小与地址、各项限制、通过赋值隐式切换活跃成员的规则（¶5），以及非平凡成员的处理（¶6）；
- [class.union.anon]：匿名联合体、类联合类（union-like class）与变体成员（variant member）。

阅读前需要熟悉 [[basic.life]]（生命周期的开始与结束，以及 ¶8 规定的在生命周期外访问对象的 UB）和 [[intro.object]]（对象如何创建、隐式对象创建）。`std::variant`、`std::optional`、`std::expected` 的实现都建立在本节之上。

## 联合体是一种类（¶1）

¶1 规定，联合体就是用 *class-key* `union` 定义的类。这句话的分量在于：**联合体是类**，所以它可以有成员函数、构造函数、析构函数、访问说明符、嵌套类型和静态成员，在重载决议、模板实参推导中也与 `struct` 遵循同一套规则。只有本节和其他条款中明确针对联合体的例外，才使它与 `struct` 不同。联合体的默认访问权是 `public`（[[class.access#3|[class.access.general]/3]]）。

## 活跃成员（¶2）

¶2 定义了本节最核心的术语：

!!! std
    In a union, a non-static data member is *active* if its name refers to an object whose lifetime has begun and has not ended.

    联合体中，一个非静态数据成员是**活跃的**，当且仅当它的名字指代的对象的生命周期已经开始且尚未结束。

注意，这个定义完全是从生命周期推导出来的：并不存在一个记录活跃与否的隐藏状态，说一个成员活跃，只是说这个成员对象处在生命周期内。于是，切换活跃成员就等价于结束旧成员的生命周期、开始新成员的生命周期，所有规则都可以回到 [[basic.life]] 去推理。

¶2 第二句规定，**同一时刻至多一个非静态数据成员是活跃的**，也就是说，联合体中至多存储一个成员的值。"至多"意味着也可以没有活跃成员，例如平凡默认初始化的 `U u;`，或者活跃成员已经被手动析构之后。

读取非活跃成员为什么是 UB？因为这个名字指代的对象不在生命周期内，对它做左值到右值转换，属于 [[basic.life#8]] 禁止的操作。

```cpp run title="inactive-read.cpp" ub
union U { int i; float f; };

int main() {
    U u{.i = 1};     // 活跃成员：i
    float x = u.f;   // UB: u.f 不在生命周期内（[basic.life]/8）
    return x > 0;
}
```

### C 的类型双关与 C++ 的差异

C 语言允许写入一个成员后读取另一个成员（C99 的技术勘误起以脚注明确了这一点），结果是把字节按新类型重新解释。C++ 没有接受这条规则。原因是 C++ 的对象模型以对象的生命周期为中心：联合体的每个成员都是一个独立的对象，读取一个不存在（不在生命周期内）的对象，无法赋予确定的含义；而且成员可能是带构造函数和不变式的类类型，把这些字节按另一种类型解释根本不安全。

```cpp run title="type-punning.cpp" ub
#include <cstdint>

union Pun { float f; std::uint32_t u; };

std::uint32_t bits_bad(float x) {
    Pun p;
    p.f = x;
    return p.u;      // UB: 活跃成员是 f，读 u
}

int main() { return bits_bad(1.0f) == 0x3f800000 ? 0 : 1; }
```

GCC 和 Clang 都把这种写法作为有文档的扩展来支持（GCC 文档明确说允许通过联合体做类型双关），所以它在实践中能用；但在常量求值中两者都会拒绝，而且这不是可移植的 C++。可移植的写法是 `std::bit_cast`（C++20）或 `std::memcpy`：

```cpp run title="bit-cast.cpp" ok
#include <bit>
#include <cstdint>

constexpr std::uint32_t bits(float x) { return std::bit_cast<std::uint32_t>(x); }
static_assert(bits(1.0f) == 0x3f800000);   // 甚至可以在编译期

int main() { }
```

### 公共初始序列特例（¶2 注 1）

¶2 的注 1 提到一条为方便使用联合体而设的特殊保证，正式规则在 [[class.mem#30|[class.mem.general]/30]]。如果满足以下条件：

- 联合体是标准布局的；
- 当前活跃成员是一个标准布局结构体 `T1`；
- 另一个成员是标准布局结构体 `T2`；
- 读取的是 `T2` 的成员 `m`，并且 `m` 处于 `T1` 与 `T2` 的**公共初始序列**（common initial sequence）中；

那么读取 `u.t2.m` 是允许的，效果如同读取 `T1` 中对应的成员。公共初始序列（[class.mem.general]/27）是从第一个成员开始的最长前缀，其中对应成员的类型布局兼容、对齐相同、位域宽度相同，并且都不带 `[[no_unique_address]]`。

```cpp run title="common-initial-sequence.cpp" ok
struct T1 { int a, b; };
struct T2 { int c; double d; };
union U { T1 t1; T2 t2; };

int f() {
    U u = { { 1, 2 } };   // 活跃成员是 t1
    return u.t2.c;        // OK: c 在公共初始序列中，如同读 u.t1.a
    // return (int)u.t2.d; // UB: d 不在公共初始序列中
}

int main() { return f() == 1 ? 0 : 1; }
```

这条规则的动机是 C 时代的带标签联合体惯用法：

```cpp run title="tagged-cis.cpp" ok
enum Kind { K_INT, K_STR };
struct Any  { Kind kind; };
struct IntV { Kind kind; int value; };
struct StrV { Kind kind; const char* value; };
union Value { Any any; IntV i; StrV s; };

int get(const Value& v) {
    switch (v.any.kind) {           // 不管活跃的是 i 还是 s，读 kind 都合法
    case K_INT: return v.i.value;
    case K_STR: return v.s.value[0];
    }
    return -1;
}

int main() {
    Value v{.i = {K_INT, 42}};
    return get(v) == 42 ? 0 : 1;
}
```

!!! impl "Clang 在常量求值中不支持这条特例"
    截至写作时（Clang 23），如果把上面的 `f` 改成 `constexpr` 并在常量表达式中调用，Clang 会报告读取了非活跃成员，拒绝这段代码。按标准，[class.mem.general]/30 说这次读取如同指名了活跃成员中对应的成员，因而不属于 [[expr.const.core]] 所禁止的对非活跃成员的左值到右值转换。这是实现的限制，不是标准的规定。

注意，这条特例只放宽了读，没有放宽写；而且只适用于成员都是结构体的情况。`union { int i; float f; }` 里的 `int` 和 `float` 不是结构体，谈不上公共初始序列。

## 大小、布局与地址（¶3）

¶3 规定，联合体的大小足以容纳最大的非静态数据成员；每个非静态数据成员都如同是某个非联合体类的唯一成员那样分配。注 2 指出，联合体对象与它的每个非静态数据成员都是**指针可互转换**的（pointer-interconvertible，[[basic.compound]]），因此**所有成员的地址都相同**，都等于联合体对象的地址。

指针可互转换意味着，`reinterpret_cast<int*>(&u)` 直接得到指向 `u.i` 的指针（如果 `u.i` 是活跃成员），不需要 `std::launder`。

```cpp run title="union-address.cpp" ok
#include <cassert>

union U { char c; int i; double d; };
static_assert(sizeof(U) >= sizeof(double));
static_assert(alignof(U) >= alignof(double));

int main() {
    U u{.i = 7};
    assert((void*)&u.c == (void*)&u.d);
    int* p = reinterpret_cast<int*>(&u);   // 指针可互转换：p 指向 u.i
    assert(*p == 7);
}
```

标准并没有规定 `sizeof(U)` 恰好等于最大成员的大小：末尾可以有填充，以满足最严格成员的对齐要求，实现也可以让它更大（虽然主流 ABI 不会这样做）。

## 联合体的限制（¶4）

¶4 列出了联合体与普通类的差异：

| 规则 | 理由 |
|---|---|
| 可以有成员函数（含构造函数、析构函数） | 联合体是类 |
| 不能有虚函数 | 虚函数需要 vptr，而 vptr 会和成员共享首地址；而且联合体不能被派生，虚函数毫无用处 |
| 不能有基类 | 基类子对象会与变体成员在布局上冲突；至多一个活跃成员的语义无法扩展到基类 |
| 不能作为基类 | 同上 |
| 不能有引用类型的非静态数据成员（否则 ill-formed） | 引用不是对象，没有可以切换的存储，重新绑定引用也无从谈起 |

```cpp title="union-restrictions.cpp" error
struct B {};
union U1 : B { int i; };          // error: 联合体不能有基类
union U2 { int i; };
struct D : U2 {};                 // error: 联合体不能作为基类
union U3 { virtual void f(); };   // error: 联合体不能有虚函数
union U4 { int& r; };             // error: 引用类型成员
```

### 非平凡成员与被删除的特殊成员函数（¶4 注 3）

从 C++11 的无限制联合体（unrestricted union）起，联合体的成员可以带有非平凡的特殊成员函数，例如 `std::string`。问题在于，编译器不知道哪个成员是活跃的，因而**无法自动生成正确的复制、移动和析构操作**。标准的处理方式是：

- 复制/移动构造、复制/移动赋值：如果任一成员的相应操作非平凡，联合体的相应函数就必须由用户提供，否则定义为删除的（[[class.copy.ctor]]、[[class.copy.assign]]）。
- 默认构造函数与析构函数：规则在 C++26 中有所改变，见下文。

注 3 的例子：

```cpp
union U {
  int i;
  float f;
  std::string s;
};
```

`U` 的复制/移动构造和复制/移动赋值都被隐式删除。默认构造和析构的情况如下。

在 C++23 及以前，`std::string` 有非平凡的默认构造函数和析构函数，因此 `U` 的默认构造函数和析构函数都被删除。`U u;` 直接 ill-formed，程序员必须写出 `U() {}` 和 `~U() {}` 才能使用它。

在 C++26 中 {{c++26}}，当前草案的注 3 写道，尽管 `std::string` 的相应函数非平凡，**`U` 的默认构造函数和析构函数都是平凡的**。这来自平凡联合体提案 [[P3074R7]]，它修改了两处：

- [[class.default.ctor#3]]：判断默认构造函数是否平凡时，联合体不考察其成员的类类型（¶3.4 "either X is a union or …"）。联合体的默认构造函数根本不构造任何成员，所以成员的构造函数是否平凡无关紧要。
- [[class.dtor#7]]：联合体的默认析构函数只在以下情况下被删除：默认初始化选中的构造函数被删除或非平凡（¶7.2.1），或者某个带默认成员初始化器的变体成员有非平凡析构函数（¶7.2.2）。直观地说，如果默认构造会让某个成员活跃，一个什么也不做的析构函数就可能泄漏它，所以要删除；如果默认构造什么也不做，析构什么也不做也就是一致的。

这项改动的动机是：`std::inplace_vector<T, N>` 这类有存储但不立即构造元素的类型，过去要写一个 `union { T storage[N]; }`，再手写空的构造函数和析构函数。手写的构造/析构函数是用户提供的，会让整个类型失去平凡性，在常量求值中也更难使用。C++26 让这种只提供存储的联合体天然就是平凡的。

```cpp run title="trivial-union.cpp" ok
#include <memory>
#include <string>
#include <type_traits>

union U { int i; std::string s; };

// C++26：默认构造与析构都是平凡的
static_assert(std::is_trivially_default_constructible_v<U>);
static_assert(std::is_trivially_destructible_v<U>);
static_assert(!std::is_copy_constructible_v<U>);   // 复制仍被删除

int main() {
    U u;                               // 没有活跃成员
    std::construct_at(&u.s, "hello");  // s 成为活跃成员
    std::destroy_at(&u.s);             // 手动结束 s 的生命周期，否则泄漏
}
```

!!! impl "实现状态"
    截至写作时，Clang 23 尚未实现 [[P3074R7]]：上例的两个 `static_assert` 失败，`U u;` 被报告为调用了隐式删除的默认构造函数。在编译器支持之前，可移植的写法是给联合体加上 `U() {}` 与 `~U() {}`（见下一节的例子）。

!!! lawyer "带默认成员初始化器的联合体"
    按 [class.default.ctor]/3.2，只要有一个成员带默认成员初始化器，默认构造函数就不是平凡的；而 [class.dtor]/7.2.1 说，默认构造选中非平凡构造函数时，联合体的默认析构函数被删除。逐字读下来，`union X { int i = 0; float f; };` 的析构函数似乎也会被删除，即使所有成员都是平凡的。这显然会破坏大量既有代码，很可能不是有意为之；阅读这一段时要留意草案的后续修订。

## 用赋值切换活跃成员（¶5）

这是本节设计最精巧的一段。考虑这个问题：给定 `union U { int i; float f; } u{.i = 1};`，写 `u.f = 2.0f;` 合法吗？按 [[basic.life]]，`u.f` 指代的对象不在生命周期内，对它赋值就是在生命周期外修改对象，属于 UB。但几十年来的 C/C++ 代码都是这么写的，标准不能宣布它们全是 UB。¶5 就是专门为这种写法提供的合法途径。

### 子表达式集合 S(E)

¶5 先对表达式 `E` 递归地定义集合 S(E)，用来挑出沿着表达式一路经过的联合体成员访问：

- ¶5.1 `E` 形如 `A.B`：S(E) 包含 S(A) 的全部元素；此外，如果 `B` 指名的联合体成员的类型是非类非数组类型、有平凡且未删除的默认构造函数的类类型，或者这类类型的数组，那么 `A.B` 本身也加入 S(E)。
- ¶5.2 `E` 形如 `A[B]` 且是内置下标：如果 `A` 是数组类型，S(E) = S(A)；如果 `B` 是数组类型（`i[arr]` 写法），S(E) = S(B)；否则为空（例如 `A` 是指针时，经过指针，链条就断了）。
- ¶5.3 其他形式：S(E) 为空。

（`A->B` 不在 ¶5.1 中。它定义为 `(*A).B`，而 `*A` 属于其他形式，所以 `p->m = …` 只会考虑 `p->m` 本身，不会追溯到 `p` 所指对象之外。）

### 规则本体

对于使用内置赋值运算符或平凡赋值运算符的赋值 `E1 = E2`，考察 S(E1) 中的每个元素 X（以及以这些元素为直接子对象、逐层向外的匿名联合体成员）。如果按 [[basic.life]] 修改 X 是 UB（即 X 不在生命周期内），那么：

- **在 X 指名的存储中隐式创建一个 X 类型的对象**；
- 不进行初始化；
- 它的生命周期开始于左右操作数的值计算之后、赋值之前。

注 4 补充说，这会结束联合体中先前活跃成员的生命周期（存储被复用，[[basic.life#2]]）。

!!! std
    …an object of the type of X is implicitly created in the nominated storage; no initialization is performed and the beginning of its lifetime is sequenced after the value computation of the left and right operands and before the assignment.

    ……在被提名的存储中隐式创建一个 X 类型的对象；不进行初始化，其生命周期的开始排在左右操作数的值计算之后、赋值之前。

有几个设计点值得体会：

1. 为什么要求平凡且未删除的默认构造函数？因为新对象不经初始化就进入了生命周期。只有当不初始化本来就是该类型合法的默认初始化（即平凡默认构造）时，这样凭空出现的对象才不会违反类型的不变式。带非平凡构造函数的类型（例如 `std::string`）不能这样无中生有。
2. 为什么要求内置赋值或平凡赋值？用户定义的 `operator=` 是普通的成员函数调用，它的 `this` 必须指向生命周期内的对象；而平凡赋值相当于逐字节复制，在未初始化的新对象上执行是安全的。
3. 为什么生命周期在右操作数求值之后才开始？这样 `u.f = u.i;` 这种读旧成员、写新成员的代码才是合法的：读取 `u.i` 时它仍然活跃，之后 `f` 的生命周期才开始，`i` 的生命周期随之结束。

```cpp run title="assign-switch.cpp" ok
union U { int i; float f; };

int main() {
    U u{.i = 1};
    u.f = static_cast<float>(u.i);   // OK: 先读 i（仍活跃），再创建 f，再赋值
    return u.f == 1.0f ? 0 : 1;      // OK: f 是活跃成员
}
```

### 嵌套与数组：标准例子的解读

```cpp run title="nested-union-assign.cpp" ok
union A { int x; int y[4]; };
struct B { A a; };
union C { B b; int k; };

constexpr int f() {
    C c;                  // 没有任何成员的生命周期开始
    c.b.a.y[3] = 4;       // OK: S(c.b.a.y[3]) = { c.b, c.b.a.y }
                          //     隐式创建 c.b 和 c.b.a.y，二者都成为各自联合体的活跃成员
    return c.b.a.y[3];    // OK
}
static_assert(f() == 4);  // 在常量求值中同样成立

int main() { return f() == 4 ? 0 : 1; }
```

计算过程如下。`c.b.a.y[3]` 是 `A[B]` 形式，`A` = `c.b.a.y` 是数组，所以 S = S(`c.b.a.y`)。`c.b.a.y` 是 `A.B` 形式，`y` 是 int 的数组，满足条件，加入。接着看 S(`c.b.a`)：`a` 是结构体 B 的成员，不是联合体成员，不加入。再看 S(`c.b`)：`b` 是联合体 `C` 的成员，类型 `B` 有平凡默认构造函数，加入。S(`c`) 为空。结果是 {`c.b`, `c.b.a.y`}，两个对象都被隐式创建。

!!! note "数组成员是 C++26 的扩展"
    有了 ¶5.1 中"或此类类型的数组"的措辞和 ¶5.2 的下标规则，对数组元素赋值也能开始联合体中数组成员的生命周期。这与平凡联合体一起，服务于 `inplace_vector` 那样的存储方式。另外，[[obj.lifetime]] 提供了 `std::start_lifetime(r)`，用于显式开始隐式生命周期聚合类型的联合体成员的生命周期（不初始化任何子对象），使它成为活跃成员；[[basic.life]] 列出联合体成员生命周期如何开始时，也列入了这种方式。

标准例子的第二部分展示了规则不适用的情况：

```cpp run title="const-member-no-switch.cpp" ub
struct X { const int a; int b; };
union Y { X x; int k; };

int main() {
    Y y = { { 1, 2 } };   // OK: y.x 是活跃成员
    int n = y.x.a;
    y.k = 4;              // OK: 结束 y.x 的生命周期，y.k 成为活跃成员
    y.x.b = n;            // UB: X 有 const 成员且无初始化器 ⇒ 默认构造函数被删除
                          //     ⇒ y.x 不进入 S(y.x.b)，y.x 的生命周期不会隐式开始
    return y.x.b;
}
```

`X` 的默认构造函数被删除（[[class.default.ctor#2]]：`const` 成员不可 const 默认构造），所以 `y.x` 不满足 ¶5.1 的条件；`b` 是结构体成员而不是联合体成员，所以 S(`y.x.b`) 为空。于是没有任何对象被隐式创建，`y.x.b = n` 是在修改生命周期外的对象。

!!! impl "Clang 的诊断能力"
    在常量求值中，对于带非平凡默认构造函数的成员，Clang 23 会正确地拒绝隐式切换（报告对非活跃成员赋值）；但对于上面这个默认构造函数被删除的例子，改写为 `constexpr` 函数后，Clang 没有给出诊断，而是直接接受。按标准这是 UB，常量求值中应当被拒绝（[[expr.const.core]]）。

### 用户定义的赋值不触发切换

```cpp run title="user-assign-no-switch.cpp" ub
struct P {
    int v;
    P& operator=(int x) { v = x; return *this; }   // 用户提供：不是平凡赋值
};
union U { int i; P p; };

int main() {
    U u{.i = 0};
    u.p = 5;     // UB: 调用 P::operator= 时 u.p 不在生命周期内，¶5 不适用
    return u.p.v;
}
```

## 带非平凡成员时：placement new 与手动析构（¶6）

¶6（注 5）指出，**¶5 不适用时，切换活跃成员的唯一手段是 placement *new-expression***（或等价的 `std::construct_at`）。例 3 给出了标准的两步做法，先析构旧成员，再构造新成员：

```cpp
u.m.~M();
new (&u.n) N;
```

把它扩展成一个完整的带标签联合体，也就是 `std::variant` 的简化版：

```cpp run title="tagged-union.cpp" ok
#include <memory>
#include <string>
#include <utility>

class IntOrString {
    enum class Kind { Int, Str } kind_ = Kind::Int;
    union { int i_ = 0; std::string s_; };   // 匿名联合体成员；i_ 默认活跃

    void destroy() { if (kind_ == Kind::Str) std::destroy_at(&s_); }

public:
    IntOrString() {}                // 必须用户提供（有 std::string 变体成员）
    ~IntOrString() { destroy(); }   // 必须用户提供，并且只析构活跃成员
    IntOrString(const IntOrString&) = delete;
    IntOrString& operator=(const IntOrString&) = delete;

    void set(int v) {
        destroy();
        i_ = v;                     // ¶5：int 成员可以直接赋值开始生命周期
        kind_ = Kind::Int;
    }
    void set(std::string v) {
        if (kind_ == Kind::Str) { s_ = std::move(v); return; }   // 同类型：普通赋值
        std::construct_at(&s_, std::move(v));                     // ¶6：只能 placement new
        kind_ = Kind::Str;
    }
    const std::string* str() const { return kind_ == Kind::Str ? &s_ : nullptr; }
};

int main() {
    IntOrString x;
    x.set("hello, union");
    x.set(42);
    x.set("again");
    return x.str() ? 0 : 1;
}
```

有几个细节：

- `s_ = std::move(v)` 只能在 `s_` 已经活跃时使用，因为 `std::string::operator=` 是用户提供的，不会触发 ¶5。
- 析构函数必须知道哪个成员是活跃的（`kind_`），联合体自身不记录这一信息。
- 如果构造新成员时抛出异常，联合体会处于没有活跃成员的状态，而 `kind_` 可能仍然是 Str，`std::variant` 的 `valueless_by_exception` 状态就是为此而设的。上面的代码在 `construct_at` 之后才更新 `kind_`，但 `destroy()` 已经把旧的 `s_` 析构了：如果 `construct_at` 抛出，`kind_` 还是 `Int`，析构函数不会再析构 `s_`，状态是一致的。

## 联合体与常量求值

联合体在常量求值中的规则分散在 [[expr.const.core]] 中：

- 对非活跃成员（或其子对象）做左值到右值转换，不是核心常量表达式（[expr.const.core]/2.11），也就是说，常量求值必须发现这种 UB 的读取。
- C++20 起（[[P1330R0]]），常量求值中可以通过 ¶5 的赋值改变活跃成员；在此之前，`constexpr` 函数中不允许改变联合体的活跃成员。
- 平凡地复制/移动联合体时，常量求值将其视为复制它的活跃成员（[expr.const.core]/7）。

```cpp run title="constexpr-union.cpp" ok
constexpr int ok() {
    union W { int a; float b; };
    W w{.a = 1};
    w.b = 2.0f;          // C++20 起：常量求值中允许切换活跃成员
    return (int)w.b;
}
static_assert(ok() == 2);

constexpr int bad() {
    union W { int a; float b; };
    W w{.a = 1};
    return (int)w.b;     // 读非活跃成员：在常量求值中被拒绝
}
// static_assert(bad() == 0);   // error: 不是常量表达式

int main() { }
```

C++20 起 `std::optional`、`std::variant` 能够在 `constexpr` 中使用，靠的正是这些规则。

## 联合体的复制

隐式定义的联合体复制/移动构造函数（它存在且未被删除时，即所有成员都平凡可复制时）**复制对象表示**（[[class.copy.ctor#16]]），并且对源对象中嵌套的每个对象，在目标中识别或创建一个对应的对象。换句话说，活跃成员会随着复制转移过去。`U v = u;` 之后 `v` 的活跃成员与 `u` 相同，依据就在这里。

---

## 匿名联合体（[class.union.anon] ¶1）

形如 `union { member-specification } ;` 的联合体称为**匿名联合体**（anonymous union）。它同时定义了一个无名类型和该类型的一个无名对象：

- 如果该对象是非静态数据成员，就称为匿名联合体成员（anonymous union member）；
- 否则（在命名空间或块作用域中），称为匿名联合体变量（anonymous union variable）。

该无名类型的每个对象都必须是这样的无名对象，你无法再声明第二个这种类型的对象。

**匿名联合体的成员名字绑定在联合体声明所在的作用域中**：它们像普通变量（或外层类的成员）一样直接使用，只是彼此共享地址。

```cpp run title="anon-union.cpp" ok
#include <cstring>

int main() {
    union { int a; const char* p; };   // 匿名联合体变量
    a = 1;                             // 直接用名字，就像普通局部变量
    p = "Jennifer";                    // ¶5：p 成为活跃成员，a 的生命周期结束
    return std::strlen(p) == 8 ? 0 : 1;
}
```

### 匿名联合体的成员规范受限

匿名联合体里的每个 *member-declaration* 只能是：

- 定义一个或多个 public 的非静态数据成员，
- 空声明，
- `static_assert` 声明。

匿名联合体里不能声明函数，也不能声明嵌套类型，包括闭包类型（即成员初始化器里不能出现 lambda）和嵌套的匿名联合体。理由很直接：匿名联合体没有名字，无法在外面写 `Anon::f` 或 `Anon::Nested`；它只是一组共享存储的变量，不是一个可以引用的类。private/protected 成员也没有意义，因为没有任何地方能成为它的成员或友元。

```cpp title="anon-union-restrictions.cpp" error
struct S {
    union { int a; float b; };              // OK
    union { int c; private: int d; };       // error: 成员必须是 public
    union { int e; void f(); };             // error: 不能声明函数
    union { int g; struct N {} n; };        // error: 不能声明嵌套类型
    union { int h; static_assert(true); };  // OK
};
```

（`union { int g; struct N {} n; }` 嵌套的 `struct N {}` 就是一个嵌套类型声明。）

### 存储类说明符（[class.union.anon] ¶2）

| 位置 | 规则 |
|---|---|
| 具有外部链接的命名空间（含全局命名空间） | 必须带 `static` |
| 块作用域 | 只能使用块变量允许的存储类说明符（`static`、`thread_local` 等） |
| 类作用域 | 不能有存储类说明符 |

为什么全局匿名联合体要带 `static`？匿名联合体变量没有名字，其他翻译单元不可能引用它；如果它有外部链接，各个 TU 中的匿名联合体就无法对应起来。要求 `static` 使它具有内部链接，问题也就不存在了。无名命名空间本身具有内部链接，所以其中的匿名联合体不需要 `static`。

```cpp title="anon-union-storage.cpp" error
union { int ga; };                  // error: 全局作用域的匿名联合体必须是 static
static union { int sa; };           // OK
namespace { union { int na; }; }    // OK: 无名命名空间不具有外部链接

void f() {
    static union { int s1; };       // OK
    thread_local union { int s2; }; // OK
}

struct C {
    static union { int x; };        // error: 类作用域不能有存储类说明符
};
```

### 声明了对象的联合体不是匿名联合体（[class.union.anon] ¶3）

注 1 指出，如果在 `union { … }` 之后声明了对象、指针或引用，它就不是匿名联合体，而是一个无名联合体类型的普通声明，成员名字只能通过对象访问：

```cpp title="not-anonymous.cpp" error
void f() {
    union { int aa; char* p; } obj, *ptr = &obj;
    aa = 1;           // error: aa 不在这个作用域中，而且也不关联任何对象
    ptr->aa = 1;      // OK
}
```

注 2 指向 [[dcl.init.aggr]]：没有用户声明的构造函数的联合体是聚合，花括号初始化默认初始化第一个成员，也可以用指派初始化器（`{.f = 1.0f}`）选择其他成员。

## 类联合类与变体成员（[class.union.anon] ¶4）

这里引入两个新术语：

- **类联合类**（union-like class）：联合体本身，或者以匿名联合体为直接成员的类。
- **变体成员**（variant member）：对联合体 `X` 而言，它的非静态数据成员中，不是匿名联合体的都是变体成员；此外，作为 `X` 的成员的匿名联合体，其非静态数据成员也（递归地）是 `X` 的变体成员。

```cpp
struct Tagged {
    int tag;                         // 非变体成员
    union { int i; double d; };      // i、d 是 Tagged 的变体成员
};                                   // Tagged 是类联合类
```

为什么需要变体成员这个概念？因为标准中有大量规则需要区分一定存在的成员和可能不活跃的成员：

- [[class.default.ctor#2]]、[[class.dtor#7]]：判断默认构造函数、析构函数是否被删除时，对非变体成员和变体成员分别处理；
- [[class.dtor]]：类的析构函数只析构非变体的直接成员（变体成员可能根本不活跃）；
- [[class.base.init]]：*mem-initializer* 可以初始化变体成员，但一个联合体至多初始化一个；
- [[basic.scope.scope]]：匿名联合体的数据成员名字绑定在外层作用域。

¶4 最后一句规定，**一个联合体中至多一个变体成员可以有默认成员初始化器**，因为默认构造时只能让一个成员活跃。注意，例子中匿名联合体的成员也计入外层联合体：

```cpp title="one-dmi.cpp" error
union U {
    int x = 0;
    union {
        int k;
    };
    union {
        int z;
        int y = 1;      // error: U 的第二个带初始化器的变体成员
    };
};
```

对于非联合体的类联合类（如 `struct Tagged`），每个匿名联合体成员各自至多有一个初始化器，因为它们是不同的联合体。

---

## 实现视角

!!! impl
    - 布局：在所有主流 ABI 中，联合体的大小是最大成员的大小向上取整到最严格的对齐，所有成员的偏移都是 0。在 Itanium C++ ABI 下，联合体按值传参的方式取决于它是否对调用而言平凡（复制构造和析构平凡且未删除）。
    - 类型双关：GCC 文档明确允许通过联合体读取非活跃成员来重新解释字节（作为扩展，并且仅限直接通过联合体类型进行的访问），Clang 的行为与之一致。这是**实现的保证，不是 C++ 标准的保证**；通过指针间接访问时，GCC 的保证不成立。
    - `std::variant` 在 libstdc++、libc++ 和 MSVC STL 中都实现为递归的联合体（`_Variadic_union` 之类），每层包含一个成员和由其余成员组成的联合体，再配合一个索引字段；`valueless_by_exception` 对应没有活跃成员的状态。
    - 常量求值器会记录每个联合体的活跃成员，所以它能报告读取了非活跃成员。

## 历史与演进

!!! history
    - **C++98/03**：联合体成员不能有非平凡的构造函数、析构函数或复制赋值（即不能放 `std::string`）。
    - **C++11**：引入无限制联合体，允许非平凡成员，相应的特殊成员函数被删除，由程序员手写。同时引入默认成员初始化器（至多一个）。
    - **C++17**：对象模型重写（[[P0137R1]] 等），活跃成员开始以生命周期严格定义；¶5 的赋值切换规则在这一时期以现在的形式出现，为长期存在的惯用法提供了依据。
    - **C++20**：[[P1330R0]] 允许在常量求值中切换活跃成员；有了指派初始化器，`U{.f = 1}` 成为选择初始化成员的标准写法；引入隐式对象创建（[[P0593R6]]）。
    - **C++26**：[[P3074R7]] 引入平凡联合体，联合体的默认构造函数和析构函数不再因成员非平凡而被删除；¶5 扩展到数组成员；引入 `std::start_lifetime`。

## 陷阱

!!! pitfall "常见误解"
    1. 以为写 A 读 B 就是按新类型重新解释字节。在 C++ 中这是 UB（编译器扩展除外），应当使用 `std::bit_cast`。
    2. 以为对成员赋值总能切换活跃成员。只有使用内置或平凡赋值，并且目标类型有平凡且未删除的默认构造函数时才行。`s` 不活跃时，`u.s = "x"`（`std::string`）是 UB。
    3. 忘记析构。联合体不知道哪个成员是活跃的，所以不会析构它。带非平凡成员的联合体必须由外层代码显式析构。
    4. 析构了非活跃成员。`s` 不活跃时，`u.s.~basic_string()` 是 UB（在生命周期外调用成员函数，[[basic.life#7]]）。
    5. 误用公共初始序列。它只适用于标准布局联合体中结构体成员的公共前缀，而且只能读。
    6. 忽视经过指针时链条会断开。在 `p->m = 1`（`p` 指向非活跃成员）中，S(E) 只考虑 `p->m` 这一层，经指针到达的外层联合体成员不会被隐式创建。

## 思考题

!!! question "思考题 1"
    给定 `struct S { int a, b; }; union U { int i; S s; } u{.i = 1};`，执行 `u.s.b = 2;` 之后读 `u.s.a` 是什么行为？

<details markdown="1">
<summary>答案</summary>

先看 S(`u.s.b`)：`b` 是结构体成员而非联合体成员，不加入。再看 S(`u.s`)：`s` 是联合体成员，其类型有平凡默认构造函数，加入。于是 `u.s` 被隐式创建（不初始化），`u.i` 的生命周期结束。`u.s.a` 是新对象 `u.s` 的子对象，处于生命周期内，但**从未初始化**，它的值是不确定的（[[basic.indet]]），读取它是 UB（对自动存储期变量而言，视具体情形也可能是错误行为）。复用了 `u.i` 的字节，并不能保证 `a == 1`。
</details>

!!! question "思考题 2"
    为什么 ¶5 要求被创建的成员类型具有平凡的默认构造函数，而不是允许任何可默认构造的类型，再隐式调用它的默认构造函数？

<details markdown="1">
<summary>答案</summary>

因为一个看起来只是赋值的表达式，不应该暗中执行任意的用户代码。如果允许调用非平凡的默认构造函数，`u.s = x;` 就会在赋值之前运行构造函数（可能分配内存，也可能抛出异常），这既违反直觉，也会让表达式的求值顺序和异常安全变得难以描述。平凡的默认构造什么也不做，凭空创建对象与正常的默认初始化在可观察行为上没有区别，所以可以安全地隐式完成。
</details>

!!! question "思考题 3"
    `union U { std::string s; int i; };` 在 C++26 中，`U u; u.i = 1;` 合法吗？之后 `u` 离开作用域会怎样？

<details markdown="1">
<summary>答案</summary>

按 C++26 的规则是合法的。`U` 的默认构造函数是平凡的（[class.default.ctor]/3.4 对联合体不考察成员），`U u;` 之后没有活跃成员；`u.i = 1` 按 ¶5 隐式创建一个 `int` 对象。`U` 的析构函数也是平凡的（默认构造选中的构造函数是平凡的，而且没有带初始化器的非平凡变体成员），离开作用域时什么也不做。这里活跃的是 `int`，不需要析构，所以没有泄漏。如果活跃的是 `s`，就必须在离开作用域之前手动调用 `std::destroy_at(&u.s)`。在 C++23 中，`U u;` 本身就是 ill-formed（默认构造与析构都被删除）。
</details>

## 小结

!!! summary
    | 主题 | 要点 |
    |---|---|
    | 活跃成员 | = 生命周期内的那个成员；至多一个；读非活跃成员是 UB |
    | 布局 | 所有成员地址相同，与联合体指针可互转换 |
    | 限制 | 无虚函数、无基类、不能作基类、无引用成员 |
    | 赋值切换（¶5） | 内置/平凡赋值 + 平凡且未删除的默认构造（或其数组）⇒ 隐式创建对象，不初始化 |
    | 非平凡成员（¶6） | 只能手动析构 + placement new / `construct_at` |
    | 特殊成员函数 | 非平凡复制/移动 ⇒ 删除；C++26 起默认构造/析构通常平凡 |
    | 公共初始序列 | 标准布局联合体中的结构体成员，可以读公共前缀 |
    | 匿名联合体 | 名字注入外层作用域；只能有 public 数据成员；全局须 `static` |
    | 变体成员 | 联合体及匿名联合体的成员；构造/析构规则对其特殊处理；至多一个默认成员初始化器 |
