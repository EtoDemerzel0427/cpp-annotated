---
title: 常量初始化
summary: 变量的初始化什么时候算常量初始化（决定静态变量在编译期还是运行期初始化），C++26 中常量里的指针和引用可以指向哪里，以及哪些变量可以在常量表达式中读取。
status: done
papers: P2686, P1143R2, P0595R2
related: expr.const.core, expr.const.const, expr.const.defns, basic.start.static, basic.start.dynamic, dcl.constexpr, dcl.constinit, topics/compile-time-programming
tags: 常量求值, 初始化, constinit, 静态初始化
updated: 2026-10-19
---

!!! tldr
    - 静态或线程存储期的变量如果是常量初始化的（constant-initialized），值在程序开始前就已就绪，没有跨翻译单元的初始化顺序问题；否则在运行期动态初始化。`constinit` 把这一点变成编译期检查。
    - 常量初始化的条件是：初始化器是常量表达式，并且变量中的指针和引用都指向从那里能以常量方式引用的对象。
    - C++26 起，constexpr 指针或引用可以指向同一次函数调用中的局部变量，但不能把它存进静态变量，也不能在 lambda 里使用。
    - 变量要在常量表达式中被读取，还必须是 constexpr、引用，或者 const 的整型、枚举类型。`const double` 不行。
    - 判断时 `std::is_constant_evaluated()` 取 true：编译器先按编译期试算初始化器，失败了再改为运行期初始化。

## 编译期初始化与运行期初始化

```cpp title="a.cpp"
int compute();                  // 定义在别处，不是 constexpr
int b_val = compute();          // 动态初始化
```

```cpp title="b.cpp" unspecified
extern int b_val;
int a_val = b_val + 1;          // 动态初始化；b_val 可能还是 0
```

两个翻译单元中动态初始化的先后是未指定的（[[basic.start.dynamic]]）。如果 `a_val` 先初始化，它读到的 `b_val` 只是零初始化的 0。这就是常说的静态初始化顺序问题。

