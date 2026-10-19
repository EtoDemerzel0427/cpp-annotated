---
title: C++ 初始化全景
summary: 每种初始化语法遇到每类类型时发生哪种初始化、对象得到什么值、在什么时候初始化，以及最常见的陷阱。
status: draft
order: 20
since: c++98
papers: P0135R1, P0960R3, P1008R1, N3922, P2795R5
related: dcl.init, dcl.init.aggr, dcl.init.string, dcl.init.ref, dcl.init.list, basic.indet, basic.start.static, class.base.init, expr.new
tags: 初始化, 专题
updated: 2026-10-19
---

!!! tldr
    - 判断一次初始化做了什么，依次看三件事：初始化器的语法形式、被初始化的类型、对象的存储期。
    - 所有初始化最后都落到四个动作之一：零初始化、默认初始化、值初始化、列表初始化。
    - `T x{}` 只有在默认构造函数不是用户提供的时候才会先清零；自己写了 `S() {}` 的类，`S{}` 不会把成员清零。
    - 花括号禁止窄化，而且优先选 `std::initializer_list` 构造函数：`std::vector<int>{10, 1}` 是两个元素。
    - 静态存储期的对象总会先被零初始化；自动存储期的标量不写初始化器，C++26 起得到错误值（读取是错误行为），以前读取是 UB。

## 三个问题定位一次初始化

```cpp
int a;        // 自动变量：没有初始化
int b{};      // 0
int c();      // 不是变量，是函数声明
static int d; // 0
```

四行看起来差不多，结果各不相同。任何一次初始化都可以按三个问题定位：

