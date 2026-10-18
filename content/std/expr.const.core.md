---
title: 核心常量表达式
summary: 一张求值期黑名单：求值中只要出现非 constexpr 调用、UB、reinterpret_cast、非瞬时分配、读取运行期对象等，表达式就不是核心常量表达式；以及 constexpr-unknown 引用
status: done
papers: P2280R4, P0784R7, P2738R1, P2747R2, P3068, P2242R3, P2647R1, P1330R0, P2795R5
related: expr.const, expr.const.const, expr.const.init, dcl.constexpr, basic.life, intro.execution, topics/compile-time-programming
tags: 常量求值, constexpr, UB
updated: 2026-10-17
---

这一节是 [expr.const] 的核心。它用排除法定义**核心常量表达式**（core constant expression）：按抽象机（[[intro.execution]]）的规则求值表达式 `E`，只要过程中没有求值 ¶2 列出的 36 类操作中的任何一种，`E` 就是核心常量表达式。

在读具体条目之前，先记住这个定义的几个关键特征：

- **看的是求值，不是代码**。`constexpr int f(bool b) { return b ? 1 : throw 0; }` 里写着 `throw`，但 `f(true)` 不会求值它，所以 `f(true)` 是核心常量表达式。没有执行到的代码不受黑名单约束，所以 C++23 才能放心地允许 constexpr 函数里出现 `goto` 和非字面类型变量。
- E 的求值包括 E 调用的所有函数。黑名单作用于整棵调用树，而不仅是 E 的直接子表达式。
- **生命期始于 E 的求值之内**（lifetime began within the evaluation of E）是贯穿全节的标尺：在 E 内部创建的对象，E 可以随意读写；在 E 之外创建的对象，E 只能读取其中可用于常量表达式的那些（[[expr.const.init#7]]）。
- 核心常量表达式只约束求值过程；对结果的约束（不能带出悬空指针、不确定值等）在 [[expr.const.const#4]]。

## 具有 constexpr-unknown 表示的类型（¶1）

¶1 定义了一个辅助概念。如果类型 T 是下列之一，就说 T **具有 constexpr-unknown 表示**（constexpr-unknown representation）：

- 联合体（¶1.1）；
- `std::meta::info`（¶1.2）{{c++26}}；
- 指针或成员指针类型（¶1.3）；
- volatile 限定的类型（¶1.4）；
- 有引用类型非静态数据成员的类类型（¶1.5）；
- 有基类或非静态成员的类型具有 constexpr-unknown 表示（¶1.6，递归）。

直观地说，这些类型的对象表示（字节）在翻译期无法确定。指针的位模式取决于链接和加载地址（空指针也不一定是全 0）；联合体的字节取决于哪个成员活跃；引用成员通常以地址实现；`volatile` 对象的值可能被外部改变。这份清单与 `std::bit_cast` 不能在常量求值中使用的类型（[[bit.cast]]）是同一组。

这个概念目前只在 ¶2.29 中使用：比较两个指向可能非唯一对象的指针时，如果其中一个指向这种类型的对象，编译器无法判断两块存储有没有被合并（见下文）。

## 黑名单总览（¶2）

!!! std
    An expression E is a core constant expression unless the evaluation of E, following the rules of the abstract machine, would evaluate one of the following: …

    除非按抽象机规则对 E 求值会求值下列之一，否则 E 是核心常量表达式。

为了便于理解，下面按被禁止的理由把 36 项重新分组，每组内保留原编号。

| 组 | 条目 | 禁止的理由 |
|---|---|---|
| 读写编译期看不见的状态 | 2.1 `this`、2.2 静态局部变量、2.10–2.12 左值到右值转换、2.14 lambda 中的 odr-use、2.18 修改、2.19 析构 | 值在运行期才存在，或修改会泄漏到求值之外 |
| 调用编译器执行不了的代码 | 2.3–2.6 函数调用、2.33 `asm`、2.34 `va_arg`、2.35 非常量库调用 | 没有可执行的定义，或语义依赖运行环境 |
| 未定义 / 未指定行为 | 2.8 UB 与 EB、2.9 浮点异常、2.17 未知边界数组算术、2.28–2.29 未指定的比较 | 结果不唯一，或标准不给结果 |
| 类型双关 | 2.15 `void*` 转换、2.16 `reinterpret_cast` | 编译器的对象模型是有类型的，不能把字节重新解释 |
| 动态内存 | 2.20–2.23 `new`/`delete`/`allocator` | 只允许瞬时分配：分配必须在本次求值内释放 |
| 异常 | 2.24、2.25、2.31 | 只允许在求值内完整地抛出与处理 {{c++26}} |
| 其他 | 2.7 实现限制、2.13 含 mutable 的联合体复制、2.26–2.27 协程、2.30 constexpr-unknown 动态类型、2.32 注入声明、2.36 `goto` | 见各条 |

### `this`（¶2.1）

`this` 只能在两种情况下出现在核心常量表达式中：

- 在作为 E 的一部分被求值的 constexpr 函数里（¶2.1.1），例如调用 constexpr 成员函数时，它的 `this` 指向调用者提供的对象；
- 作为（隐式或显式）类成员访问的 *postfix-expression*（¶2.1.2），即 `this->m` 或隐式的 `m`。

第二条与 [[P2280R4]] 的思路一致：在非 constexpr 成员函数里，按 ¶9，`this` 指向的对象被视为一个 constexpr-unknown 对象；只要 `this` 仅用于成员访问，被调用的成员函数又不读取成员，就不需要知道它的值。

```cpp
struct S {
    static constexpr int cap() { return 4; }
    constexpr int sz() const { return 3; }   // 不读取任何成员
    void f() {                               // 非 constexpr 成员函数
        static_assert(this->cap() == 4);     // 按 ¶2.1.2：OK
        static_assert(sz() == 3);            // 按 ¶2.1.2 + ¶9：OK（隐式 this->sz()）
    }
};
```

!!! impl "Clang 的分歧"
    本站测试的 Clang 23 拒绝上面两条 `static_assert`，诊断为 "use of 'this' pointer is only allowed within the evaluation of a call to a 'constexpr' member function"，即尚未实现 ¶2.1.2 的放宽。

### 静态与线程局部的块变量（¶2.2）

如果控制流经过一个静态或线程存储期块变量的声明，而该变量不可用于常量表达式，表达式就不是核心常量表达式。

```cpp ok
constexpr char test() {
    static const int x = 5;                    // const int + 常量初始化 → 可用于常量表达式
    static constexpr char c[] = "Hello World";
    return *(c + x);
}
static_assert(' ' == test());
```

为什么？在运行期，静态局部变量在控制流首次经过时初始化，并且要保证线程安全，这需要守卫变量（guard variable）；而且它的值在多次调用之间共享。如果允许常量求值经过一个可变的 `static int`，编译期与运行期看到的状态就会分叉。可用于常量表达式的静态变量（`static constexpr`，或经常量初始化的 `static const` 整型变量）是不可变的常量，没有这个问题。

```cpp error
constexpr int counter() {
    static int k = 0;   // 非 const：经过此声明 → 不是核心常量表达式
    return ++k;
}
constexpr int c = counter();   // error
```

!!! history "演进"
    在 C++20 及之前，constexpr 函数体里根本不能定义静态或线程存储期变量（无论是否被求值）。C++23 的 [[P2242R3]] 允许它们出现在不被求值的分支里；[[P2647R1]] 进一步允许控制流经过 `static constexpr` 变量。现在的 ¶2.2 是二者的合并形式：只看求值时是否经过，以及变量是否可用于常量表达式。

### 函数调用（¶2.3–2.6）

- ¶2.3 调用非 constexpr 函数。脚注 61 强调，重载决议照常进行，不会因为某个候选不是 constexpr 就转而选择另一个。
- ¶2.4 调用已声明但尚未定义的 constexpr 函数（在求值发生的那一点，定义还不可达）。
- ¶2.5 调用一个不是 constexpr-suitable 的 constexpr 函数实例化。按 [[dcl.constexpr#3]]，目前唯一不 suitable 的情形是协程：函数模板加了 `constexpr`，但某个实例化成了协程，这个实例化仍然合法，只是不能用于常量求值。
- ¶2.6 对动态类型为 constexpr-unknown 的对象调用虚函数（见 ¶9）。注意，对动态类型已知的对象调用虚函数，自 C++20（[[P1064R0]]）起是允许的。

```cpp
constexpr int f();                 // 只声明
constexpr int a = f();             // error: ¶2.4，f 此时未定义
constexpr int f() { return 1; }
constexpr int b = f();             // OK

int rt();                          // 非 constexpr
constexpr int g(bool x) { return x ? 1 : rt(); }
constexpr int c = g(true);         // OK：rt() 未被求值
constexpr int d = g(false);        // error: ¶2.3
```

!!! note "C++23 起允许永远无法常量求值的 constexpr 函数"
    `constexpr int g() { return rt(); }` 在 C++20 及之前是 IFNDR（没有任何调用能成为常量表达式）。C++23 的 [[P2448R2]] 删除了这条规则，这样的函数现在是良构的，只是每次在常量求值中调用它都会命中 ¶2.3。Clang 在 C++20 及更早模式下仍给出 "constexpr function never produces a constant expression" 诊断。

### 实现限制（¶2.7）

超出附录 [[implimits]] 中实现定义的限制的表达式不是核心常量表达式。附录建议的量包括递归 constexpr 调用的深度（至少 512）、单个核心常量表达式求值中的完整表达式数量（至少 1 048 576）等。这样，无限循环的 constexpr 求值就有了明确的结局：编译器不会卡死，表达式只是不再是常量。

!!! impl "实现视角"
    Clang：`-fconstexpr-depth=`（默认 512）、`-fconstexpr-steps=`（默认 1048576）。GCC：`-fconstexpr-depth=`、`-fconstexpr-loop-limit=`、`-fconstexpr-ops-limit=`。MSVC：`/constexpr:depth`、`/constexpr:steps`。超出限制时，表达式不是常量，因此在要求常量的上下文中是 ill-formed，在 `const int x = ...` 这样的上下文中则不声不响地退化为动态初始化。

### 未定义行为与错误行为（¶2.8）

!!! std
    an operation that would have undefined or erroneous behavior as specified in Clause [intro] through Clause [cpp];

    一个按第 4 至第 15 章（核心语言部分）的规定会有未定义行为或错误行为的操作。

这是常量求值最重要的性质：**核心语言的 UB 在常量求值中必须被诊断**。脚注 62 举的例子有：有符号整数溢出、某些指针算术、除以零、某些移位。实际覆盖面更广，还包括越界访问、解引用空指针或悬空指针、访问生命期外的对象、读取非活跃联合体成员、违反严格别名、读取不确定值等。

这样规定有两个理由：

1. 常量表达式的值必须是确定的。如果 UB 可以产生一个值，不同编译器就会把不同的值嵌入程序，模板实例化 `X<INT_MAX + 1>` 将没有可移植的含义。
2. 编译器本来就在模拟抽象机，它知道每个对象的类型、边界和生命期，比运行期更容易检测这些错误。

```cpp error
#include <climits>
constexpr int add(int a, int b) { return a + b; }
constexpr int a1 = add(INT_MAX, 1);   // error: 有符号溢出

constexpr int oob() { int a[3]{}; return a[3]; }
constexpr int a2 = oob();             // error: 越过末尾读

constexpr int a3 = 1 / 0;             // error: 除以零
constexpr int a4 = 1 << 32;           // error: 移位量 ≥ 位宽

constexpr int dangling() {
    int* p;
    { int x = 1; p = &x; }
    return *p;                        // 读取生命期已结束的对象
}
constexpr int a5 = dangling();        // error
```

{{c++26}} C++26 引入了**错误行为**（erroneous behavior，[[P2795R5]]），例如未初始化的自动变量现在具有错误值，读取它不再是 UB。¶2.8 明确把错误行为也列入黑名单，所以下面的代码在 C++26 中仍然不是常量：

```cpp error
constexpr int uninit() {
    int x;          // C++26：x 具有错误值（erroneous value）
    return x;       // 错误行为 → 不是核心常量表达式（同时命中 ¶2.12 之前的规则）
}
constexpr int v = uninit();   // error
```

!!! warning "范围：只有核心语言的 UB"
    ¶2.8 只覆盖第 4–15 章（核心语言与预处理器）。标准库的 UB（违反前置条件，如 `std::vector::operator[]` 越界）不在此列，由 ¶4 处理：是否为核心常量表达式是**未指定**的。因此，库函数的 UB 在常量求值中不保证被诊断，尽管主流实现的 constexpr 库通常会因为底层触发了核心 UB（越界读）而报错。

### 浮点算术（¶2.9）

浮点运算的 UB 比较微妙：IEEE 754 定义了 `1.0/0.0 == inf`，但标准的 [[expr.pre#4]] 说，结果不在可表示值范围内或在数学上无定义时是 UB。¶2.9 精确规定了常量求值中哪些浮点运算不可接受。在以下情况下，算术表达式不是核心常量表达式：

- ¶2.9.1 所有操作数都是有限值，但结果不是有限值（溢出到无穷、`0.0/0.0`、`1.0/0.0`）；
- ¶2.9.2 任一操作数是 signaling NaN；
- ¶2.9.3 没有操作数是 NaN，但结果是 NaN。

换句话说，已经是 inf 或 quiet NaN 的值可以继续参与运算（`inf * 2` 是常量），但不能在常量求值中产生新的 inf 或 NaN。

```cpp
#include <limits>
constexpr double inf = std::numeric_limits<double>::infinity();
constexpr double d1 = inf * 2;                                 // OK：操作数不是有限值
constexpr double d2 = 1.0 / 0.0;                               // error: ¶2.9.1
constexpr double d3 = 0.0 / 0.0;                               // error: ¶2.9.1 / ¶2.9.3
constexpr double d4 = std::numeric_limits<double>::max() * 2;  // 按 ¶2.9.1 应为 error
```

!!! impl "Clang 的分歧"
    本站测试的 Clang 23 拒绝 `d2`、`d3`（诊断为除以零），但接受 `d4`（有限值相乘溢出为 inf）。按当前草案 ¶2.9.1，`d4` 不是常量表达式。这是编译器尚未跟进的规则，可移植代码不应依赖 `d4` 被接受。

### 左值到右值转换：读取什么是允许的（¶2.10–2.12）

在标准里，读取一个对象的值就是**左值到右值转换**（lvalue-to-rvalue conversion，[[conv.lval]]）。这是黑名单里最常命中的一条。¶2.10 规定，左值到右值转换只在下列三种情况下允许：

1. ¶2.10.1 作用于 `cv std::nullptr_t` 类型的泛左值。读取 `nullptr_t` 不需要访问内存（[[conv.lval]] 直接给出空指针常量），所以哪怕对象未初始化也没关系；
2. ¶2.10.2 作用于非 volatile 的泛左值，且它指代一个可用于常量表达式的对象（[[expr.const.init#9]]），包括 `constexpr` 变量、用常量初始化的 `const` 整型/枚举变量、字符串字面量对象、模板参数对象，以及它们的非 mutable 子对象；
3. ¶2.10.3 作用于字面类型的非 volatile 泛左值，且它指代一个生命期始于 E 的求值之内的非 volatile 对象，即本次求值自己创建的局部变量、临时对象、`new` 出来的对象。

```cpp
const int ci = 5;          // const 整型 + 常量初始化 → 可用于常量表达式
static_assert(ci == 5);    // OK：¶2.10.2

int nc = 5;
static_assert(nc == 5);    // error: nc 不是 const，不可用于常量表达式

const double cd = 1.0;
static_assert(cd == 1.0);  // error: const double 不是 potentially-constant（只有整型/枚举享受"const 即常量"的老规则）

const volatile int vi = 1;
static_assert(vi == 1);    // error: volatile

constexpr int local() {
    int x = 1;             // 生命期始于本次求值
    x += 2;
    return x;              // OK：¶2.10.3
}
static_assert(local() == 3);

constexpr bool np() {
    decltype(nullptr) p;   // 未初始化
    return p == nullptr;   // OK：¶2.10.1，读取 nullptr_t 不访问内存
}
static_assert(np());
```

!!! lawyer "为什么 `const double` 不行而 `const int` 可以？"
    这是 C++98 遗留的特例：C++98 允许用常量初始化的 const 整型变量做数组边界，C++11 保留了这条规则，但没有推广到浮点（浮点常量那时也不能做 NTTP，且不保证编译期与运行期一致）。现在 [[expr.const.init#6]] 把它形式化为 **potentially-constant**：constexpr 变量、引用类型变量，或非 volatile 的 const 整型/枚举类型变量。想让 `double` 可用于常量表达式，必须写 `constexpr`。

¶2.11：对非活跃联合体成员（或其子对象）做左值到右值转换。这是 UB（[[class.union]]），常量求值中必须拒绝。注意，C++20 起（[[P1330R0]]）可以在常量求值中通过赋值切换活跃成员。

```cpp
union U { int i; float f; };
constexpr float pun() { U u{.i = 1}; return u.f; }      // 读非活跃成员
constexpr float x = pun();                              // error: ¶2.11

constexpr int sw() { U u{.i = 1}; u.f = 2.0f; return (int)u.f; }  // 切换活跃成员后读取
static_assert(sw() == 2);                               // OK
```

¶2.12：对具有不确定值的对象做左值到右值转换。C++20 的 [[P1331R2]] 允许 constexpr 函数中出现未初始化的变量（平凡默认初始化），但读取它仍然不行。在 C++26 中，未初始化的自动变量多数情况下具有错误值（由 ¶2.8 覆盖）；不确定值仍然存在，例如用 `[[indeterminate]]` 标注的变量和动态分配的对象。

### 联合体的复制与 mutable 成员（¶2.13）

如果调用联合体隐式定义的复制/移动构造函数或赋值运算符，而联合体的活跃成员是 `mutable` 的，那么除非联合体对象的生命期始于 E 之内，表达式就不是核心常量表达式。

理由是：联合体的平凡复制本质上是按字节复制整个对象，¶7 把它解释为复制活跃成员。对一个 constexpr 联合体对象而言，它的 mutable 成员不是常量（可以在运行期被修改），所以复制它就等于读取一个运行期可变的值。

```cpp
union U { mutable int m; int n; };
constexpr U u{.m = 1};
constexpr U v = u;          // error: ¶2.13，活跃成员 m 是 mutable

constexpr int local() { U a{.m = 1}; U b = a; return b.m; }
static_assert(local() == 1);   // OK：a 的生命期始于本次求值
```

### lambda 中对外层自动变量的 odr-use（¶2.14）

在 *lambda-expression* 中引用 `this` 或 lambda 之外定义的自动变量，如果这个引用构成 odr-use，表达式就不是核心常量表达式。

```cpp
void g() {
    const int n = 0;
    [=] {
        constexpr int i = n;     // OK：n 是常量初始化的 const int，此处不是 odr-use
        constexpr int j = *&n;   // error: &n 是对 n 的 odr-use
    };
}
```

为什么？在 lambda 体中，对外层 `n` 的 odr-use 会导致捕获，捕获后的 `n` 实际上指的是闭包对象的数据成员。闭包对象存在于运行期，constexpr 变量 `j` 的初始化器不能依赖它。而在 `constexpr int i = n;` 中，`n` 是可用于常量表达式的变量，直接读它的值不是 odr-use（[[basic.def.odr]]），也就不需要捕获。

注 1 补充说，如果 odr-use 发生在闭包类型的函数调用运算符被调用时，*id-expression* 已经变换成对闭包数据成员的访问（[[expr.prim.lambda.capture]]），不再指代外层自动变量，因此不受 ¶2.14 约束。所以下面这种在常量求值内部创建闭包的写法完全合法：

```cpp ok
auto monad = [](auto v) { return [=] { return v; }; };
auto bind  = [](auto m) { return [=](auto fvm) { return fvm(m()); }; };
static_assert(bind(monad(2))(monad)() == monad(2)());
```

!!! impl "Clang 的分歧"
    本站测试的 Clang 23 没有拒绝上面的 `constexpr int j = *&n;`（lambda 从未被调用，Clang 没有在 lambda 体内诊断该初始化器）。按 ¶2.14 它应当是 ill-formed。

### 类型双关：`void*` 与 `reinterpret_cast`（¶2.15–2.16）

¶2.15 {{c++26}}：把指向 cv `void` 的指针纯右值 P 转换为指向 T 的指针（T 不是 void）时，除非 P 是空指针值，或 P 指向一个类型与 T 相似（similar，[[conv.qual]]）的对象，否则表达式不是核心常量表达式。

```cpp
constexpr int ok() {
    int x = 42;
    void* p = &x;
    return *static_cast<int*>(p);      // OK（C++26）：p 确实指向 int
}
static_assert(ok() == 42);

constexpr int bad() {
    int x = 42;
    void* p = &x;
    return *static_cast<short*>(p);    // 指向的对象是 int，与 short 不相似
}
constexpr int b = bad();               // error: ¶2.15
```

在 C++23 及之前，任何从 `void*` 到对象指针的 `static_cast` 都使表达式非常量，导致类型擦除容器（`std::any`、`std::function_ref` 风格的实现）无法 constexpr。[[P2738R1]] 放开了转回原类型这一安全情形，因为编译器知道每个对象的真实类型，检查成本很低。

¶2.16：`reinterpret_cast` 一律不允许，不论转换是否安全。常量求值器维护的是一个有类型的对象模型，而使用 `reinterpret_cast` 得到的指针（例如把 `int*` 当 `char*` 读字节）需要知道对象表示，编译器不愿也不必支持。需要编译期读字节时，用 `std::bit_cast`（[[bit.cast]]）。

```cpp error
constexpr int first_byte() {
    int x = 1;
    return *reinterpret_cast<unsigned char*>(&x);   // 即使是合法的别名访问
}
constexpr int fb = first_byte();   // error: ¶2.16
```

### 未知边界数组的指针算术（¶2.17）

如果指针算术的一个操作数指向未知边界数组的首元素，另一个是非零整数，表达式就不是核心常量表达式。原因是编译器不知道数组有多长，无法判断 `+ n` 是否越界（越界是 UB，必须能检测）。加零是安全的。

```cpp
extern int ea[];                  // 未知边界
constexpr int* p0 = ea + 0;       // OK
constexpr int* p1 = ea + 1;       // error: ¶2.17
```

### 修改与析构（¶2.18–2.19）

¶2.18：修改对象（赋值、复合赋值、自增自减）时，除非作用于字面类型的非 volatile 左值，且该左值指代一个生命期始于 E 之内的非 volatile 对象，否则表达式不是核心常量表达式。

这条是 C++14 的 [[N3652]]（放宽 constexpr 限制）的核心。C++11 的常量求值是纯函数式的，完全不允许修改；C++14 允许修改本次求值创建的对象。为什么只能是本次创建的？因为修改外部对象（全局变量、用 `const_cast` 去掉 const 的常量）会让常量求值产生副作用，而翻译期的副作用无法反映到运行期。

```cpp
int g = 0;
constexpr int touch() { return ++g; }
constexpr int e1 = touch();           // error: g 的生命期不始于本次求值

constexpr int k = 1;
constexpr int cheat() { return ++const_cast<int&>(k); }
constexpr int e2 = cheat();           // error: 同理（运行期这也是 UB：修改 const 对象）
```

¶2.19：对生命期不始于 E 之内的对象调用析构函数或伪析构函数。逻辑相同：不能在常量求值中结束外部对象的生命期。

### 动态内存：瞬时分配（¶2.20–2.23）

C++20 的 [[P0784R7]] 允许在常量求值中使用动态内存，条件是分配必须是**瞬时的**（transient）：

- ¶2.20.1 *new-expression* 选择的是可替换的全局分配函数（`::operator new` 族），并且分配的存储在 E 的求值之内被释放；
- ¶2.21 *delete-expression* 只能释放 E 之内分配的存储；
- ¶2.22–2.23 `std::allocator<T>::allocate` / `deallocate` 同理。

```cpp
#include <vector>
constexpr int sum() {
    std::vector<int> v{1, 2, 3};
    v.push_back(4);
    int s = 0;
    for (int x : v) s += x;
    return s;                     // v 在返回前析构，内存已释放
}
static_assert(sum() == 10);       // OK

constexpr int* leak() { return new int(1); }
constexpr int* p = leak();        // error: 分配未在求值内释放

constexpr std::vector<int> gv{1, 2, 3};   // error: 同理，存储会"泄漏"到运行期
```

为什么不允许非瞬时分配？如果允许，编译期分配的内存就必须提升为静态存储，而运行期代码可能会对它调用 `delete`，从而释放一块从未由运行期分配器分配的内存。这一问题（non-transient constexpr allocation）在 C++26 中仍未解决。

¶2.20.2 {{c++26}}（[[P2747R2]]）：非分配形式的 placement new（`::new (p) T(...)`）也是允许的，只要满足：

- 放置实参指向一个可以被新对象透明替换（transparently replaceable，[[basic.life]]）的对象（对数组则指向其首元素）；
- 放置实参指向的存储，其存储期始于 E 之内。

```cpp ok
#include <memory>
#include <new>
constexpr int pn() {
    std::allocator<int> al;
    int* p = al.allocate(1);
    ::new (p) int(7);          // C++26：constexpr placement new
    int r = *p;
    std::destroy_at(p);
    al.deallocate(p, 1);
    return r;
}
static_assert(pn() == 7);
```

在 C++20/23 中，只能用 `std::construct_at` 达到同样效果；引入 `construct_at` 本来就是为了绕开 placement new 不是 constexpr 的限制。¶6 规定，判断核心常量表达式时忽略 `std::allocator<T>` 成员函数函数体的求值，因为库实现内部可能用了非 constexpr 的手段，标准只关心调用了 allocate/deallocate 这一事实本身。

### 异常（¶2.24–2.25、¶2.31）

{{c++26}} [[P3068]] 允许常量求值抛出并捕获异常：

- ¶2.24：构造异常对象，除非它及其通过 `std::current_exception` / `std::rethrow_exception` 产生的所有隐式副本都在 E 之内销毁。也就是说，异常必须在求值内部被捕获并处理完，不能逃出常量求值。
- ¶2.25：不带操作数的 `throw;`（重新抛出），除非当前处理的异常对象是在 E 之内构造的。
- ¶2.31：`dynamic_cast`、`typeid`、*new-expression* 本来会抛出异常，但异常类型（`std::bad_cast`、`std::bad_typeid`、`std::bad_alloc`、`std::bad_array_new_length`）的定义不可达，例如没有包含 `<typeinfo>`/`<new>`。此时编译器需要构造这种类型的对象，却看不到它的定义。

```cpp
constexpr int ex() {
    try { throw 1; }
    catch (int e) { return e; }
}
static_assert(ex() == 1);   // C++26：OK；C++23：error（求值了 throw-expression）
```

!!! impl "实现状态"
    截至写作时，本站测试的 Clang 23 仍然拒绝上例（"subexpression not valid in a constant expression"），即尚未实现 [[P3068]]。在 C++23 及之前，只要求值了 *throw-expression*，表达式就不是常量；`try` 块自 C++20（[[P1002R1]]）起可以出现在 constexpr 函数中，但 `catch` 在常量求值中永远执行不到。

### 协程、`asm`、`va_arg`、`goto`（¶2.26–2.27、¶2.33–2.36）

- ¶2.26–2.27：`co_await`、`co_yield` 不可求值（协程帧需要运行期分配，且协程函数本身不是 constexpr-suitable）。
- ¶2.33：*asm-declaration*。C++20（[[P1668R1]]）起 constexpr 函数中可以出现 `asm`，以便在 `if consteval` / `is_constant_evaluated()` 的运行期分支中使用内联汇编，但它不能被求值。
- ¶2.34：`va_arg`。¶4 另外规定，求值 `va_start` 时常量性未指定。
- ¶2.35：**非常量库调用**（non-constant library call，[[defns.nonconst.libcall]]），即库规定会阻止 E 成为核心常量表达式的那些调用，例如库规格中 *Constant When* 元素（[[structure.specifications]]）给出的条件不满足时。
- ¶2.36：`goto` 语句。注 2 说明，标准中用等价的 goto 来描述的语句（如 `while` 的语义）不算在内，循环当然可以在常量求值中执行。C++23（[[P2242R3]]）起 constexpr 函数可以含有 `goto` 和标号，只要求值时不执行它。

```cpp
constexpr int gt(int n) {
    if (n < 0) goto bad;     // C++23 起可以出现
    return n;
bad:
    return 0;
}
constexpr int a = gt(1);     // OK：goto 未被求值
constexpr int b = gt(-1);    // error: ¶2.36
```

为什么禁止 `goto`？主要出于历史和实现成本的考虑：常量求值器通常是基于 AST 的树遍历解释器，任意跳转（尤其是跳入作用域）实现起来很复杂，而 `goto` 能表达的东西都能用结构化控制流替代。这是一条策略性的禁令，并非语义上的必要。

### 未指定结果的比较（¶2.28–2.29）

¶2.28：结果未指定的三路比较、关系运算、相等运算。最典型的是比较两个无关对象的地址：

```cpp
int g1, g2;
constexpr bool c1 = &g1 < &g2;     // error: 无关对象地址的大小关系未指定
constexpr bool c2 = &g1 == &g2;    // OK：false（不同对象地址必然不同）
```

¶2.29 处理**可能非唯一对象**（potentially non-unique object，[[intro.object#9]]），包括字符串字面量对象、`initializer_list` 的后备数组、数组类型的模板参数对象。实现可以让它们共享存储（合并相同或重叠的字面量），所以 `"foo" == "foo"` 在运行期可能是 true，也可能是 false。规则是：用相等运算比较两个指向可能非唯一对象的指针时，如果两个指针值关联于不同的求值（[[basic.compound#4]]），并且

- 它们可能指向同一个可能非唯一对象内的同一偏移，或者
- 其中之一指向的对象类型具有 constexpr-unknown 表示（¶1），

那么表达式不是核心常量表达式。

```cpp
constexpr const char* f() { return "foo"; }

constexpr bool b1 = +"foo" == "foo";              // error: 两次求值可能合并
constexpr bool b2 = f() == f();                   // error: f 中的字面量每次求值可能是不同对象
constexpr const char* p = f();
constexpr bool b3 = p == p;                       // OK：同一个指针值，true
constexpr bool b4 = "xfoo" + 1 == "foo\0y";       // error: 可能被合并进 "xfoo\0y"
constexpr bool b5 = "foo" == "bar" + 0;           // OK：false，内容不同不可能重叠
constexpr bool b6 = (const char*)"foo" == "oo";   // OK：false，即使合并，偏移也不同
```

值得注意的是 `b5` 与 `b6`：编译器可以证明两者不可能指向同一位置（内容不同，或者合并后偏移必然不同），所以结果确定为 false。而 `b4` 中 `"xfoo"+1` 和 `"foo\0y"` 的前四个字符完全一致，二者可以被放在同一块存储里，结果取决于实现。

标准例子中还有：

```cpp
#include <initializer_list>
constexpr std::initializer_list<int *> il1 = { (int *)nullptr };
constexpr std::initializer_list<unsigned long> il2 = { 0 };
constexpr bool b7 = il1.begin() == (void *)il2.begin();   // error
```

`int*` 是具有 constexpr-unknown 表示的类型：空指针的位模式未必是全零，编译器在翻译期不知道 `{nullptr}` 和 `{0UL}` 的后备数组字节是否相同，因此不能排除它们被合并。（本站测试的 Clang 23 接受 `b7`，未实现这条较新的规则。）

### constexpr-unknown 对象上的 `dynamic_cast` / `typeid`（¶2.30）

对动态类型为 constexpr-unknown（¶9）的对象做 `dynamic_cast` 或多态 `typeid`，表达式不是核心常量表达式，因为编译器不知道它实际是什么类型。见 ¶9 的例子。

### 注入声明（¶2.32）

{{c++26}} 如果表达式会产生注入声明（injected declaration，如 `std::meta::define_aggregate`），那么除非 E 是 *consteval-block-declaration*（`consteval { ... }`）对应的表达式，否则它不是核心常量表达式。这样，修改程序本身的能力就被限定在一个明确的、求值时机确定的语法位置。详见 [[expr.const.reflect]]。

## 运行期未定义行为（¶3）

!!! std
    It is implementation-defined whether E is a core constant expression if E satisfies the constraints of a core constant expression, but evaluation of E has runtime-undefined behavior.

    如果 E 满足核心常量表达式的约束，但 E 的求值具有运行期未定义行为，则 E 是否是核心常量表达式由实现定义。

**运行期未定义行为**（runtime-undefined behavior，[[intro.defs]] 3.51）是 C++23 引入的术语：它在运行期是 UB，在常量求值中是否使表达式非常量由实现定义，此外没有其他效果。目前唯一的来源是假设（assumption）：`[[assume(expr)]]` 中的 `expr` 会求值为 false 的情形（[[dcl.attr.assume]]）。

为什么不像 ¶2.8 那样强制诊断？因为假设表达式不被求值，检查它意味着编译器要额外求值一个可能很昂贵、甚至有副作用的表达式，所以标准把选择权交给实现。

```cpp impl
constexpr int as(int x) {
    [[assume(x > 0)]];
    return x;
}
constexpr int e = as(-1);   // 实现定义：Clang 拒绝（"assumption evaluated to false"）
```

## 库 UB 与 `va_start`：未指定（¶4）

如果 E 满足核心常量表达式的约束，但会求值：

- ¶4.1 第 16 章（库）至第 33 章中规定的具有 UB 的操作，或
- ¶4.2 `va_start`，

则 E 是否为核心常量表达式是**未指定**的。

这条与 ¶2.8 形成对照：核心语言 UB 必须诊断，库 UB 则不保证。理由很现实：要求每个库实现在常量求值中检查所有前置条件，代价太高（C++26 的加固前置条件与 contracts 正在改变这一局面）。实践中，`std::array<int,3>{}[3]` 之类的代码在常量求值中通常会被拒绝，因为库实现内部最终执行了核心语言层面的越界访问，但这只是实现的副产品，并不是 ¶4 的保证。

## 标准例子：生命期始于何处（¶5）

¶5 的例子把生命期始于 E 之内这一点讲得很透彻：

```cpp
int x;                                   // 非常量
struct A {
    constexpr A(bool b) : m(b ? 42 : x) { }
    int m;
};
constexpr int v = A(true).m;             // OK：只读到 42
constexpr int w = A(false).m;            // error: 读取 x

constexpr int f1(int k) {
    constexpr int x = k;   // error: k 的生命期始于 x 的初始化器之外
    return x;
}
constexpr int f2(int k) {
    int x = k;             // OK：非 constexpr 局部变量不要求常量初始化器
    return x;
}

constexpr int incr(int& n) { return ++n; }
constexpr int g(int k) {
    constexpr int x = incr(k);   // error: 修改 k，而 k 的生命期始于 incr(k) 之外
    return x;
}
constexpr int h(int k) {
    int x = incr(k);             // OK
    return x;
}
constexpr int y = h(1);          // OK：在求值 h(1) 时，k 的生命期始于 h(1) 之内
```

要点在于**E 指的是哪个表达式**。在 `f1` 中，`constexpr int x = k;` 自己就是一个独立的常量表达式上下文，E 是 `k`，而形参 `k` 的生命期不在 E 之内，无论 `f1` 本身是否在常量求值中被调用都是如此。constexpr 函数的形参不是常量表达式，精确的原因就在这里。而在 `y = h(1)` 中，E 是 `h(1)`，形参 `k` 是这次求值创建的，可以随意修改。

```cpp error
#include <array>
constexpr int size_of(int n) {
    std::array<int, n> a{};   // error: n 不是常量表达式（同 f1）
    return a.size();
}
```

## 两条视同规则（¶6–¶7）

- ¶6：判断时忽略 `std::allocator<T>` 成员函数函数体的求值（上文已述）。
- ¶7：对联合体平凡的复制/移动构造函数或赋值运算符的调用，视为复制/移动其活跃成员（若有）。平凡复制在运行期就是 `memcpy`，但常量求值器没有字节的概念，于是标准把它解释为复制活跃成员，活跃成员也随之转移。

```cpp ok
union U { int i; float f; };
constexpr float h() {
    U a{.f = 1.5f};
    U b = a;         // 平凡复制 ≡ 复制活跃成员 f，b 的活跃成员是 f
    return b.f;      // OK
}
static_assert(h() == 1.5f);
```

## 结构化绑定在常量求值中的语义（¶8）

对命名结构化绑定 v 的 *id-expression*：

- ¶8.1 如果 v 是绑定到某个虚构引用 r 的左值（tuple-like 协议情形，见 [[dcl.struct.bind]]），则行为如同指名了 r；
- ¶8.2 否则 v 指代数组元素或类成员，行为如同求值 `e[i]` 或 `e.m`，其中 e 是结构化绑定声明引入的那个无名变量。

这样，结构化绑定在常量求值中的行为完全由它实际指代的东西决定：

```cpp
#include <tuple>
struct S {
    mutable int m;
    constexpr S(int m) : m(m) {}
    virtual int g() const;
};
void f(std::tuple<S&> t) {
    auto [r] = t;
    static_assert(r.g() >= 0);        // error: 动态类型为 constexpr-unknown（¶2.6）
    constexpr auto [m] = S(1);
    static_assert(m == 1);            // error: 等价于 e.m，读 mutable 子对象
    using A = int[2];
    constexpr auto [v0, v1] = A{2, 3};
    static_assert(v0 + v1 == 5);      // OK：等价于 e[0] + e[1]
}
```

{{c++26}} `constexpr` 结构化绑定本身是 C++26 的新特性（[[P2686]]）。

## constexpr-unknown：未知的引用与对象（¶9）

这条规则由 [[P2280R4]] 引入，C++26 又做了进一步完善。它解决了一个长期令人困惑的问题：

```cpp
#include <cstddef>
template <typename T, std::size_t N>
constexpr std::size_t array_size(T (&)[N]) { return N; }

void use_array(int const (&gold_medal_mel)[2]) {
    constexpr auto gold = array_size(gold_medal_mel);   // C++20：error！C++23 起：OK
}
```

`array_size` 根本不读数组，只用模板参数 N。但在 C++20 中，把引用形参 `gold_medal_mel` 作为实参传递需要求值这个 *id-expression*，而引用只有在被常量初始化时才能在常量表达式中使用，形参显然不满足。结果是这段看似显然正确的代码不合法（`std::size(arr)` 也有同样的问题）。

¶9 的新规则是：在把 E 作为核心常量表达式求值时，所有指代生命期不始于 E 之内的对象或引用的 *id-expression*、*splice-expression* 和 `*this`：

- 被视为指代该对象或引用的某个特定实例，其生命期（以及所有子对象，包括所有联合体成员的生命期）覆盖整个常量求值；
- 若该对象不可用于常量表达式，其动态类型是 **constexpr-unknown**；
- 若该引用不可用于常量表达式，则视为绑定到被引用类型的一个未指定对象，其生命期覆盖整个求值，动态类型为 constexpr-unknown。

换句话说，编译器可以拿着一个未知的引用或对象做不需要它的值的事情，比如取地址、传递、调用非虚成员函数（只要那个函数不读成员）、`sizeof`；但一旦需要读值、调用虚函数、做 `dynamic_cast`/`typeid`，就会命中黑名单。

```cpp
#include <typeinfo>
struct Swim {
    constexpr int phelps() { return 28; }
    virtual constexpr int lochte() { return 12; }
    int coughlin = 12;
};

constexpr int how_many(Swim& swam) {
    Swim* p = &swam;
    return (p + 1 - 1)->phelps();
}

void splash(Swim& swam) {
    static_assert(swam.phelps() == 28);          // OK：不读 swam 的任何值
    static_assert((&swam)->phelps() == 28);      // OK
    Swim* pswam = &swam;
    static_assert(pswam->phelps() == 28);        // error: 读取指针变量 pswam（¶2.10）
    static_assert(how_many(swam) == 28);         // OK：p 是求值内创建的局部变量
    static_assert(Swim().lochte() == 12);        // OK：动态类型已知
    static_assert(swam.lochte() == 12);          // error: ¶2.6，动态类型 constexpr-unknown
    static_assert(swam.coughlin == 12);          // error: ¶2.10，读取不可用于常量表达式的对象
}

extern Swim dc;
extern Swim& trident;
constexpr auto& sandeno   = typeid(dc);          // OK：dc 是对象，其动态类型只能是 Swim
constexpr auto& gallagher = typeid(trident);     // error: ¶2.30
```

注意 `sandeno` 与 `gallagher` 的区别。`trident` 是引用，按 ¶9，它绑定到一个动态类型为 constexpr-unknown 的未指定对象，实际可能绑定到 `Swim` 的某个派生类对象。多态 `typeid` 需要动态类型（[[expr.typeid#4]]），于是命中 ¶2.30。而 `dc` 是一个声明为 `Swim` 类型的对象变量。变量声明的对象必然是完整对象，其最终派生类型只能是 `Swim` 本身，所以标准例子注明 "can only be typeid(Swim)"，判为 OK（Clang 也接受）。

!!! lawyer "措辞与例子的出入"
    ¶9 第二句说，对于这样一个不可用于常量表达式的对象，其动态类型是 constexpr-unknown。按字面读，`typeid(dc)` 也应命中 ¶2.30，标准例子却判为 OK。合理的解读是：对于由变量直接声明的完整对象，constexpr-unknown 的动态类型仍然只能是声明类型，`typeid` 不需要真正知道什么。这类措辞与例子不一致的情况在草案中并不罕见。读者可以以例子体现的意图为准，但应意识到规范文字本身并没有把话说死。

另一个例子说明 lambda 的情形：

```cpp ok
constexpr auto olympic_mile() {
    const int ledecky = 1500;
    return [] { return ledecky; };    // 不捕获：ledecky 可用于常量表达式，读值不是 odr-use
}
static_assert(olympic_mile()() == 1500);
```

!!! history "P2280 作为 DR"
    [[P2280R4]] 在 C++23 周期被采纳，并作为缺陷报告（DR）追溯适用于更早的标准模式。主流编译器在近几个大版本中陆续实现了它；在较旧的编译器上，上面 `use_array` 中的 `array_size(gold_medal_mel)` 会被拒绝。C++26 草案又补上了 `*this`、*splice-expression*，以及所有联合体成员的生命期都覆盖整个求值等细节。

## 实现视角

!!! impl "常量求值器是一个解释器"
    - **Clang** 的常量求值器传统上是 `ExprConstant.cpp` 里的 AST 遍历解释器，它为每个对象维护 `APValue`，跟踪生命期、活跃联合体成员，并用基对象加路径的形式表示指针，因此能精确检测越界、悬空、类型双关。新的字节码解释器（`-fexperimental-new-constant-interpreter`）正在逐步替代它。
    - **GCC** 的 `constexpr.cc` 同样是 AST 级解释器，有 constexpr 调用缓存（相同实参的调用只求值一次）。
    - **MSVC** 有自己的常量求值器，在细节（例如 ¶2.29 字符串字面量比较）上历来与另两家存在差异。
    - 三者的共同点是：指针不是整数，而是由某个对象加偏移构成的符号值。所以 `reinterpret_cast`、指针转整数、比较无关对象的地址都无法支持，求值器里根本没有地址值。

## 陷阱

!!! pitfall "constexpr 函数里的 UB 只在常量求值时被诊断"
    同一个 `add(INT_MAX, 1)`，在 `constexpr int x = ...` 里是编译错误，在 `int x = ...` 里则是运行期 UB，编译器不会给出任何提示。constexpr 函数通过了 static_assert 测试，只说明那几组实参没有 UB。

!!! pitfall "非常量 ≠ 编译错误"
    在不要求常量的上下文中（如 `const int n = f();`、命名空间作用域的 `int x = f();`），如果表达式因黑名单而不是常量，它只是不声不响地变成动态初始化，程序仍然合法。如果你依赖它一定在编译期计算，请用 `constexpr` 或 `constinit`。

!!! pitfall "形参永远不是常量表达式"
    `constexpr void f(int n) { static_assert(n > 0); }` 永远是错的，哪怕 f 只在常量求值中被调用。¶5 解释了原因：`static_assert` 的条件是独立的常量表达式 E，形参 n 的生命期不在 E 之内。要把值作为常量传入，应当用模板参数（或 C++26 反射、`std::constant_wrapper` 一类的技巧）。

## 思考题

!!! question "思考题 1"
    下面哪些 `static_assert` 合法？

    ```cpp
    struct P { int x; constexpr int get() const { return 7; } };
    void f(P& r, P v) {
        static_assert(r.get() == 7);   // (a)
        static_assert(v.get() == 7);   // (b)
        static_assert(&r == &r);       // (c)
        static_assert(v.x == v.x);     // (d)
    }
    ```

<details markdown="1">
<summary>答案</summary>

- (a) OK：按 ¶9，r 视为绑定到一个未指定的 `P` 对象；调用非虚成员函数 `get` 时，`this` 出现在被求值的 constexpr 函数内（¶2.1.1），而 `get` 不读任何成员。
- (b) OK：同理，v 是生命期不始于 E 的对象，按 ¶9 视为某个特定实例。
- (c) OK：两侧都指代同一个特定实例，取地址不读值，比较结果确定为 true。
- (d) error：读取 `v.x` 是对一个不可用于常量表达式、生命期也不始于 E 的对象的左值到右值转换（¶2.10）。

在 P2280 之前，(a) 和 (c) 也是 error，因为它们需要求值引用 r，而 r 不是用常量表达式初始化的引用；(b) 则一向是 OK 的（`std::array` 对象调 `size()` 的经典用法）。本站测试的 Clang 23 的结果与上面的分析一致。
</details>

!!! question "思考题 2"
    为什么下面的程序中 `a` 是良构的，而 `b` 不是？

    ```cpp
    constexpr int f(int* p) { return p ? *p : 0; }
    constexpr int a = f(nullptr);
    int g = 1;
    constexpr int b = f(&g);
    ```

<details markdown="1">
<summary>答案</summary>

`f(nullptr)` 中的 `*p` 根本没有被求值，而黑名单只看求值。`f(&g)` 中的 `&g` 本身没问题（g 有静态存储期，取地址得到常量），但 `*p` 是对 `g` 的左值到右值转换，而 `g` 既不可用于常量表达式（不是 const），生命期也不始于本次求值，所以命中 ¶2.10。
</details>

!!! question "思考题 3"
    `constexpr std::string s = "hi";` 在不同标准库下行为可能不同，为什么？

<details markdown="1">
<summary>答案</summary>

这取决于 `std::string` 实现是否在常量求值中对短字符串使用 SSO（短字符串优化，存储在对象内部，不分配）。如果使用 SSO，就没有动态分配，`s` 的初始化是常量表达式；如果实现在常量求值中总是分配（libc++ 的较早版本据报道如此），就是非瞬时分配（¶2.20），ill-formed。标准并不保证任何一种结果，所以这种代码不可移植；长字符串则在所有实现上都不行。本站测试的 libc++（随 Clang 23）接受 `"hi"`，拒绝超过 SSO 容量的字符串。
</details>

## 小结

| 想在常量求值中做的事 | 何时允许 | 条目 |
|---|---|---|
| 读一个变量 | 它可用于常量表达式，或生命期始于本次求值 | ¶2.10 |
| 写一个变量 | 它的生命期始于本次求值 | ¶2.18 |
| 调用函数 | constexpr、已定义、非协程实例化 | ¶2.3–2.5 |
| 调虚函数 / `dynamic_cast` / `typeid` | 动态类型已知（不是 constexpr-unknown） | ¶2.6、¶2.30 |
| `new` / `delete` | 本次求值内配对（瞬时分配） | ¶2.20–2.23 |
| placement new | 存储在本次求值内获得 {{c++26}} | ¶2.20.2 |
| `static_cast` 自 `void*` | 指向的对象类型与目标相似 {{c++26}} | ¶2.15 |
| 抛异常 | 本次求值内抛出并处理完 {{c++26}} | ¶2.24–2.25 |
| `reinterpret_cast`、`goto`、`asm`、协程 | 永不（求值时） | ¶2.16、¶2.36、¶2.33、¶2.26 |
| 任何核心语言 UB / EB | 永不（必须诊断） | ¶2.8 |
| 库 UB | 未指定 | ¶4 |
| `[[assume]]` 为假 | 实现定义 | ¶3 |