如果 `b_val` 用常量初始化，例如写成 `int b_val = 41;`，问题就不存在了。[[basic.start.static#2]] 规定，静态或线程存储期的变量如果是**常量初始化的**（[[g:constant-initialized]]），就执行常量初始化；否则先零初始化。这两种合称静态初始化，它们都发生在任何动态初始化之前。

| | 常量初始化 | 动态初始化 |
|---|---|---|
| 什么时候完成 | 程序开始前，值直接写在 `.data` 或 `.rodata` 中 | 运行期：命名空间作用域的变量在 `main` 之前，块作用域的 `static` 在控制流第一次经过时 |
| 初始化顺序问题 | 没有 | 跨翻译单元的顺序未指定 |
| 块作用域的 `static` | 不需要守卫变量 | 需要线程安全的守卫变量（Itanium ABI 中是 `__cxa_guard_acquire`） |
| `thread_local` | 不需要初始化包装函数 | 从其他翻译单元访问时可能要经过 TLS 包装函数 |

实现也可以把本应动态初始化的变量提前做成静态初始化，只要结果不变（[[basic.start.static#3]]）。所以一个变量不是常量初始化的，并不说明它一定在运行期初始化，只是没有保证。

!!! tip "constinit：要求常量初始化"
    C++20 的 `constinit`（[[P1143R2]]）要求变量具有静态初始化，否则程序非良构（[[dcl.constinit#2]]）。它不像 `constexpr` 那样隐含 `const`，变量以后可以修改。

    ```cpp
    constinit int counter = 0;                  // 可修改的全局变量，没有初始化顺序问题
    constinit thread_local int tls_depth = 0;   // 从其他翻译单元访问时可以省去 TLS 包装函数

    const char* g() { return "dynamic"; }
    constexpr const char* f(bool p) { return p ? "constant" : g(); }
    constinit const char* c = f(true);          // OK
    constinit const char* d = f(false);         // error: 不是常量初始化
    ```

    `tls_depth` 的那条好处要求其他翻译单元中的声明也带上 `constinit`（`extern constinit thread_local int tls_depth;`），编译器才知道无需检查初始化。

## 什么样的初始化是常量初始化（¶4–¶5）

¶4 如果下面三个条件都满足，变量 v 就是 **constant-initializable**（可常量初始化）的：

1. 把初始化的完整表达式当作一个常量表达式来解释时，它确实是常量表达式（[[expr.const.const]]）；
2. 紧接 v 的初始化声明之后，v 声明的对象或引用是 constexpr-representable 的；
3. 如果它具有静态或线程存储期，那么在初始化声明之后、第一个直接位于命名空间作用域的程序点，它也是 constexpr-representable 的。

第 2、3 条是 C++26 新增的，检查变量里的指针和引用指向哪里，下一节再讲。

第 1 条有两个注。注 1：判断时 `std::is_constant_evaluated()` 的值为 true，后文会看到它的后果。注 2 {{c++26}}：判断时所有契约断言都按 ignore 语义处理（[[basic.contract.eval]]），但如果这次初始化确实是在编译期求值的，编译器仍可以用其他语义检查契约，违反时给出诊断或使程序非良构。所以契约检查失败不会把常量初始化悄悄变成动态初始化。

¶5 constant-initializable 的变量如果有初始化器，或者类型是 [[g:const-default-constructible]] 的（默认初始化就会初始化所有成员的类类型，[[dcl.init.general]]），就是常量初始化的。

为什么要加这一条？`static int sx;` 没有初始化器，默认初始化什么也不做，随后的零初始化由 [[basic.start.static]] 另外处理。它没有经历用常量初始化的过程，所以不算常量初始化。

## 常量中的指针和引用可以指向哪里（¶1–¶3）{{c++26}}

```cpp
void f() {
  int x;
  constexpr int& ar = x;           // C++26: OK
  static constexpr int& sr = x;    // error: 静态引用指向局部变量
}
```

`ar` 在每次调用 `f` 时都指向这次调用的 `x`，含义是确定的，编译器可以把它实现为栈上的偏移。`sr` 却是静态变量，它会把第一次调用中 `x` 的引用一直保留下去，下一次调用时就悬空了。C++26 用下面三个概念把这个直觉写成规则。

¶1 变量 x 的**组成值和组成引用**（[[g:constituent-values|constituent values and references]]）：如果 x 声明的是对象，就是这个对象的组成值和组成引用（[[intro.object]]，即把对象展开后所有标量子对象的值和所有引用成员）；如果 x 声明的是引用，这个引用本身就是 x 的组成引用。此外，组成引用绑定到的、生命期被延长的临时对象，它的组成值和组成引用也递归地算作 x 的。

临时对象要算进来，是因为 `struct A { const int& r; }; constexpr A a{2};` 中，生命期被延长的临时对象和 `a` 同时存在、同时销毁，它的内容就是 `a` 的一部分。

¶2 满足下列条件之一时，对象 o 从程序点 P 是 **constexpr-referenceable** 的（可以被常量地引用）：

- o 具有静态存储期；
- o 具有自动存储期，并且包含 o 所属变量的最小作用域与包含 P 的最小作用域是同一个函数形参作用域。找最小作用域时跳过块作用域，也跳过 *requires* 表达式的形参作用域，因为后者并不对应一次真正的函数调用。o 所属的变量指它的完整对象对应的变量，或者 o 的生命期被延长到的那个变量。

直观地说，只有当引用者和自动变量处在同一次函数调用中时，才能以常量的方式引用这个变量。同一个函数体内的所有块共用一个栈帧，局部变量的地址在函数体内任何地方都指同一个东西。lambda 体是另一个函数，它的调用是另一个栈帧，而且 lambda 可能被带到别处调用。线程存储期的对象则永远不是 constexpr-referenceable 的：每个线程有一个实例，地址在编译期没有统一的含义。

```cpp
struct A {
  int m;
  const int& r;
};
void f() {
  static int sx;
  thread_local int tx;    // tx 在哪里都不是 constexpr-referenceable
  int ax;
  A aa = {1, 2};
  static A sa = {3, 4};
  // 这里：sx、ax、aa.m、sa.m，以及 aa.r、sa.r 绑定的临时对象都是
  auto lambda = [] {
    int ay;
    // 这里：sx、sa.m、ay，以及 sa.r 绑定的临时对象是；ax 和 aa 不是
  };
}
```

¶3 如果对象或引用 x 的每个组成值所指向（或越过末尾）的对象、每个组成引用所引用的对象，从 P 都是 constexpr-referenceable 的，x 在 P 就是 **constexpr-representable** 的。

回到开头的例子。`ar` 的初始化声明之后，`x` 与它在同一个函数中，所以第 4.2 项满足。`sr` 是静态的，第 4.3 项要求在下一个命名空间作用域的程序点再检查一次，那里已经在 `f` 之外，`x` 不是 constexpr-referenceable 的，于是 `sr` 不是常量初始化的。

¶5 标准的例子 2 把几种存储期组合在一起：

```cpp
void f() {
  int ax = 0;                   // 常量初始化
  thread_local int tx = 0;      // 常量初始化
  static int sx;                // 不是：没有初始化器，int 也不是 const-default-constructible
  static int& rss = sx;         // 常量初始化：sx 是静态的
  static int& rst = tx;         // 不是：tx 是线程局部的
  static int& rsa = ax;         // 不是：静态引用指向自动变量
  thread_local int& rts = sx;   // 常量初始化
  thread_local int& rtt = tx;   // 不是
  thread_local int& rta = ax;   // 不是
  int& ras = sx;                // 常量初始化
  int& rat = tx;                // 不是
  int& raa = ax;                // 常量初始化：同一次函数调用
}
```

`ax`、`raa` 这些自动变量也可以是常量初始化的。这个概念不只决定静态初始化，也是变量能否用于常量表达式的前提（下一节）。

!!! history "从允许的结果到 constexpr-representable"
    C++23 及以前，常量表达式的结果中，指针和引用只能指向静态存储期的对象（[[expr.const.const]] 中的允许的结果），所以 `constexpr int& ar = x;` 非法。C++26 的 [[P2686]] 引入了上面三个概念，把要求从表达式移到变量上，于是同一函数中的 constexpr 引用成为可能，constexpr 结构化绑定也是借此实现的。

!!! impl "实现状态"
    Clang 23 仍按 C++23 的规则处理：它拒绝 `constexpr int& ar = x;`，报告 `constexpr variable 'ar' must be initialized by a constant expression`。

## 可用于常量表达式的变量（¶6–¶9）

常量求值中能读取哪些在求值之外创建的对象？[[expr.const.core#2.10]] 的回答是：可用于常量表达式的对象。

```cpp
const int a = 10;           // 常量初始化的 const int
int arr1[a];                // OK

int rt();
const int b = rt();         // 不是常量初始化
int arr2[b];                // error: b 不可用于常量表达式

const double d = 1.0;       // 常量初始化，但类型是 double
static_assert(d == 1.0);    // error: const double 不是 potentially-constant
```

¶6 如果一个变量是 constexpr 的，或者具有引用类型，或者具有非 volatile 的 const 整型或枚举类型，它就是 **potentially-constant**（[[g:potentially-constant]]）的。这道类型门槛保留了 C++98 以来的一条特例：`const int n = 10;` 不写 `constexpr` 也能用作数组边界，`const double` 则不行。

¶7 变量 V 在程序点 P **可用于常量表达式**（[[g:usable-in-constant-expressions|usable in constant expressions]]），需要同时满足：

- V 是常量初始化的，并且是 potentially-constant 的；
- V 的初始化声明 D 从 P 可达；
- 以下之一成立：V 是 constexpr（7.1）；V 没有被初始化为 TU-local 值（7.2）；P 与 D 在同一个翻译单元中（7.3）。

```cpp
extern const int late;
static_assert(late == 1);   // error: late 的初始化声明此处不可达
const int late = 1;
static_assert(late == 1);   // OK
```

第 7.2、7.3 项主要针对模块。TU-local 值是指向只在本翻译单元有效的实体（例如内部链接的对象）的值，见 [[basic.link]]。一个导出的非 constexpr 的 `const` 变量如果被初始化为这样的值，其他翻译单元就不能把它当常量使用。

¶8 下列对象或引用在 P **潜在可用于常量表达式**（potentially usable in constant expressions）：

- 在 P 可用于常量表达式的变量所声明的对象或引用（8.1）；
- 生命期被延长到这样一个变量的、非 volatile const 字面类型的临时对象（8.2）；
- 模板参数对象（8.3，[[temp.param]]）；
- 字符串字面量对象（8.4，[[lex.string]]）；
- 以上各项的非 mutable 子对象（8.5）和引用成员（8.6）。

¶9 潜在可用于常量表达式，并且在 P 是 constexpr-representable 的对象或引用，在 P **可用于常量表达式**。

```cpp
struct A { int m; const int& r; };
constexpr A ga = {1, 2};       // 临时对象 2 的生命期延长到 ga
static_assert(ga.r == 2);      // OK: 第 8.2、8.6 项

constexpr const char* s = "abc";
static_assert(s[1] == 'b');    // OK: 字符串字面量对象

struct M { mutable int x; };
constexpr M mm{1};
static_assert(mm.x == 1);      // error: mutable 子对象被排除

const int c = 10;
int& rc = const_cast<int&>(c); // 引用类型，绑定到静态对象
static_assert(rc == 10);       // OK: rc 可用，它指代的 c 也可用
```

第 9 段的 constexpr-representable 条件处理的是 C++26 才有的情形：constexpr 变量里存着指向局部变量的指针，到了另一次函数调用里（例如 lambda 中）就不能用了。

```cpp
struct B { int* const& r; };
void g(int x) {
  constexpr B b = {&x};
  static_assert(b.r == &x);             // C++26: OK
  [&] {
    static_assert(b.r != nullptr);      // error: 在 lambda 中，x 不是 constexpr-referenceable
  }();
}
```

Clang 23 在 `constexpr B b = {&x};` 处就报错，因为按 C++23 的规则指向自动变量的指针不能是常量表达式的结果，后面两条 `static_assert` 也随之失败。

## 先按编译期试算，失败再到运行期

第 4.1 项的注 1 规定，判断初始化器是否为常量表达式时，`std::is_constant_evaluated()` 取 true。所以静态存储期变量的初始化分两步：编译器先按编译期试算，失败了，再按运行期的方式动态初始化，这时 `is_constant_evaluated()` 返回 false。

```cpp run ok
#include <cstdio>
#include <type_traits>
int y;
const int a = std::is_constant_evaluated() ? y : 1;  // 试算读 y 失败，动态初始化
const int b = std::is_constant_evaluated() ? 2 : y;  // 试算得 2，常量初始化
int main() { std::printf("%d %d\n", a, b); }         // 1 2
```

`a` 的结果尤其反直觉：表达式里写着 `is_constant_evaluated()`，最终却在运行期求值，得到 false，于是取 1。完整的分析见 [[expr.const.defns]]。

!!! warning "Clang 的警告不完全准确"
    Clang 对这两行都给出 `-Wconstant-evaluated` 警告，说 `is_constant_evaluated` "will always evaluate to 'true' in a manifestly constant-evaluated expression"。对 `a` 来说并不成立，它是动态初始化的，运行时这个调用返回 false。这条警告的实际用意是提醒这种写法多半不是你想要的。

## 常见误解

!!! pitfall "`const int` 的常量性取决于初始化器"
    `const int n = f();` 中的 `n` 能否用于常量表达式，完全取决于 `f()` 能否在编译期求值。在 `f` 里加一行非 constexpr 的日志调用，远处的 `int arr[n];` 就会出错，而 `n` 的声明处没有任何诊断。需要常量时写 `constexpr`，需要静态初始化时写 `constinit`。

!!! pitfall "constexpr 局部变量就是静态变量"
    函数内的 `constexpr int arr[1000] = {...};` 具有自动存储期，每次调用都是一个新对象。编译器通常会把它优化成直接引用 `.rodata` 中的数据，但标准不保证地址不变。需要唯一的地址，或者要返回它的指针，应写 `static constexpr`。

!!! pitfall "块作用域 static 的初始化器一定在运行期执行"
    如果初始化器能在编译期求值，块作用域的 `static` 变量就是常量初始化的，控制流经过时什么也不做：

    ```cpp run ok
    #include <cstdio>
    int calls = 0;
    constexpr int expensive() {
      if !consteval { ++calls; }   // 只在运行期计数
      return 42;
    }
    int get() {
      static int cache = expensive();   // 常量初始化
      return cache;
    }
    int main() {
      get();
      std::printf("%d\n", calls);       // 0
    }
    ```

## 思考题

!!! question "思考题 1"
    下面每个变量是不是常量初始化的？能不能用于常量表达式？

    ```cpp
    struct P { int v; constexpr P() : v(7) {} };
    const P p1;                       // (1)
    const int i1 = P().v;             // (2)
    const double d1 = 1;              // (3)
    int& r1 = const_cast<int&>(i1);   // (4)
    ```

<details markdown="1">
<summary>答案</summary>

1. `p1` 没有初始化器，但 `P` 有用户提供的 constexpr 默认构造函数，是 const-default-constructible 的，所以它是常量初始化的。它是类类型，又不是 constexpr，不是 potentially-constant，因此不可用于常量表达式，`static_assert(p1.v == 7)` 会失败。
2. `i1` 是常量初始化的（`P().v` 是常量表达式），类型是 `const int`，可用于常量表达式。
3. `d1` 是常量初始化的（会做静态初始化），但 `const double` 不是 potentially-constant，不可用于常量表达式。
4. `r1` 是引用，所以是 potentially-constant；初始化器是一个引用静态对象的常量表达式，所以是常量初始化的，可用于常量表达式。`static_assert(r1 == 7)` 会读 `i1`，而 `i1` 可用，所以成立。

Clang 23 的结果与上面一致。
</details>

!!! question "思考题 2"
    为什么第 2 段把线程存储期的对象一律排除在 constexpr-referenceable 之外，而静态存储期的对象总可以？

<details markdown="1">
<summary>答案</summary>

静态存储期的对象在整个程序中只有一个实例，地址可以表示为符号加偏移，由链接器或加载器填入，对所有使用者都一样。线程存储期的对象每个线程一个实例，地址只能在运行期通过线程指针计算，不存在一个能写进 `.data` 的统一的值，也就不能作为常量存进 constexpr 变量。例子 2 中的 `rst` 不是常量初始化的，原因相同。
</details>

## 小结

| 概念 | 条件 | 作用 |
|---|---|---|
| constexpr-referenceable {{c++26}} | 静态存储期，或同一次函数调用中的自动对象 | 定义下一行 |
| constexpr-representable {{c++26}} | 所有组成指针、组成引用的目标都是 constexpr-referenceable 的 | 常量初始化和可用性的条件 |
| constant-initializable | 初始化器是常量表达式，且可表示 | constexpr 变量必须满足 |
| 常量初始化的 | constant-initializable，并且有初始化器或 const-default-constructible | 静态初始化、`constinit` |
| potentially-constant | constexpr、引用、const 非 volatile 的整型或枚举 | 可用性的类型门槛 |
| 可用于常量表达式 | 常量初始化 + potentially-constant + 可达（+ TU-local 限制） | [[expr.const.core#2.10]] 允许读取 |
