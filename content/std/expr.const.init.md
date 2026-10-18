---
title: 常量初始化
summary: 变量的组成值与组成引用、constexpr-referenceable 与 constexpr-representable（C++26）、constant-initializable / constant-initialized，以及可用于常量表达式的变量与对象。这些是静态初始化与 constexpr 变量的基础
status: done
papers: P2686, P1143R2, P0595R2
related: expr.const.core, expr.const.defns, basic.start.static, basic.start.dynamic, dcl.constexpr, dcl.constinit, topics/compile-time-programming
tags: 常量求值, 初始化, constinit, 静态初始化
updated: 2026-10-17
---

本节回答关于变量的两个问题：

1. 变量 v 的初始化能否在编译期完成？这就是 **constant-initialized**（¶4–¶5）。对静态或线程存储期变量，它决定变量做静态初始化还是动态初始化（[[basic.start.static#2]]）；对 constexpr 变量和 `constinit` 变量，它都是必须满足的要求（[[dcl.constexpr#6]]、[[dcl.constinit]]）。
2. 在程序点 P 处，常量求值能否读取 v 的值？这就是 **usable in constant expressions**（¶6–¶9），也是 [[expr.const.core#2.10]] 允许左值到右值转换的条件。

C++26 通过 [[P2686]]（constexpr 结构化绑定与对 constexpr 变量的引用）重写了本节，引入 constexpr-referenceable 与 constexpr-representable 两个概念，取代了 C++23 中"常量表达式的允许结果必须具有静态存储期"的规则。下面逐段读。

## 组成值与组成引用（¶1）

变量 x 的**组成值**（constituent values）与**组成引用**（constituent references）定义如下：

- ¶1.1 如果 x 声明的是对象，那个对象的组成值和组成引用（[[intro.object]]：对象展开后所有标量子对象的值与所有引用成员）就是 x 的组成值和组成引用；
- ¶1.2 如果 x 声明的是引用，这个引用本身就是 x 的组成引用。

此外，如果 x 的某个组成引用 r 绑定到一个生命期延长到 r 的临时对象（或其子对象），那个临时对象的组成值与组成引用也递归地算作 x 的。

为什么要把临时对象算进来？考虑 `constexpr const int& r = 42;` 或 `struct A { const int& r; }; constexpr A a{2};`。生命期延长后的临时对象与变量同时存在、同时消亡，它的内容就是变量内容的一部分，判断变量能否在编译期确定时必须一起检查。

## constexpr-referenceable（¶2）{{c++26}}

如果满足下列条件之一，就说对象 o 从程序点 P **constexpr-referenceable**（可被 constexpr 引用）：

- ¶2.1 o 具有静态存储期；
- ¶2.2 o 具有自动存储期，并且令 v 为 o 的完整对象对应的变量（或 o 的生命期所延长到的那个变量），包含 v 的最小非块作用域与包含 P 的最小非块作用域是同一个函数形参作用域（寻找最小作用域时，跳过块作用域和与 *requirement-parameter-list* 关联的形参作用域）。

直观地说，只有当引用者与一个自动变量处在同一次函数调用中时，才能以常量的方式引用这个变量的地址。原因如下：

- 函数内部的所有块共享同一个栈帧，在同一个函数体内的任何地方，局部变量 `x` 的地址都指同一个东西。所以 `constexpr int* p = &x;`（p 也在这个函数里）是有意义的：每次调用，p 都指向这次调用的 x。编译器可以把 p 实现为 x 的栈偏移，不需要运行期存储。
- 如果 P 在一个嵌套的 lambda 体内，情况就不同了。lambda 的调用是另一个栈帧（另一个函数形参作用域），外层的 x 在那里不是同一次函数调用中的对象，而且 lambda 可能被带到别处调用。
- 线程存储期对象永远不是 constexpr-referenceable 的：每个线程有各自的实例，地址在编译期没有统一的含义。

标准例子：

```cpp
struct A {
    int m;
    const int& r;
};
void f() {
    static int sx;
    thread_local int tx;                // tx 永远不是 constexpr-referenceable
    int ax;
    A aa = {1, 2};
    static A sa = {3, 4};
    // 在这里：sx、ax、aa.m、sa.m，以及 aa.r 和 sa.r 绑定的临时对象，
    // 都是 constexpr-referenceable 的
    auto lambda = [] {
        int ay;
        // 在这里：sx、sa.m、ay，以及 sa.r 绑定的临时对象是 constexpr-referenceable 的；
        // ax 与 aa 不是（它们属于外层 f 的形参作用域）
    };
}
```

跳过 *requirement-parameter-list* 的形参作用域是一个细节：`requires (T t) { ... }` 里的形参作用域并不对应真正的函数调用，不应因此把 f 的局部变量隔开。

## constexpr-representable（¶3）{{c++26}}

如果对象或引用 x 的每个指向对象 o（或越过 o 末尾）的组成值、每个引用对象 o 的组成引用都满足 o 从 P constexpr-referenceable，就说 x 在程序点 P **constexpr-representable**（可被 constexpr 表示）。

换句话说，从 P 看来，x 里所有的指针和引用都指向可以常量地引用的对象。这是对 C++23 中常量表达式允许结果的推广（那里要求指针指向静态存储期对象）：静态存储期对象在任何地方都可以引用，自动对象只能在同一次函数调用内引用。

## constant-initializable（¶4）

如果满足下列条件，变量 v 就是 **constant-initializable**（可常量初始化）的：

- ¶4.1 把其初始化的完整表达式当作 *constant-expression* 解释时，它是常量表达式，其中所有契约断言（contract assertion）都按 *ignore* 求值语义处理（[[basic.contract.eval]]）{{c++26}}；
- ¶4.2 紧接 v 的初始化声明之后，v 声明的对象或引用 x 是 constexpr-representable 的；
- ¶4.3 如果 x 具有静态或线程存储期，那么在初始化声明之后第一个直接作用域为命名空间作用域的程序点处，x 也是 constexpr-representable 的。

逐条看。

¶4.1 是传统的要求，即初始化器是常量表达式。这一条附有两个注：

- 注 1：做这个判断时，`std::is_constant_evaluated()` 的值为 true。也就是说，编译器先假设这是常量求值，据此试算初始化器；试算失败，再按运行期方式（`is_constant_evaluated()` 为 false）进行动态初始化。`std::is_constant_evaluated()` 的种种反直觉行为都源于此，见 [[expr.const.defns]]。
- 注 2 {{c++26}}：判断时忽略契约断言；但如果初始化确实是显然常量求值的，翻译期的实际求值仍可以用其他求值语义检查契约，违反时导致诊断或程序 ill-formed。因此，契约检查失败本身不会把常量初始化悄悄变成动态初始化。

¶4.2 与 ¶4.3 是 C++26 新增的可表示性检查：

```cpp
namespace N {
    void f() {
        int x;
        constexpr int& ar = x;           // OK（C++26）：从 ar 的声明之后看，x 可被 constexpr 引用
        static constexpr int& sr = x;    // error: sr 具有静态存储期，¶4.3 要在命名空间作用域的点检查，
                                         //        那里 x（自动变量）不可被 constexpr 引用
    }
}
```

`sr` 的错误很好理解：静态变量保存了某次调用中局部变量的引用，到下一次调用时这个引用就悬空了。¶4.3 规定在下一个命名空间作用域的点检查，把这个直觉形式化：静态变量的可见范围超出了任何一次函数调用。

!!! impl "实现状态"
    本站测试的 Clang 23 仍按 C++23 规则拒绝上例中的 `ar`（"constexpr variable 'ar' must be initialized by a constant expression"）。在 C++23 中 `ar` 确实是 ill-formed 的，因为引用的允许结果必须是静态存储期对象。

## constant-initialized（¶5）

一个 constant-initializable 的变量，如果有初始化器，或者其类型是 **const-default-constructible** 的（[[dcl.init.general]]：类类型，且默认初始化会初始化所有成员，例如有用户提供的默认构造函数），就是 **constant-initialized**（已常量初始化）的。

为什么需要这一条？`static int sx;` 没有初始化器，默认初始化什么也不做（随后的零初始化由 [[basic.start.static]] 另行处理）。它没有经历用常量表达式初始化的过程，因此不算 constant-initialized。

标准例子（展示 ¶2–¶5 的综合效果）：

```cpp
void f() {
    int ax = 0;                   // constant-initialized
    thread_local int tx = 0;      // constant-initialized
    static int sx;                // 不是：没有初始化器，int 不是 const-default-constructible
    static int& rss = sx;         // constant-initialized：sx 是静态的
    static int& rst = tx;         // 不是：tx 是线程局部的，永远不可被 constexpr 引用
    static int& rsa = ax;         // 不是：静态引用指向自动变量（¶4.3）
    thread_local int& rts = sx;   // constant-initialized
    thread_local int& rtt = tx;   // 不是
    thread_local int& rta = ax;   // 不是
    int& ras = sx;                // constant-initialized
    int& rat = tx;                // 不是
    int& raa = ax;                // constant-initialized（C++26）：同一函数调用内
}
```

注意 `ax`、`raa` 这些自动变量也可以是 constant-initialized 的。这个概念不只服务于静态初始化，也服务于可用于常量表达式的判断（¶7）。

### 对静态存储期变量的后果：静态初始化

[[basic.start.static#2]] 规定：静态或线程存储期变量如果是 constant-initialized 的，就执行**常量初始化**，否则先执行零初始化。常量初始化与零初始化合称**静态初始化**，其余的都是动态初始化；所有静态初始化都 strongly happens before 任何动态初始化。

实际后果：

| | 常量初始化 | 动态初始化 |
|---|---|---|
| 何时完成 | 程序开始前（值直接写在 `.data`/`.rodata` 中） | 运行期：`main` 之前（命名空间作用域）或首次经过时（块作用域 `static`） |
| 初始化顺序问题 | 无 | 跨 TU 的顺序未指定（静态初始化顺序问题） |
| 块作用域 `static` | 不需要守卫变量 | 需要线程安全的守卫变量（`__cxa_guard_acquire`） |
| `thread_local` | 无需 TLS 初始化包装函数 | 每次跨 TU 访问可能经过 TLS wrapper 函数 |

```cpp title="a.cpp"
int compute();                  // 定义在别处，非 constexpr
int b_val = compute();          // 动态初始化
```

```cpp title="b.cpp"
extern int b_val;
int a_val = b_val + 1;          // 动态初始化；b_val 可能尚未初始化（此时读到 0）
```

把 `b_val` 改为常量初始化（`constinit int b_val = 41;`，或用 constexpr 函数计算）就消除了顺序问题，因为它在任何动态初始化之前就已就绪。

!!! tip "constinit：把常量初始化变成断言"
    `constinit`（C++20，[[P1143R2]]）要求变量具有静态初始化，否则程序 ill-formed（[[dcl.constinit#2]]）。它不像 `constexpr` 那样隐含 `const`，变量之后可以修改。典型用途：

    ```cpp
    constinit int counter = 0;                     // 可变的全局计数器，保证无初始化顺序问题
    constinit thread_local int tls_depth = 0;      // 跨 TU 访问时编译器可以省去 TLS wrapper
    extern constinit int late;                     // 在声明处加 constinit，告诉其他 TU 无需检查初始化
    ```

### 实现可以提前做静态初始化

[[basic.start.static#3]] 允许实现把本应动态初始化的变量改为静态初始化，条件是：（3.1）动态版本不会在初始化之前改变其他静态或线程存储期对象；（3.2）静态版本产生的值，与所有不要求静态初始化的变量都做动态初始化时的值相同。所以一个变量不是 constant-initialized，并不意味着它一定在运行期初始化，只是没有保证。这也是不能根据有没有在 `main` 之前打印来推断常量性的原因。

## potentially-constant（¶6）

如果变量是 `constexpr` 的，或者具有引用类型，或者具有非 volatile 的 const 限定的整型或枚举类型，它就是 **potentially-constant**（潜在常量）的。

这是可用于常量表达式的类型门槛。它保留了 C++ 一条历史悠久的特例：`const int n = 10;` 不需要 `constexpr` 就能用作数组边界（C++98 起），而 `const double d = 1.0;` 不能用于常量表达式。

## 可用于常量表达式的变量（¶7）

如果变量 V 是 constant-initialized 且 potentially-constant 的，V 的初始化声明 D 从 P 可达，并且满足下列条件之一，就说 V 在点 P **可用于常量表达式**（usable in constant expressions）：

- ¶7.1 V 是 constexpr；
- ¶7.2 V 没有被初始化为 TU-local 值（[[basic.link]]）；
- ¶7.3 P 与 D 在同一个翻译单元中。

```cpp
const int a = 10;           // constant-initialized + const int → 可用于常量表达式
int arr1[a];                // OK

int rt();
const int b = rt();         // 不是 constant-initialized → 不可用
int arr2[b];                // error（或 VLA 扩展）

const int c = 10;
int& rc = const_cast<int&>(c);   // 引用类型 → potentially-constant；绑定到静态对象 → constant-initialized
static_assert(rc == 10);    // OK：rc 可用于常量表达式，它指代的 c 也可用，读取被 [expr.const.core]/2.10 放行
```

可达（reachable）的要求：

```cpp
extern const int late;
static_assert(late == 1);   // error: late 的初始化声明此处不可达
const int late = 1;
static_assert(late == 1);   // OK
```

¶7.2–7.3 关于 TU-local 的规则主要服务于模块。一个导出的 `const int&` 变量如果绑定到内部链接的对象（TU-local 实体），在其他翻译单元中就不应当作常量使用，否则不同 TU 看到的常量可能指向不同的实体。constexpr 变量不受此限制（¶7.1），因为 constexpr 变量的值必须在任何地方都能得到一致的理解。

## 可用于常量表达式的对象与引用（¶8–¶9）

¶8：如果对象或引用属于下列情形之一，它在 P **潜在可用于常量表达式**（potentially usable in constant expressions）：

- ¶8.1 在 P 可用于常量表达式的变量所声明的对象或引用；
- ¶8.2 非 volatile const 限定的字面类型临时对象，且其生命期延长到某个在 P 可用于常量表达式的变量；
- ¶8.3 模板参数对象（[[temp.param]]）；
- ¶8.4 字符串字面量对象（[[lex.string]]）；
- ¶8.5 上述任一者的非 mutable 子对象；
- ¶8.6 上述任一者的引用成员。

¶9：如果对象或引用潜在可用于常量表达式，并且在 P 是 constexpr-representable 的，它就在 P 可用于常量表达式。

```cpp
struct A { int m; const int& r; };
constexpr A ga = {1, 2};       // 临时对象 2 的生命期被延长到 ga
static_assert(ga.r == 2);      // OK：¶8.2 + ¶8.6

constexpr const char* s = "abc";
static_assert(s[1] == 'b');    // OK：¶8.4 字符串字面量对象

struct M { mutable int x; };
constexpr M mm{1};
static_assert(mm.x == 1);      // error: mutable 子对象被 ¶8.5 排除
```

¶9 的 constexpr-representable 条件处理的是 C++26 才出现的情形：constexpr 变量里存了指向局部变量的指针，它在另一次函数调用（例如 lambda）中不可用。

```cpp
struct A { int* const& r; };
void f(int x) {
    constexpr A a = {&x};
    static_assert(a.r == &x);             // OK（C++26）
    [&] {
        static_assert(a.r != nullptr);    // error: 在 lambda 中，a.r 引用的临时对象存着 &x，
                                          //        而 x 在 lambda 的形参作用域中不可被 constexpr 引用
    }();
}
```

!!! impl "实现状态"
    本站测试的 Clang 23 在 `constexpr A a = {&x};` 处就报错（按 C++23 规则，指向自动变量的指针不是允许的结果），因此后续两条 `static_assert` 也都失败。

## 与 is_constant_evaluated 的交互（概要）

¶4.1 注 1 规定判断时 `is_constant_evaluated()` 为 true，因此静态存储期变量的初始化分两个阶段：先按常量试算，失败了再按运行期执行。

```cpp ok
#include <type_traits>
int y;
const int a = std::is_constant_evaluated() ? y : 1;   // 试算：读 y 失败 → 动态初始化，a == 1
const int b = std::is_constant_evaluated() ? 2 : y;   // 试算：得 2，成功 → 静态初始化，b == 2
```

`a` 的结果尤其反直觉：表达式中出现了 `is_constant_evaluated()`，最终却在运行期求值（得 false，于是取 1）。完整分析见 [[expr.const.defns]]。

!!! warning "Clang 的警告不完全准确"
    Clang 对上面两行都会给出 `-Wconstant-evaluated` 警告，称 `is_constant_evaluated` "will always evaluate to 'true' in a manifestly constant-evaluated expression"。对 `a` 而言这并不成立：`a` 最终是动态初始化的，运行时 `is_constant_evaluated()` 返回 false。这条警告的本意是提醒这种用法很可能不是你想要的。

## 历史与演进

!!! history "从允许的结果到 constexpr-representable"
    - C++11：常量初始化就是用常量表达式初始化；引用必须绑定到静态存储期对象或函数。
    - C++20：引入 `constinit`（[[P1143R2]]）和 `std::is_constant_evaluated()`（[[P0595R2]]）。为了定义后者的行为，标准引入了显然常量求值和试算的表述（即 ¶4.1 注 1 的前身）。
    - C++23：可用于常量表达式的定义已基本是 ¶7–¶9 的形状，但常量表达式的结果不能指向自动变量。
    - C++26：[[P2686]] 引入 constexpr-referenceable / constexpr-representable，允许 `constexpr int& r = local;`，并使 constexpr 结构化绑定成为可能；判断时契约断言按 ignore 语义处理。

## 陷阱

!!! pitfall "constexpr 变量 ≠ 静态变量"
    函数内的 `constexpr int arr[1000] = {...};` 是自动存储期变量，每次调用都可能在栈上构造一份。编译器通常会优化为从 `.rodata` 复制，甚至直接引用，但标准不保证地址稳定。如果需要唯一的地址，或者要返回它的指针，应写 `static constexpr`。

!!! pitfall "`const` 整型的常量性取决于初始化器"
    `const int n = f();` 中的 n 能否用于常量表达式，完全取决于 `f()` 能否在编译期成功求值。在 `f` 里加一行非 constexpr 的日志调用，远处的 `int arr[n];` 就会出错，而 n 的声明处没有任何诊断。需要常量时写 `constexpr`，需要静态初始化时写 `constinit`。

!!! pitfall "块作用域 static 的常量初始化"
    对于 `static int cache = expensive();`，如果 `expensive()` 是 constexpr 且能成功求值，变量就是常量初始化的，首次经过时**不会**调用 `expensive()`。依赖其副作用（例如打印、计数）的代码，其行为会随编译器能否常量求值而不同。

## 思考题

!!! question "思考题 1"
    以下每个变量是否 constant-initialized？是否可用于常量表达式？

    ```cpp
    struct P { int v; constexpr P() : v(7) {} };
    const P p1;          // (1)
    const int i1 = P().v;// (2)
    const double d1 = 1; // (3)
    int& r1 = const_cast<int&>(i1); // (4)
    ```

<details markdown="1">
<summary>答案</summary>

1. `p1`：没有初始化器，但 P 有用户提供的 constexpr 默认构造函数，是 const-default-constructible 的，初始化是常量表达式，所以是 constant-initialized。但它是类类型，又不是 constexpr，所以不是 potentially-constant，**不可用于常量表达式**（`static_assert(p1.v == 7)` 失败）。
2. `i1`：constant-initialized（`P().v` 是常量表达式），类型是 const int，可用于常量表达式。
3. `d1`：constant-initialized（会做静态初始化），但 `const double` 不是 potentially-constant，不可用于常量表达式。
4. `r1`：引用类型，因此是 potentially-constant；初始化器是引用一个静态存储期对象的常量表达式，因此是 constant-initialized，可用于常量表达式。`static_assert(r1 == 7)` 会读取 `i1`，而 `i1` 可用，所以成立。
</details>

!!! question "思考题 2"
    为什么 ¶2 把线程存储期对象一概排除在 constexpr-referenceable 之外，而静态存储期对象总是可以？

<details markdown="1">
<summary>答案</summary>

静态存储期对象在整个程序中只有一个实例，其地址可以表示为符号加偏移，由链接器或加载器填入，对所有使用者都一致。线程存储期对象每个线程一个实例，地址只能在运行期通过线程指针（TLS 寄存器）计算，不存在一个能写进 `.data` 的统一值，也就无法作为常量存进 constexpr 变量。静态初始化的引用不能绑定到 `thread_local` 对象（例子中的 `rst`），也是同一个原因。
</details>

## 小结

| 概念 | 定义 | 用途 |
|---|---|---|
| constexpr-referenceable {{c++26}} | 静态存储期；或同一函数调用内的自动对象 | ¶3 |
| constexpr-representable {{c++26}} | 所有组成指针/引用的目标都 constexpr-referenceable | constexpr 变量、模板实参 |
| constant-initializable | 初始化器是常量表达式 + 可表示 | constexpr 变量的要求 |
| constant-initialized | constant-initializable 且有初始化器或 const-default-constructible | 静态初始化、constinit |
| potentially-constant | constexpr / 引用 / const 非 volatile 整型或枚举 | 可用性的类型门槛 |
| usable in constant expressions | constant-initialized + potentially-constant + 可达（+TU-local 限制） | [[expr.const.core#2.10]] 的读取许可 |
