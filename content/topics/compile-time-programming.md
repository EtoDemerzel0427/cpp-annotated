---
title: 编译期编程
summary: constexpr、consteval、constinit、if constexpr、if consteval、模板与概念、静态反射各管什么，什么时候用哪个，以及为什么常量求值能替你抓住未定义行为。
status: done
since: c++11
order: 30
papers: N2235, N3652, P0292R2, P0784R7, P1073R3, P1143R2, P0595R2, P1938R3, P2564R3, P2280R4, P2996R13
related: expr.const, expr.const.core, expr.const.init, expr.const.imm, expr.const.defns, dcl.constexpr, dcl.constinit, stmt.if, temp.arg.nontype, temp.constr
tags: 常量求值, constexpr, consteval, 模板, 反射
updated: 2026-10-19
---

!!! tldr
    - `constexpr` 函数表示可以在编译期求值，不保证一定在编译期求值；`consteval` 函数的每次调用都必须在编译期完成；`constinit` 保证静态初始化，变量本身仍可修改。
    - 只有在显然常量求值的场合（数组边界、模板实参、`static_assert`、`constexpr` 变量的初始化器等），标准才要求在编译期求值。
    - 常量求值中不允许出现核心语言的未定义行为，所以把测试写成 `static_assert`，编译器会替你检查这组输入有没有 UB。
    - 编译期 `new` 出来的内存必须在同一次常量求值中释放，不能留给运行期。
    - 按类型分派用 `if constexpr`；同一个函数需要编译期和运行期两套实现时用 `if consteval`。

## constexpr 不保证编译期执行

```cpp run ok
constexpr int fib(int n) { return n < 2 ? n : fib(n - 1) + fib(n - 2); }
consteval int fib_ct(int n) { return fib(n); }

int run() {
  int a = fib(20);             // 可能在运行期计算
  constexpr int b = fib(20);   // 必须在编译期计算
  int c = fib_ct(20);          // 立即调用：必须在编译期计算
  return a + b + c;
}
int main() { return run() == 3 * 6765 ? 0 : 1; }
```

三行都调用了同一个 `constexpr` 函数。本机 Clang 23 用 `-O2` 编译，`a` 仍然是一次真实的 `fib(20)` 调用，优化器没有展开这么深的递归；`b` 和 `c` 在汇编里直接是常数 6765。

原因是一个表达式能不能作为常量表达式，和它实际在什么时候求值，是两件事。