1. **语法形式是什么？** 带 `=` 的形式（`T x = v;`、`T x = {v};`）以及传参、返回值，叫做[[g:copy-initialization|复制初始化]]；不带 `=` 的 `T x(v)`、`T x{v}`、`new T(v)`、`static_cast` 等叫做[[g:direct-initialization|直接初始化]]（[[dcl.init#13]]、[[dcl.init#14]]）。初始化器是花括号的，又都属于[[g:list-initialization|列表初始化]]。
2. **被初始化的是什么类型？** 标量、[[g:aggregate|聚合]]、有构造函数的类、引用、数组，各走各的分支（[[dcl.init#15]]、[[dcl.init.list#3]]）。聚合指数组，以及没有用户声明的构造函数、没有私有或受保护的直接数据成员、没有虚函数和虚基类的类。
3. **对象的存储期是什么？** 静态和线程存储期的对象在任何动态初始化之前先完成静态初始化：能常量初始化就常量初始化，否则零初始化（[[basic.start.static]]）。自动和动态存储期的对象没有这层兜底（[[basic.indet]]）。

## 四个基本动作

| 动作 | 对 `int` | 对类 | 典型触发 |
|---|---|---|---|
| [[g:zero-initialization\|零初始化]]（[[dcl.init#5]]） | `0` | 每个成员和基类零初始化，填充位清零，不调用构造函数 | 静态存储期对象的第一步；值初始化的第一步 |
| [[g:default-initialization\|默认初始化]]（[[dcl.init#6]]） | 什么也不做 | 调用默认构造函数 | `T x;`、`new T`、构造函数没有提到的成员 |
| [[g:value-initialization\|值初始化]]（[[dcl.init#8]]） | `0` | 选中的默认构造函数不是用户提供的：先零初始化再默认初始化；否则只默认初始化 | `T()`、`T{}`（非聚合）、`new T()`、`: m()` |
| 列表初始化（[[dcl.init.list]]） | 从唯一元素初始化，禁止窄化 | 聚合：聚合初始化；否则选构造函数，`initializer_list` 构造函数优先 | 一切 `{…}` |

值初始化对类的分叉最容易出错。一个构造函数是[[g:user-provided|用户提供]]的，指它由用户声明，而且在首次声明时没有写 `= default` 或 `= delete`。所以：

<div class="compare" markdown="1">

```cpp
struct A { A() = default; int i; };
A a{};   // a.i == 0
// 类内 = default：不是用户提供的
// 值初始化先清零
```

```cpp
struct S { S() {} int i; };
S s{};   // s.i 没有初始化
// 用户提供的构造函数：
// 值初始化只调用 S()
```

</div>

## 语法 × 类型

下表用这几个类型代表各类别：

```cpp
#include <initializer_list>
#include <string>
struct Agg { int a; std::string s; };                 // 聚合
struct Usr { Usr() {} Usr(int) {} int i; };           // 默认构造函数是用户提供的，不初始化 i
struct Dft { Dft() = default; Dft(int) {} int i; };   // 非聚合，默认构造函数不是用户提供的
struct IL  { IL(std::initializer_list<int>) {} IL(int, int) {} };
```

`v` 表示一个合适类型的值。下表默认是块作用域里的自动变量。表中"未初始化"在 C++26 中指对象持有[[g:erroneous-value|错误值]]，读取它是错误行为（erroneous behavior：标准认定为错误、但行为有定义的操作，实现可以诊断）；C++23 及以前读取是 UB。

| 语法 | `int` | `Agg` | `Usr` | `Dft` | `int[3]` | 引用 |
|---|---|---|---|---|---|---|
| `T x;` | 未初始化 | `a` 未初始化，`s` 为空 | 调用 `Usr()`，`i` 未初始化 | `i` 未初始化 | 3 个都未初始化 | 非良构 |
| `T x{};` | `0` | 聚合初始化：`a = 0`，`s` 为空 | 值初始化，只调用 `Usr()`，`i` 未初始化 | 值初始化，先清零，`i = 0` | `{0, 0, 0}` | `int&` 非良构；`const int&` 绑定到临时量 `0` |
| `T x();` | 函数声明 | 函数声明 | 函数声明 | 函数声明 | — | — |
| `T x = v;` | 转换后的 `v` | `v` 是 `Agg` 时复制 | `v` 是 `int` 时经 `Usr(int)` | 同左 | 非良构（字符数组用字符串字面量初始化除外） | 绑定，见 [[dcl.init.ref]] |
| `T x(v);` | `v` | `v` 不是 `Agg` 时圆括号聚合初始化，`a = v`（C++20） | `Usr(v)` | `Dft(v)` | `{v, 0, 0}`（C++20） | 绑定 |
| `T x{v};` | `v`，禁止窄化 | 聚合初始化 `a = v` | `Usr(v)`，禁止窄化 | `Dft(v)` | `{v, 0, 0}` | 绑定 |
| `T x = {v};` | 同 `{v}` | 同 `{v}` | 同 `{v}`，但选中 explicit 构造函数时非良构 | 同左 | 同 `{v}` | 同 `{v}` |
| `T x(a, b);` | 非良构 | 圆括号聚合初始化（C++20） | 构造函数 | 构造函数 | `{a, b, 0}`（C++20） | 非良构 |
| `new T` | 不确定值，读取是 UB | 同 `T x;` | 同 `T x;` | 同 `T x;` | 同 `T x;` | — |
| `new T()`、`new T{}` | `0` | `a = 0`，`s` 为空 | `Usr()`，`i` 未初始化 | `i = 0` | 全 0 | — |
| 表达式 `T()`、`T{}` | `0` | `a = 0`，`s` 为空 | `Usr()`，`i` 未初始化 | `i = 0` | — | — |
| 成员：构造函数没提到，也没有默认成员初始化器 | 未初始化 | 默认初始化 | `Usr()` | `i` 未初始化 | 未初始化 | 非良构 |
| 成员：`: m()` | `0` | 值初始化 | `Usr()` | `i = 0` | 全 0 | 非良构 |
| `static T x;` | `0` | `a = 0`，`s` 为空 | 先零初始化，再调用 `Usr()`，`i = 0` | `i = 0` | 全 0 | 非良构 |

`new T` 一行与 `T x;` 不同：动态存储期的对象不适用错误值的规则，默认初始化之后是[[g:indeterminate-value|不确定值]]，读取在任何版本中都是 UB（[[basic.indet]]）。

有 `initializer_list` 构造函数的类，花括号的含义会变：

| 语法 | 选中的构造函数 | 原因 |
|---|---|---|
| `IL x{1, 2};` | `IL(initializer_list<int>)` | 列表非空时先只考虑 `initializer_list` 构造函数（[[over.match.list]]） |
| `IL x(1, 2);` | `IL(int, int)` | 不是列表初始化 |
| `IL x{};` | `IL(initializer_list<int>)`，空列表 | `IL` 没有默认构造函数，所以不走值初始化（[[dcl.init.list#3.5]]），第一阶段照样只看 `initializer_list` 构造函数 |
| `IL x{1.5, 2};` | 非良构 | 第一阶段选中 `initializer_list` 构造函数，然后发现 `1.5` 到 `int` 是窄化，不会退回 `IL(int, int)` |

**窄化转换**（[[g:narrowing-conversion|narrowing conversion]]）指可能丢失信息的隐式转换，例如浮点到整数、`long` 到 `int`（值装不下时）、指针到 `bool`。完整定义见 [[dcl.init.list#7]]。

## 判定流程

上面两张表可以归结成一个流程。花括号初始化按 [[dcl.init.list#3]] 的顺序判断，其他形式按 [[dcl.init#15]]：

```text
初始化器是 {…} 吗？
├─ 是 → 列表初始化 [dcl.init.list]
│     ├─ 有指派符？                  → 聚合初始化（指派顺序须与声明顺序一致）
│     ├─ 聚合类 + 单个同类或派生类元素？→ 从该元素复制
│     ├─ 字符数组 + 字符串字面量？    → [dcl.init.string]
│     ├─ 聚合？                      → 聚合初始化
│     ├─ 空列表 + 类有默认构造函数？   → 值初始化
│     ├─ 类？                        → initializer_list 构造函数优先，再看其他构造函数；窄化即错
│     ├─ 固定底层类型的枚举 + 单元素直接初始化？→ 转换为该枚举
│     ├─ 单元素（且不是需要临时量的引用）？→ 从该元素初始化；窄化即错
│     ├─ 引用？                      → 生成临时量（复制列表初始化）再绑定
│     └─ 空列表？                    → 值初始化
└─ 否 → [dcl.init]/15
      ├─ 引用？                      → [dcl.init.ref]
      ├─ 字符数组 + 字符串字面量？    → [dcl.init.string]
      ├─ 初始化器是 ()？              → 值初始化（但声明 T x(); 是函数声明）
      ├─ 数组？                      → (x1,…,xk)：逐个复制初始化，其余值初始化（C++20）
      ├─ 类？
      │    ├─ 同类型 prvalue？        → 直接用它初始化（保证的复制消除）
      │    ├─ 直接初始化，或源是同类/派生类？→ 选构造函数；没有可行的、且是聚合 → 圆括号聚合初始化
      │    └─ 其余复制初始化？        → 一次用户定义转换（不考虑 explicit）
      ├─ 源是类？                    → 转换函数
      └─ 其他                        → 标准转换
```

## 初始化在什么时候发生

| 对象 | 时机 | 条款 |
|---|---|---|
| 命名空间作用域变量、静态数据成员、静态局部变量 | 程序启动时先静态初始化（常量初始化，否则零初始化） | [[basic.start.static]] |
| 命名空间作用域变量的动态初始化 | `main` 之前，或推迟到首次 odr-use 之前；同一翻译单元内按定义顺序，跨翻译单元顺序未指定 | [[basic.start.dynamic]] |
| 静态局部变量的动态初始化 | 控制流第一次经过声明时；多线程下也只初始化一次；抛出异常则下次再试 | [[stmt.dcl]] |
| 自动变量 | 控制流每次经过声明时 | [[stmt.dcl]] |
| 基类和成员 | 构造函数体之前，按声明顺序，而不是 *mem-initializer* 的书写顺序 | [[class.base.init]] |
| `new` 出的对象 | *new-expression* 求值时 | [[expr.new]] |

跨翻译单元的动态初始化顺序未指定，一个全局对象的初始化器用到另一个文件里的全局对象时，可能读到还没初始化的值。`constinit`（[[dcl.constinit]]）要求变量必须常量初始化，否则编译失败，这样它就不参与动态初始化。

## 常见陷阱

### 函数声明而不是对象

```cpp
struct Timer {};
struct Guard { Guard(Timer) {} };
void f() {
  Timer t();            // 函数声明：无参、返回 Timer
  Guard g(Timer());     // 也是函数声明：形参是"返回 Timer 的函数"
  Guard g2{Timer{}};    // OK：对象
}
```

[[dcl.ambig.res]] 规定，能解析为声明的就按声明解析，这就是[[g:most-vexing-parse|最令人烦恼的解析]]（most vexing parse）。`()` 本身也不是合法的 *initializer*（[[dcl.init#15]] 注 6）。花括号不会有这个问题。Clang 对前两行给出 `-Wvexing-parse` 警告。

### 窄化

```cpp
#include <vector>
int n = 7.9;               // OK：截断为 7，Clang 只给警告
int m{7.9};                // error: 窄化
std::vector<int> v{3.0};   // error: 选中 initializer_list 构造函数后发现窄化
```

泛型代码里要注意：同样的参数，`T{args...}` 可能因窄化失败，`T(args...)` 却能编译。

### `initializer_list` 构造函数优先

```cpp
#include <string>
#include <vector>
std::vector<int> a(10, 1);              // 10 个 1
std::vector<int> b{10, 1};              // 2 个元素：10 和 1
std::vector<std::string> c{3};          // 3 个空串：int 转不成 string，退回 vector(size_type)
std::vector<std::string> d{"a", "b"};   // 2 个串
// std::vector<std::string> e{{"a", "b"}};
//   UB：一个 string，用两个无关的指针当迭代器区间构造
```

容器类型用花括号列出元素，用圆括号传递大小、计数之类的参数。

### 类外 `= default` 是用户提供的

```cpp
struct A { A() = default; int i; };
struct B { B(); int i; };
B::B() = default;   // 首次声明时没有 = default，所以是用户提供的
A a{};              // a.i == 0
B b{};              // b.i 没有初始化
```

同样，一个类只要自己写了构造函数而漏掉某个标量成员，外面写 `{}` 还是 `()` 都不会把它清零。最稳妥的做法是给每个标量成员写默认成员初始化器：`int i = 0;`。C++14 起这不会让类失去聚合性。

### 漏掉的成员

```cpp
struct Conn {
  int fd;
  bool open;
  Conn() : fd(-1) {}   // open 没有初始化
};
```

自动存储期的 `Conn` 里，C++26 起读取 `open` 是错误行为，C++23 及以前是 UB。`new Conn` 得到的对象里 `open` 是不确定值，读取在任何版本中都是 UB。

### `auto` 与花括号

```cpp
auto a = {1};   // std::initializer_list<int>
auto b{1};      // int（C++17 起，N3922）
auto c{1, 2};   // error: 直接列表初始化的 auto 只能有一个元素
```

### 圆括号聚合初始化不延长临时量的寿命

```cpp
#include <string>
struct R { const std::string& name; };
R r1{"temp"};   // 临时 string 的生命周期延长到与 r1 相同
void f() {
  R r2("temp"); // C++20 起合法，但 r2.name 立刻悬垂（Clang：-Wdangling）
}
```

圆括号聚合初始化按"调用一个构造函数"的模型设计，而构造函数的引用形参不延长实参的寿命（[[dcl.init#15]] 注 7，[[class.temporary#6.11]]）。更多情形见 [[topics/dangling-references]]。

### C++20 起有用户声明构造函数的类不是聚合

```cpp
struct P { P() = default; int x, y; };
P p{1, 2};   // C++17：OK，P 是聚合；C++20：error，没有匹配的构造函数
```

[[P1008R1]] 把聚合的条件从"没有用户提供的构造函数"改成"没有用户声明的构造函数"。演变过程见 [[dcl.init.aggr]]。

### 成员按声明顺序初始化

```cpp
struct S {
  int b;
  int a;
  S() : a(1), b(a + 1) {}   // b 先初始化，此时 a 还没有初始化
};
```

*mem-initializer* 的书写顺序不影响初始化顺序（[[class.base.init]]）。Clang 对这段代码给出 `-Wreorder-ctor` 和 `-Wuninitialized` 两条警告。

## 演变

| 版本 | 变化 |
|---|---|
| C++98 | 零初始化、默认初始化；从 C 继承的聚合初始化 |
| C++03 | 新增值初始化：C++98 的 `T()` 只对 POD 清零，C++03 起没有用户声明构造函数的类（例如含 `std::string` 成员的类）也会先清零（[[dcl.init#8]]） |
| C++11 | 花括号初始化与 `std::initializer_list`、窄化检查、默认成员初始化器、`= default`/`= delete`、线程安全的静态局部变量初始化 |
| C++14 | 有默认成员初始化器的类也可以是聚合；直接列表初始化中也允许花括号省略，如 `std::array<int, 3> a{1, 2, 3}` |
| C++17 | 保证的复制消除（[[P0135R1]]）；聚合可以有基类；`auto x{1}` 推导为 `int`（[[N3922]]）；有固定底层类型的枚举可以 `E e{1}` |
| C++20 | 指派初始化器；圆括号聚合初始化（[[P0960R3]]）；有用户声明构造函数的类不再是聚合（[[P1008R1]]）；`constinit`；指针到 `bool` 算窄化 |
| C++23 | 范围 for 初始化器中的临时量延长寿命（见 [[topics/dangling-references]]） |
| C++26 | 未初始化的自动变量从 UB 改为错误行为，`[[indeterminate]]` 可以恢复旧行为（[[P2795R5]]）；`return` 把引用绑定到临时量是非良构 |

当前草案还允许在指派初始化器中指派基类的成员（[[dcl.init.list#3]] 例 2 中的 `B e{.x = 1, .q = 3}`）。本机 Clang 23 尚未实现，会报 "field designator 'x' does not refer to any field"。

!!! summary "实用建议"
    - 默认写 `T x{…}` 或 `T x = …`，避开函数声明歧义；容器的大小、计数参数用圆括号。
    - 给每个标量成员写默认成员初始化器，所有构造路径就都有确定的值。
    - 想让一个类保持聚合，就不要给它声明任何构造函数，包括 `= default`。
    - 静态存储期变量尽量用 `constexpr` 或 `constinit`，避开跨文件的动态初始化顺序问题。
    - 不要保存 `std::initializer_list`，不要让引用成员绑定到构造函数实参的临时量。
