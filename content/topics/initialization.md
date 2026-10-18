---
title: C++ 初始化全景
summary: 一张地图看懂 C++ 初始化：每种语法形式 × 每类类型会发生哪种初始化、得到什么值；常见陷阱与 C++98→26 的演变
status: draft
order: 20
since: c++98
papers: P0135R1, P0960R3, P1008R1, N3922, P2795R5
related: dcl.init, dcl.init.aggr, dcl.init.string, dcl.init.ref, dcl.init.list, basic.indet, basic.start.static, class.base.init, expr.new
tags: 初始化, 专题
updated: 2026-10-17
---

C++ 的初始化以复杂著称，但它的复杂性是**有结构的**。任何一次初始化都可以按三个问题定位：

1. **语法形式是什么？** 决定是[[g:copy-initialization|拷贝初始化]]还是[[g:direct-initialization|直接初始化]]，是不是**列表**初始化（[[dcl.init#13]]、[[dcl.init#14]]）。
2. **被初始化的是什么类型？** 标量、聚合、有构造函数的类、引用、数组——各有各的分支（[[dcl.init#15]]、[[dcl.init.list#3]]）。
3. **对象的存储期是什么？** 静态/线程存储期的对象在一切之前先被零初始化（[[basic.start.static]]）；自动与动态存储期的对象则没有这层兜底（[[basic.indet]]）。

本页把这三个维度展开成一张大表，然后讨论最常见的陷阱。每条结论都链接到给出它的条款，需要精确推理时请跳过去读。

## 先认识四个"动作"

所有初始化最终都落到这几个动作之一（定义在 [[dcl.init]] ¶5–¶8）：

| 动作 | 对 `int` | 对类 | 典型触发 |
|---|---|---|---|
| [[g:zero-initialization|零初始化]] | `0` | 各成员零初始化（不调用构造函数） | 静态存储期对象的第一步；值初始化的第一步 |
| [[g:default-initialization|默认初始化]] | 不初始化 | 调用默认构造函数 | `T x;`、`new T`、构造函数没提到的成员 |
| [[g:value-initialization|值初始化]] | `0` | 默认构造函数是**用户提供的** → 只调用它；否则 → 先零初始化再调用 | `T()`、`T{}`（非聚合）、`new T()` |
| [[g:list-initialization|列表初始化]] | 从唯一元素初始化，禁止窄化 | 聚合 → 聚合初始化；否则 → 构造函数（initializer_list 优先） | 一切 `{…}` |

## 示例类型

下表中的列用以下类型代表各类别：

```cpp
#include <string>
struct Agg  { int a; std::string s; };                       // 聚合
struct Usr  { Usr() {} Usr(int) {} int i; };                 // 用户提供的默认构造函数（不初始化 i）
struct Dft  { Dft() = default; Dft(int) {} int i; };         // 非聚合，默认构造函数不是用户提供的
struct IL   { IL(std::initializer_list<int>) {} IL(int, int) {} };  // 有 initializer-list 构造函数
```

`int` 代表标量，`int&` / `const int&` 代表引用，`int[3]` 代表数组；`v` 是一个合适类型的值。

## 大表：语法 × 类型

以下默认是**块作用域、自动存储期**的声明（静态存储期见后面单独一行）。"未初始化"在 C++26 中意味着**错误值**（读取是错误行为），在 C++23 及以前读取是 UB。

| 语法 | `int` | `Agg` | `Usr` | `Dft` | `int[3]` | 引用 |
|---|---|---|---|---|---|---|
| `T x;` | 未初始化 | `a` 未初始化，`s` 为空 | 调用 `Usr()`，`i` 未初始化 | 隐式默认构造，`i` 未初始化 | 3 个未初始化 | 非良构 |
| `T x{};` | `0` | 聚合初始化：`a = 0`，`s` 为空 | 值初始化 → `Usr()`，`i` **未初始化** | 值初始化 → 先清零，`i = 0` | `{0, 0, 0}` | `int&` 非良构；`const int&` 绑定到临时 `0` |
| `T x();` | **函数声明** | 函数声明 | 函数声明 | 函数声明 | — | — |
| `T x = v;` | 转换后的 `v` | `v` 是 `Agg`：拷贝 | `v` 是 `int`：经 `Usr(int)`（非 explicit） | 同左 | 非良构（字符数组 + 字符串字面量除外） | 绑定（规则见 [[dcl.init.ref]]） |
| `T x(v);` | `v` | `v` 是 `Agg`：拷贝；否则圆括号聚合初始化 `a = v`（C++20） | `Usr(v)` | `Dft(v)` | C++20：`{v, 0, 0}` | 绑定 |
| `T x{v};` | `v`，禁止窄化 | `v` 是 `Agg`：拷贝；否则聚合初始化 `a = v` | `Usr(v)`，禁止窄化 | `Dft(v)` | `{v, 0, 0}` | 绑定（被引用类型与 `v` 引用相关时直接绑定） |
| `T x = {v};` | 同 `{v}` | 同 `{v}` | 同 `{v}`，但选中 explicit 构造函数则非良构 | 同左 | 同 `{v}` | 同 `{v}` |
| `T x(a, b);` | 非良构 | C++20：圆括号聚合初始化 | 构造函数 | 构造函数 | C++20：`{a, b, 0}` | 非良构 |
| `new T` | 未初始化（**不确定值**，读取是 UB） | 同 `T x;` | 同 `T x;` | 同 `T x;` | 同 `T x;` | — |
| `new T()` | `0` | 值初始化：`a = 0`，`s` 为空 | `Usr()`，`i` 未初始化 | `i = 0` | `new int[3]()` 全 0 | — |
| `new T{}` | `0` | 同 `T x{};` | 同 `T x{};` | 同 `T x{};` | `new int[3]{}` 全 0 | — |
| 表达式 `T()` | `0` | 值初始化：全零 | `Usr()` | `i = 0` | — | — |
| 表达式 `T{}` | `0` | 聚合初始化：全零 | `Usr()` | `i = 0` | `T{}`（别名）全 0 | — |
| 成员：构造函数没提到、无默认成员初始化器 | 未初始化 | 默认初始化 | `Usr()` | `i` 未初始化 | 未初始化 | 非良构 |
| 成员：`: m()` | `0` | 值初始化 | `Usr()` | `i = 0` | 全 0 | 非良构 |
| `static T x;`（静态存储期，无初始化器） | `0` | `a = 0`，`s` 为空 | 先清零，再 `Usr()` → `i = 0` | `i = 0` | 全 0 | 非良构 |

带 `IL` 的几行单独看，因为 initializer-list 构造函数会改变花括号的含义：

| 语法 | 结果 | 依据 |
|---|---|---|
| `IL x{};` | `IL(initializer_list<int>)`，空列表 | [[dcl.init.list#3]]、[[over.match.list]] |
| `IL x{1, 2};` | `IL(initializer_list<int>)` | 第一阶段胜出 |
| `IL x(1, 2);` | `IL(int, int)` | 非列表初始化 |
| `IL x{1.5, 2};` | 非良构：第一阶段选中 initializer-list 构造函数，然后发现窄化 | [[dcl.init.list#7]] |

（第一行的推理展示了规则的层层递进：空列表时，¶3.5 只在**有默认构造函数**时适用；否则进入 ¶3.7，而 [[over.match.list]] 第一阶段的条件"列表非空**或 T 没有默认构造函数**"恰好成立。）

## 用一个流程回答"`T x = …` / `T x(…)` 到底做了什么"

```text
初始化器是 {…} 吗？
├─ 是 → 列表初始化 [dcl.init.list]
│     ├─ 有指派符？              → 聚合初始化（按声明顺序）
│     ├─ 聚合 + 单个同类元素？    → 拷贝
│     ├─ 聚合？                  → 聚合初始化（花括号省略、默认成员初始化器、余下 {}）
│     ├─ 空列表 + 有默认构造函数？ → 值初始化
│     ├─ 类？                    → initializer_list 构造函数优先，否则其他构造函数；窄化即错
│     ├─ 固定底层类型枚举 + 直接？ → T(v)
│     ├─ 单元素？                → 从该元素初始化；窄化即错
│     ├─ 引用？                  → 造临时量（拷贝列表初始化）再绑定
│     └─ 空？                    → 值初始化
└─ 否 → [dcl.init] ¶15
      ├─ 引用？                  → [dcl.init.ref]
      ├─ 字符数组 + 字符串字面量？→ [dcl.init.string]
      ├─ ()？                    → 值初始化（但 T x(); 是函数声明）
      ├─ 数组？                  → (x1,…,xk)：逐个拷贝初始化，其余值初始化（C++20）
      ├─ 类？
      │    ├─ 同类型纯右值？      → 就是它（保证的复制消除）
      │    ├─ 直接初始化 / 同类或派生类拷贝？→ 构造函数；没有可行的且是聚合 → 圆括号聚合初始化
      │    └─ 其他拷贝初始化？    → 一次用户定义转换（非 explicit）
      ├─ 源是类？                → 转换函数
      └─ 其他                    → 标准转换
```

## 初始化在**什么时候**发生

"做了什么"之外，还有"什么时候做"：

| 对象 | 时机 | 条款 |
|---|---|---|
| 命名空间作用域 / 静态数据成员 / 静态局部变量 | 程序启动时先**静态初始化**（常量初始化，否则零初始化） | [[basic.start.static]] |
| 命名空间作用域变量的动态初始化 | `main` 之前（或首次 odr-use 之前），同一 TU 内按定义顺序，跨 TU 顺序未指定 | [[basic.start.dynamic]] |
| 静态局部变量的动态初始化 | 控制流**首次**经过声明时；线程安全；抛异常则下次重试 | [[stmt.dcl]] |
| 自动变量 | 控制流经过声明时，每次都初始化 | [[stmt.dcl]] |
| 成员 | 构造函数的 *ctor-initializer* 阶段，按**声明顺序**（不是 *mem-initializer* 的书写顺序） | [[class.base.init]] |
| `new` 出的对象 | *new-expression* 求值时 | [[expr.new]] |

`constinit`（[[dcl.constinit]]）断言一个静态存储期变量是常量初始化的，从而杜绝"静态初始化顺序灾难"。

## 最常见的陷阱

### 1. 最令人烦恼的解析

```cpp
struct Timer {};
struct Guard { Guard(Timer) {} };
void f() {
  Timer t();                // 函数声明，不是对象
  Guard g(Timer());         // 也是函数声明：参数是"返回 Timer 的函数"
  Guard g2{Timer{}};        // OK: 对象
}
```

规则来源：[[dcl.ambig.res]]——"能被解析为声明的，就是声明"；`()` 不是合法的 *initializer*（[[dcl.init]] ¶15.4 注 6）。花括号初始化不受影响。

### 2. 窄化

```cpp
int n = 7.9;          // OK: 截断为 7（只有警告）
int m{7.9};           // error: 窄化
std::vector<int> v{3.0};   // error: 选中 initializer_list 构造函数后窄化，不会回退
```

花括号拒绝窄化是**好事**，但要记住它在泛型代码中可能让 `T{args...}` 失败而 `T(args...)` 成功。完整定义见 [[dcl.init.list#7]]。

### 3. initializer_list 劫持

```cpp
std::vector<int> a(10, 1);    // 10 个 1
std::vector<int> b{10, 1};    // 2 个元素：10 和 1
std::vector<std::string> c{3};      // 3 个空串（initializer_list<string> 不可行，回退）
std::vector<std::string> d{"a", "b"};   // 2 个串
// std::vector<std::string> e{{"a", "b"}};  // UB: 一个 string，用两个无关指针做迭代器区间
```

经验法则：对"容器类"，花括号用于**列出元素**，圆括号用于**传递参数**。

### 4. `= default` 与值初始化的清零

```cpp
struct A { A() = default; int i; };      // 类内 = default：不是用户提供的
struct B { B(); int i; };
B::B() = default;                        // 类外 = default：是用户提供的！
A a{};   // a.i == 0
B b{};   // b.i 未初始化
```

更隐蔽的版本：一个有用户提供构造函数的类，其构造函数没有初始化某个标量成员——外层再怎么写 `{}`、`()` 都不会清零它（值初始化只在默认构造函数**不是**用户提供时才先清零）。最稳健的做法是给每个标量成员写**默认成员初始化器**：`int i = 0;`。

### 5. 未初始化的成员与局部变量

```cpp
struct Conn {
  int fd;
  bool open;
  Conn() : fd(-1) {}       // open 没有被初始化！
};
```

C++26 起读取 `open` 是错误行为（实现可以诊断或给出固定的错误值），C++23 及以前是 UB。`new Conn` 出来的对象中，`open` 是不确定值，读取在任何版本中都是 UB（[[basic.indet]]）。

### 6. `auto` 与花括号

```cpp
auto a = {1};    // std::initializer_list<int>
auto b{1};       // int（C++17 起；N3922）
auto c{1, 2};    // error
```

### 7. 圆括号聚合初始化不延长寿命

```cpp
struct R { const std::string& name; };
R r1{"temp"};    // 临时 string 的寿命延长到 r1 的寿命
R r2("temp");    // C++20 合法，但 r2.name 立即悬垂
```

见 [[dcl.init#15]] 注 7 和 [[class.temporary]] ¶6.11。

### 8. C++20 中聚合"消失"了

```cpp
struct P { P() = default; int x, y; };
P p{1, 2};       // C++17: OK（聚合）；C++20: error（有用户声明的构造函数，不再是聚合）
```

见 [[dcl.init.aggr]] 中的定义演变表。

### 9. 成员初始化顺序

```cpp
struct S {
  int b;
  int a;
  S() : a(1), b(a + 1) {}   // b 先于 a 初始化（声明顺序），读取未初始化的 a
};
```

*mem-initializer* 的书写顺序不影响初始化顺序（[[class.base.init]]）；Clang/GCC 的 `-Wreorder` 会提醒。

## 演变简史

| 版本 | 变化 | 详见 |
|---|---|---|
| C++98 | 零初始化、默认初始化；聚合初始化（来自 C）；`T()` 对 POD 清零 | [[dcl.init]] |
| C++03 | **值初始化** | [[dcl.init#8]] |
| C++11 | 花括号/列表初始化、`std::initializer_list`、窄化检查、默认成员初始化器、`= default`/`= delete`、`constexpr`、线程安全的静态局部变量 | [[dcl.init.list]] |
| C++14 | 聚合可以有默认成员初始化器；花括号省略放宽 | [[dcl.init.aggr]] |
| C++17 | 保证的复制消除（[[P0135R1]]）；聚合可以有基类；`auto x{1}` 是 `int`（[[N3922]]）；枚举的直接列表初始化；CTAD | [[dcl.init#15]] |
| C++20 | 指派初始化器；圆括号聚合初始化（[[P0960R3]]）；聚合不能有用户声明的构造函数（[[P1008R1]]）；`constinit`；指针到 `bool` 是窄化 | [[dcl.init.aggr]] |
| C++23 | 扩展浮点类型的窄化规则；`reference_constructs_from_temporary`；范围 for 初始化器中的临时量延寿 | [[dcl.init.ref]] |
| C++26 | **错误行为**：未初始化的自动变量不再是 UB（[[P2795R5]]）；`[[indeterminate]]`；`return` 绑定临时量非良构；backing array 可静态存储；（当前草案）指派基类成员 | [[basic.indet]]、[[dcl.init.ref]] |

## 实用建议

!!! tip
    - **默认使用 `T x{…}` 或 `T x = …`**，避免 `T x(…)` 带来的解析歧义；但对容器类型的"大小/计数"参数，必须用圆括号。
    - **给每个标量成员写默认成员初始化器**。这让 `T x;`、`T x{}`、构造函数遗漏成员的所有情形都有确定值，且不会使类失去聚合性（C++14 起）。
    - **不要在 C++20 代码中为聚合声明 `= default` 构造函数**——除非你就是想让它不再是聚合。
    - **静态存储期变量用 `constinit` 或 `constexpr`**，杜绝动态初始化顺序问题。
    - **不要存储 `std::initializer_list`**，不要让引用成员绑定到构造函数实参的临时量。