- 能否作为常量表达式，是表达式的性质，由 [[expr.const.core]] 和 [[expr.const.const]] 规定。
- 何时求值是实现的选择。标准只在**显然常量求值**（manifestly constant-evaluated，[[expr.const.defns#1]]）的场合要求在翻译期得到结果，例如数组边界、模板实参、`static_assert`、`constexpr` 和 `constinit` 变量的初始化器、`consteval` 函数的调用。
- 其他场合，一个常量表达式可以留到运行期求值，一个非常量表达式也可以被优化器在编译期折叠。

要保证在编译期计算，就把结果放进显然常量求值的场合：用 `constexpr` 变量接住，作为模板实参，放进 `static_assert`，或者把函数声明为 `consteval`。

## 工具一览

| 工具 | 作用于 | 含义 | 引入 | 条款 |
|---|---|---|---|---|
| `constexpr` 变量 | 变量 | 必须常量初始化、常量析构；隐含 `const`；可用于常量表达式 | C++11 | [[dcl.constexpr#6]] |
| `constexpr` 函数 | 函数 | 可以在常量表达式中调用，也可以在运行期调用 | C++11，C++14 大幅放宽 | [[dcl.constexpr]] |
| `consteval` 函数 | 函数 | 只能在编译期调用，每次调用都必须是常量表达式 | C++20 | [[expr.const.imm]] |
| `constinit` | 静态或线程存储期变量 | 必须静态初始化；不隐含 `const` | C++20 | [[dcl.constinit]] |
| `if constexpr` | 语句 | 条件是常量；在模板中，没有选中的分支不会被实例化 | C++17 | [[stmt.if#2]] |
| `if consteval` | 语句 | 判断当前是否在显然常量求值中；第一个分支可以调用 `consteval` 函数 | C++23 | [[stmt.if#4]] |
| `std::is_constant_evaluated()` | 表达式 | 与 `if consteval` 判断的是同一件事，但不能借此调用 `consteval` 函数 | C++20 | [[meta.const.eval]] |
| `static_assert` | 声明 | 编译期断言 | C++11 | [[dcl.pre#13]] |
| 模板与非类型模板形参 | 类型和值 | 以类型和常量值为参数生成代码；C++20 起非类型模板形参可以是浮点数和结构化类类型 | C++98、C++20 | [[temp.arg.nontype]] |
| 概念与 `requires` | 约束 | 编译期谓词，参与重载决议 | C++20 | [[temp.constr]] |
| 静态反射 `^^`、`[: :]` | 程序实体 | 把类型、成员、命名空间变成 `std::meta::info` 值，在 `consteval` 代码中查询和生成 | C++26 | [[expr.const.reflect]] |
| `consteval { }` 块 | 声明 | 在命名空间或类作用域执行一段编译期代码，可以产生注入声明 | C++26 | [[dcl.pre#15]] |

## 常量求值器是一台严格的解释器

C++11 的 `constexpr` 函数只能有一条 `return` 语句。C++14 起（[[N3652]]），规则改为限制求值时能做什么：[[expr.const.core#2]] 列出了一张不允许出现的操作清单，函数体内可以写循环、局部变量和修改。

可以把常量求值器想成一个严格的解释器：

- 它知道每个对象的类型、数组边界、生命周期，以及联合体当前的活跃成员；
- 它不知道只在运行期存在的东西：非 const 全局变量的值、地址的具体数值、I/O；
- 它拒绝任何未定义行为。

所以一段代码只要不碰运行期状态、没有 UB、不把编译期分配的内存带出去、不做类型双关，通常就能在编译期求值。

### 编译期分配的内存不能逃逸

C++20 允许在常量求值中使用 `new`、`delete`，以及 `std::vector`、`std::string`（[[P0784R7]]），但分配的内存必须在同一次常量求值中释放（[[expr.const.core#2.20]]）：

```cpp
#include <vector>
constexpr std::vector<int> v{1, 2, 3};                // error: 内存逃逸到运行期
constexpr int n = std::vector<int>{1, 2, 3}.size();   // OK：临时 vector 在求值内销毁
```

要得到一个编译期算出的序列，常用两步法：先用动态容器算出长度，再把内容复制进定长的 `std::array`。

```cpp run ok
#include <algorithm>
#include <array>
#include <vector>

constexpr std::vector<int> primes_upto(int n) {
  std::vector<int> v;
  for (int i = 2; i <= n; ++i) {
    bool p = true;
    for (int d : v) {
      if (d * d > i) break;
      if (i % d == 0) { p = false; break; }
    }
    if (p) v.push_back(i);
  }
  return v;
}

constexpr auto primes = [] {
  std::array<int, primes_upto(50).size()> a{};   // 第一次求值：只取长度
  std::ranges::copy(primes_upto(50), a.begin()); // 第二次求值：复制内容
  return a;
}();

static_assert(primes.size() == 15 && primes.back() == 47);
int main() { return primes[3]; }   // 7
```

C++26 的 `std::define_static_array` 可以直接把编译期得到的范围放进静态存储的数组，不再需要两步法。

## 常量求值能抓住 UB

[[expr.const.core#2.8]] 规定，会产生未定义行为或错误行为（erroneous behavior，[[g:erroneous-behavior]]）的操作，使表达式不是核心常量表达式。`static_assert` 这类场合要求常量表达式，所以编译器必须在这里报告 UB。标准只在这一处强制要求检测 UB。

把单元测试写成 `static_assert`，编译器就会证明这组输入没有核心语言的 UB：

```cpp error
#include <cstddef>
constexpr int find_last(const int* a, std::size_t n, int x) {
  for (std::size_t i = n; i >= 0; --i)    // bug：size_t 永远 >= 0
    if (a[i - 1] == x) return int(i - 1);
  return -1;
}
constexpr int test() {
  int a[3] = {1, 2, 3};
  return find_last(a, 3, 42);
}
static_assert(test() == -1);   // error: 越界访问（下标回绕成一个巨大的值）
```

Clang 的诊断指出了越界的位置：`cannot refer to element 18446744073709551615 of array of 3 elements`。同样的代码在运行期是越界读，可能碰巧通过，也可能崩溃。

下面每个函数都含有一种典型的 UB，每条 `static_assert` 都会失败：

```cpp error
#include <climits>
constexpr int t1() { int x = INT_MAX; return x + 1; }               // 有符号溢出
constexpr int t2() { int a[2]{}; return a[2]; }                     // 越界读
constexpr int t3() { int* p = new int(1); delete p; return *p; }    // 释放后使用
constexpr int t4() { int* p = new int(1); delete p; delete p; return 0; }   // 重复释放
constexpr int t5() { int* p = new int[2]; delete p; return 0; }     // new[] 配 delete
constexpr int t6() { int x; return x; }                             // 读未初始化的值（C++26 起是错误行为）
union U { int i; float f; };
constexpr float t7() { U u{.i = 1}; return u.f; }                   // 读非活跃的联合体成员
struct B { virtual constexpr ~B() = default; };
struct D : B { int d = 1; };
constexpr int t8() { B b; return static_cast<D&>(b).d; }            // 错误的向下转换

static_assert(t1() == 0);   // error
static_assert(t2() == 0);   // error
static_assert(t3() == 0);   // error
static_assert(t4() == 0);   // error
static_assert(t5() == 0);   // error
static_assert(t6() == 0);   // error
static_assert(t7() == 0);   // error
static_assert(t8() == 0);   // error
```

Clang 对每一条都指向了 UB 本身，例如 `value 2147483648 is outside the range of representable values of type 'int'`、`read of heap allocated object that has been deleted`、`non-array delete used to delete pointer to array object of type 'int[2]'`、`read of member 'f' of union with active member 'i'`、`cannot cast object of dynamic type 'B' to type 'D'`。

!!! warning "这种检查的局限"
    1. 只检查实际执行的路径和给定的输入。`static_assert(f(3) == 9)` 通过，不代表 `f(INT_MAX)` 没有 UB。
    2. 标准库的 UB 是否被检测是未指定的（[[expr.const.core#4]]）。`std::vector::operator[]` 越界通常会因为底层的核心语言越界而被发现，但标准不保证。
    3. `[[assume(false)]]` 这类运行期未定义行为是否被检测，由实现定义（[[expr.const.core#3]]）。
    4. 编译器未必完全跟上标准。当前草案规定，有限的浮点操作数算出无穷大时不是常量表达式（[[expr.const.core#2.9]]），本机 Clang 23 仍然接受 `constexpr double d = DBL_MAX * 2;`。
    5. 只能覆盖可以在编译期求值的代码，I/O、线程、系统调用、`reinterpret_cast` 都不行。

## 三种分支

`if constexpr`、`if consteval` 和 `std::is_constant_evaluated()` 看起来都在问是不是编译期，实际问的不是同一个问题：

| | `if constexpr (C)` | `if consteval` | `if (std::is_constant_evaluated())` |
|---|---|---|---|
| 问的问题 | 常量 C 的值 | 当前求值是否显然常量求值 | 同左 |
| 何时决定 | 翻译时或模板实例化时，静态决定 | 每次求值时 | 每次求值时 |
| 没有选中的分支 | 被丢弃，在模板中不实例化，可以是非良构的 | 正常编译，必须良构 | 正常编译，必须良构 |
| 第一个分支能否以非常量实参调用 `consteval` 函数 | 不能 | 能 | 不能 |
| 典型用途 | 按类型分派，如 `if constexpr (std::is_integral_v<T>)` | 编译期和运行期两套实现 | 同左，C++20 的写法 |

`if consteval` 的第一个分支是**立即函数语境**（immediate function context，[[g:immediate-function-context]]），在那里调用 `consteval` 函数不要求是常量表达式。

```cpp run ok
#include <cstddef>
#include <cstring>
#include <type_traits>

template<class T>
constexpr void copy_n(T* dst, const T* src, std::size_t n) {
  if consteval {
    for (std::size_t i = 0; i < n; ++i) dst[i] = src[i];   // 编译期：逐个元素
  } else {
    if constexpr (std::is_trivially_copyable_v<T>)
      std::memcpy(dst, src, n * sizeof(T));               // 运行期：memcpy（不是 constexpr 函数）
    else
      for (std::size_t i = 0; i < n; ++i) dst[i] = src[i];
  }
}
constexpr int t() { int a[3]{1, 2, 3}, b[3]{}; copy_n(b, a, 3); return b[2]; }
static_assert(t() == 3);
int main() { int a[3]{1, 2, 3}, b[3]{}; copy_n(b, a, 3); return b[2] - 3; }
```

!!! pitfall "`if constexpr (std::is_constant_evaluated())`"
    `if constexpr` 的条件本身是显然常量求值的，`is_constant_evaluated()` 在那里永远是 `true`，运行期分支直接被丢弃。Clang 对此给出警告 `'std::is_constant_evaluated' will always evaluate to 'true' in a manifestly constant-evaluated expression`。

## 初始化：constexpr、constinit 与 const

| 声明 | 必须常量初始化 | 隐含 const | 可用于常量表达式 | 适用的存储期 |
|---|---|---|---|---|
| `constexpr T x = e;` | 是 | 是 | 是 | 任意 |
| `constinit T x = e;` | 是 | 否 | 否（另加 `const` 且为整型或枚举时例外） | 静态、线程 |
| `const int x = e;` | 否，成功时是 | 是 | 常量初始化成功时是（仅限整型和枚举） | 任意 |
| `T x = e;`（静态存储期） | 否，成功时是 | 否 | 否 | |

**静态初始化**指在程序开始执行前就完成的初始化（[[g:static-initialization]]）。不加 `constinit` 时，一个全局变量是否静态初始化，取决于初始化器能否在编译期求值，编译器不会告诉你结果。`constinit` 把它变成编译器检查的保证，从而排除了静态初始化顺序问题（[[g:static-initialization-order-fiasco]]）；同时变量之后仍可修改，这一点 `constexpr` 做不到。见 [[expr.const.init]]。

```cpp run ok
constinit int counter = 0;               // 可修改，但保证没有初始化顺序问题
constinit thread_local int depth = 0;    // 跨翻译单元访问时，编译器可以省去 TLS 初始化的包装函数
int main() { return counter + depth; }
```

## 模板、概念与常量表达式

在 `constexpr` 函数出现之前，编译期计算只能靠模板。三代写法对比：

```cpp ok
// C++98：类模板当函数，特化当分支
template<int N> struct Fact { static const int value = N * Fact<N - 1>::value; };
template<>      struct Fact<0> { static const int value = 1; };
static_assert(Fact<5>::value == 120);

// C++11：只有一条 return 的递归
constexpr int fact11(int n) { return n <= 1 ? 1 : n * fact11(n - 1); }

// C++14 起：普通代码
constexpr int fact14(int n) { int r = 1; while (n > 1) r *= n--; return r; }

static_assert(fact11(5) == 120 && fact14(5) == 120);
```

今天计算值用 `constexpr` 函数，计算类型仍然用模板，因为类型不是值，函数不能返回类型。C++26 的反射把类型表示成 `std::meta::info` 值，才打破了这个界限。

概念和 `requires` 子句是编译期谓词。原子约束代入后的结果是显然常量求值的（[[expr.const.defns#1.5]]），所以约束里可以调用 `constexpr` 函数：

```cpp ok
constexpr bool is_pow2(unsigned n) { return n && !(n & (n - 1)); }

template<unsigned N> requires (is_pow2(N))
struct RingBuffer { /* 用 & (N-1) 代替 % N */ };

RingBuffer<64> ok;
// RingBuffer<60> bad;   // error: 约束不满足
```

C++20 起，非类型模板形参可以是浮点数，也可以是**结构化类型**（structural type，[[g:structural-type]]）的类对象，大致是所有成员都公开、不是 `mutable` 的类：

```cpp ok
struct Point { int x, y; };
template<Point P> constexpr int manhattan = (P.x < 0 ? -P.x : P.x) + (P.y < 0 ? -P.y : P.y);
static_assert(manhattan<Point{3, -4}> == 7);
```

## consteval：必须在编译期

`consteval` 函数叫做**立即函数**（[[g:immediate-function]]）。不在立即函数语境中时，对它的每次调用都是立即调用，必须是常量表达式（[[expr.const.imm]]）。典型用途有三种：

- 在编译期校验输入。`std::format` 在编译期解析格式串，错误的格式说明符是编译错误。
- 只在编译期有意义、不应生成代码的函数。反射库的函数全部是 `consteval`。
- 强制在编译期计算，例如为 `switch` 生成 `case` 标签：

```cpp run ok
#include <cstdint>
#include <string_view>
consteval std::uint32_t fnv1a(std::string_view s) {
  std::uint32_t h = 2166136261u;
  for (char c : s) { h ^= static_cast<unsigned char>(c); h *= 16777619u; }
  return h;
}
constexpr std::uint32_t fnv1a_rt(std::string_view s) {   // 运行期版本，用于 switch 的条件
  std::uint32_t h = 2166136261u;
  for (char c : s) { h ^= static_cast<unsigned char>(c); h *= 16777619u; }
  return h;
}
int dispatch(std::string_view cmd) {
  switch (fnv1a_rt(cmd)) {
  case fnv1a("start"): return 1;
  case fnv1a("stop"):  return 2;
  default:             return 0;
  }
}
int main() { return dispatch("stop") == 2 ? 0 : 1; }
```

`consteval` 曾经很难用在泛型代码里。C++23 的 [[P2564R3]] 规定：一个 `constexpr` 函数模板的特化，如果调用了 `consteval` 函数而这次调用不是常量表达式，这个特化会自动变成立即函数。非模板的 `constexpr` 函数不会这样升级：

```cpp error
consteval int id(int x) { return x; }
template<class T> constexpr int tf(T x) { return id(x); }  // OK：tf<int> 升级为立即函数
constexpr int nf(int x) { return id(x); }                 // error: 不是常量表达式
```

需要两套实现时，在非模板函数里用 `if consteval`。

## 静态反射 {{c++26}}

[[P2996R13]] 让程序在编译期把自身的结构当作数据处理：`^^T` 得到类型 `T` 的反射，一个 `std::meta::info` 值；`[: r :]` 把反射拼回代码。配合 C++26 的展开语句 `template for`，枚举值转字符串可以这样写：

```cpp
#include <meta>
#include <string_view>
#include <type_traits>

template<typename E> requires std::is_enum_v<E>
constexpr std::string_view enum_to_string(E value) {
  template for (constexpr auto e :
                std::define_static_array(std::meta::enumerators_of(^^E))) {
    if (value == [:e:])
      return std::meta::identifier_of(e);
  }
  return "<unnamed>";
}

enum class Color { red, green, blue };
static_assert(enum_to_string(Color::green) == "green");
```

反射值是**只在编译期存在的值**（consteval-only value，[[expr.const.const#1]]），不能进入运行期的对象。`consteval { ... }` 块配合 `std::meta::define_aggregate` 还能在编译期定义类。这让常量求值有了副作用，标准用求值上下文等规则保证结果不依赖求值顺序（[[expr.const.reflect]]）。

本机 Clang 23 不支持反射，本节的例子没有经过编译，可以在 Compiler Explorer 上用实验性的反射实现试验。

## 演进

| 版本 | 主要变化 |
|---|---|
| C++98 | 整型常量表达式；模板元编程 |
| C++11 | `constexpr` 变量与函数（[[N2235]]），函数体只能有一条 `return`；`static_assert` |
| C++14 | 放宽 `constexpr` 函数（[[N3652]]）：局部变量、循环、修改局部对象 |
| C++17 | `if constexpr`（[[P0292R2]]）；`constexpr` lambda |
| C++20 | `consteval`（[[P1073R3]]）、`constinit`（[[P1143R2]]）、`std::is_constant_evaluated`（[[P0595R2]]）；编译期动态分配和 `constexpr` 的 `vector`、`string`（[[P0784R7]]）；`constexpr` 虚函数、`try`、`dynamic_cast`、切换联合体活跃成员；概念；类类型的非类型模板形参 |
| C++23 | `if consteval`（[[P1938R3]]）；`consteval` 向上传播（[[P2564R3]]）；在常量表达式中使用未知值的引用（[[P2280R4]]）；`constexpr` 函数中允许非字面类型的变量、`goto`、`static constexpr` 变量 |
| C++26 | 从 `void*` 转换、placement new、异常进入常量求值；`constexpr` 结构化绑定；静态反射、`consteval` 块、展开语句 |

条款层面的细节见 [[expr.const]]。

## 常见陷阱

!!! pitfall "constexpr 函数的形参不是常量"
    `constexpr void f(int n) { static_assert(n > 0); }` 总是错误，`std::array<int, n>` 也一样。`static_assert` 是一个独立的常量表达式，读取 `n` 是对一个生命周期不在这个表达式内开始的对象做左值到右值转换（[[expr.const.core#2.10]]）。Clang 的说法是 `function parameter 'n' with unknown value cannot be used in a constant expression`。要传常量，用模板形参。

!!! pitfall "编译期和运行期两套实现必须等价"
    如果 `if consteval` 的两个分支结果不同，同一个调用在 `constexpr int x = f();` 和 `int x = f();` 中会得到不同的值；而后者走哪个分支，还取决于编译器能否在编译期完成初始化（见思考题 1）。

!!! pitfall "全局 const 变量是否是常量，取决于初始化器"
    `const int n = g();` 中一个看似无关的改动，例如在 `g` 里加一行日志，会让 `n` 从静态初始化变成动态初始化，也不再能用于常量表达式。需要常量时写 `constexpr`，需要静态初始化时写 `constinit`。

!!! pitfall "函数内的 constexpr 变量是自动存储期的"
    `constexpr std::array<int, 1000> table = make();` 写在函数里，按语义每次调用都在栈上有一份。需要唯一的地址或要返回指向它的指针时，写 `static constexpr`（C++23 起也可以写在 `constexpr` 函数中）。

!!! pitfall "编译期计算有代价"
    常量求值器是解释器，比原生代码慢几个数量级，还受实现限制（Clang 的 `-fconstexpr-steps`、GCC 的 `-fconstexpr-ops-limit` 等）。超出限制时，在要求常量的场合是编译错误；在 `const int x = ...;` 中则没有任何提示地退回到动态初始化。

!!! pitfall "浮点结果可能与运行期不同"
    标准不保证翻译期和运行期的浮点计算结果一致（[[expr.const.general]]），在 x87、`-ffast-math`、FMA 收缩或修改了舍入模式时尤其如此。

## 思考题

!!! question "思考题 1"
    下面的 `a`、`b`、`c` 分别是多少？把 `if constexpr (std::is_constant_evaluated())` 换成 `if consteval` 呢？

    ```cpp
    #include <type_traits>
    constexpr int g() {
      if constexpr (std::is_constant_evaluated()) return 1;
      else return 2;
    }
    constexpr int a = g();
    int b = g();
    int rt;
    int c = g() + rt * 0;
    ```

<details markdown="1">
<summary>答案</summary>

全部是 1。`if constexpr` 的条件是显然常量求值的，`is_constant_evaluated()` 在那里永远是 `true`，`else` 分支在定义 `g` 时就被丢弃，`g` 实际上就是 `return 1;`。

换成 `if consteval` 后，结果是 `1 1 2`。`a` 在编译期求值。`b` 是静态存储期变量，编译器先尝试把它的初始化器当作常量表达式求值（[[expr.const.defns#1]]），成功了，于是静态初始化，走第一个分支。`c` 的初始化器读了非 const 变量 `rt`，尝试失败，退回到运行期的动态初始化，走 `else` 分支。本机 Clang 23 运行结果与此相同。
</details>

!!! question "思考题 2"
    哪种写法能同时保证：`table` 在编译期算好，程序中只有一份，运行期可以修改？

    ```cpp
    #include <array>
    constexpr auto make() { std::array<int, 4> a{}; for (int i = 0; i < 4; ++i) a[i] = i * i; return a; }
    // (A) constexpr auto table = make();
    // (B) constinit auto table = make();
    // (C) static const auto table = make();
    // (D) auto table = make();
    ```

<details markdown="1">
<summary>答案</summary>

(B)，前提是写在命名空间作用域，或者在块作用域写成 `static constinit`。`constinit` 保证静态初始化，而且不隐含 `const`，运行期可以修改。

(A) 不能修改。(C) 是 `const`，而且不保证静态初始化，虽然实际上会是。(D) 能在编译期求值时实际上也会常量初始化，但这一点不受检查，改动 `make` 可能让它退回到动态初始化。
</details>

!!! question "思考题 3"
    为什么 C++ 规定常量求值中的 UB 使表达式不是常量，而不是规定 UB 的结果未指定？

<details markdown="1">
<summary>答案</summary>

常量表达式的值会进入类型系统（模板实参、数组边界），也受 ODR 约束：`X<f()>` 在两个翻译单元中必须是同一个类型。如果 UB 可以产生任意值，不同的编译器、甚至同一编译器在不同翻译单元中，可能得出不同的类型，程序就失去了一致的含义。编译器在常量求值中本来就完整地模拟了对象模型，检测 UB 的成本很低。所以标准规定有 UB 就不是常量（[[expr.const.core#2.8]]），在要求常量的场合就是编译错误。
</details>
