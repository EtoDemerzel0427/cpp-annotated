---
title: 编译期编程
summary: constexpr、consteval、constinit、if constexpr、if consteval、模板与概念、静态反射——C++ 编译期工具箱的分工、演进与陷阱；以及"常量求值是 UB 检测器"
status: done
since: c++11
order: 30
papers: N2235, N3652, P0292R2, P0784R7, P1073R3, P1143R2, P0595R2, P1938R3, P2564R3, P2280R4, P2996R13
related: expr.const, expr.const.core, expr.const.init, expr.const.imm, expr.const.defns, dcl.constexpr, dcl.constinit, stmt.if, temp.arg.nontype, temp.constr
tags: 常量求值, constexpr, consteval, 模板, 反射
updated: 2026-10-17
---

C++ 有两门语言：一门在运行期执行，一门在编译期执行。从 C++98 的模板元编程（用类型和特化"计算"），到 C++11 的 `constexpr` 函数（用普通代码计算），再到 C++26 的静态反射（用普通代码**读写程序本身**），编译期那一门语言越来越像运行期那一门。本专题把散落在 [[expr.const]]、[[dcl.constexpr]]、[[dcl.constinit]]、[[stmt.if]]、[[temp]] 中的工具放在一起，回答三个问题：**各个工具管什么？什么时候用哪个？有哪些坑？**

## 工具箱一览

| 工具 | 作用对象 | 一句话语义 | 引入 | 条款 |
|---|---|---|---|---|
| `constexpr` 变量 | 变量 | 必须常量初始化 + 常量析构；隐含 `const`；可用于常量表达式 | C++11 | [[dcl.constexpr#6]] |
| `constexpr` 函数 | 函数 | **可以**在常量表达式中调用；也可以在运行期调用 | C++11（C++14 大幅放宽） | [[dcl.constexpr]] |
| `consteval` 函数 | 函数 | **只能**在编译期调用；每次调用必须是常量表达式 | C++20 | [[expr.const.imm]] |
| `constinit` | 静态/线程存储期变量 | 必须静态初始化；**不**隐含 `const` | C++20 | [[dcl.constinit]] |
| `if constexpr` | 语句 | 条件是常量；未选中分支被丢弃（模板中不实例化） | C++17 | [[stmt.if#2]] |
| `if consteval` | 语句 | 当前是否在显然常量求值中；第一分支是立即函数语境 | C++23 | [[stmt.if#4]] |
| `std::is_constant_evaluated()` | 表达式 | 同上，但不建立立即函数语境 | C++20 | [[meta.const.eval]] |
| `static_assert` | 声明 | 编译期断言 | C++11 | [[dcl.pre#13]] |
| 模板与 NTTP | 类型 / 值 | 以类型和常量值为参数生成代码；C++20 起 NTTP 可为浮点与结构化类类型 | C++98 / C++20 | [[temp.arg.nontype]] |
| 概念与 `requires` | 约束 | 编译期谓词，参与重载决议 | C++20 | [[temp.constr]] |
| 静态反射 `^^` / `[: :]` | 程序实体 | 把类型、成员、命名空间变成值（`std::meta::info`），在 consteval 代码中查询与生成 | C++26 | [[expr.const.reflect]] |
| `consteval { }` 块 | 声明 | 在命名空间/类作用域执行一段编译期代码，可产生注入声明 | C++26 | [[dcl.pre#15]] |

## 核心心智模型

### 1. 常量性是属性，编译期是时机

这是最重要、也最常被误解的一点：**`constexpr` 不等于"在编译期执行"**。

- "是否是常量表达式"是表达式的**属性**（[[expr.const.core]]、[[expr.const.const]]）。
- "是否在编译期求值"是**时机**。标准只在**显然常量求值**（[[expr.const.defns#1]]）的场合规定必须在翻译期求值：数组边界、模板实参、`static_assert`、`constexpr`/`constinit` 变量的初始化器、立即调用等。
- 其他场合，一个常量表达式**可以**在运行期求值；一个非常量表达式也**可以**被优化器折叠。

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

在本站测试的 Clang 23（arm64）上，即使用 `-O2`，`a` 仍然是一次真实的 `fib(20)` 调用（优化器没有展开这么深的递归），而 `b` 与 `c` 在汇编中直接是常数 6765。`-O0` 下更不必说。

**想要保证编译期**：用 `constexpr` 变量接住结果、作为模板实参、放进 `static_assert`，或把函数声明为 `consteval`。

### 2. 常量求值 = 在编译器里跑一台"干净的"抽象机

C++14 起，constexpr 的规则从"限制你能**写**什么"变成了"限制求值时能**做**什么"（[[expr.const.core#2]] 的黑名单）。可以把常量求值器想象成一个严格的解释器：

- 它知道每个对象的类型、边界、生命期、联合体的活跃成员；
- 它不知道任何运行期才存在的东西：非 const 全局变量的值、地址的数值、I/O；
- 它拒绝任何未定义行为。

于是有一条实用的判断法：**如果一段代码不碰运行期状态、没有 UB、不把编译期分配的内存带出来、不做类型双关，它几乎一定能 constexpr。**

### 3. 编译期内存不能逃逸

C++20 允许常量求值中使用 `new`/`delete`、`std::vector`、`std::string`（[[P0784R7]]），但分配必须在**同一次**常量求值中释放（[[expr.const.core#2.20]]）。所以：

```cpp
#include <vector>
constexpr std::vector<int> v{1, 2, 3};   // error: 编译期分配的内存逃逸到运行期
constexpr int n = std::vector<int>{1, 2, 3}.size();   // OK：临时 vector 在求值内销毁
```

常用的"两步法"：先在编译期用动态容器算出大小，再拷贝进定长 `std::array`：

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
    std::array<int, primes_upto(50).size()> a{};   // 第一次求值：只取大小
    std::ranges::copy(primes_upto(50), a.begin()); // 第二次求值：拷贝内容
    return a;
}();

static_assert(primes.size() == 15 && primes.back() == 47);
int main() { return primes[3]; }   // 7
```

C++26 的反射库提供了 `std::define_static_array` 一类工具，可以直接把编译期范围"提升"为静态存储的数组，省去两步法。

## 常量求值是 UB 检测器

[[expr.const.core#2.8]] 规定：会产生**未定义行为或错误行为**的操作使表达式不是核心常量表达式。由于 `static_assert` 等上下文**要求**常量表达式，编译器**必须**在这里诊断出 UB。这是 C++ 中唯一一处标准强制要求检测 UB 的地方。

把单元测试写成 `static_assert`，就得到了一个"由编译器证明无 UB"的测试——至少对那组输入而言：

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
static_assert(test() == -1);   // error: 越界访问 a[-1]（下标回绕为巨大的值）
```

Clang 的诊断会精确指出"cannot refer to element 18446744073709551615 of array of 3 elements"。运行期这段代码是越界读——可能"碰巧通过"，也可能崩溃。

能被检出的典型 UB：

```cpp error
#include <climits>
constexpr int t1() { int x = INT_MAX; return x + 1; }               // 有符号溢出
constexpr int t2() { int a[2]{}; return a[2]; }                     // 越界读
constexpr int t3() { int* p = new int(1); delete p; return *p; }    // 释放后使用
constexpr int t4() { int* p = new int(1); delete p; delete p; return 0; }   // 重复释放
constexpr int t5() { int* p = new int[2]; delete p; return 0; }     // new[] 配 delete
constexpr int t6() { int x; return x; }                             // 读未初始化值（C++26：错误行为）
union U { int i; float f; };
constexpr float t7() { U u{.i = 1}; return u.f; }                   // 读非活跃联合体成员
struct B { virtual constexpr ~B() = default; };
struct D : B { int d = 1; };
constexpr int t8() { B b; return static_cast<D&>(b).d; }            // 错误的向下转换

static_assert(t1() == 0);   // error: 每一条 static_assert 都会因相应的 UB 而失败
static_assert(t2() == 0);
static_assert(t3() == 0);
static_assert(t4() == 0);
static_assert(t5() == 0);
static_assert(t6() == 0);
static_assert(t7() == 0);
static_assert(t8() == 0);
```

Clang 对每一条都给出了指向 UB 本身的诊断，例如 "value 2147483648 is outside the range of representable values of type 'int'"、"read of dereferenced one-past-the-end pointer"、"read of heap allocated object that has been deleted"、"delete of pointer that has already been deleted"、"non-array delete used to delete pointer to array object of type 'int[2]'"、"read of uninitialized object"、"read of member 'f' of union with active member 'i'"。

!!! warning "UB 检测器的局限"
    1. **只检查实际执行的路径和给定的输入**。`static_assert(f(3) == 9)` 通过，不代表 `f(INT_MAX)` 没有 UB。
    2. **库的 UB 不保证被检测**（[[expr.const.core#4]]：未指定）。`std::vector::operator[]` 越界通常会因为底层的核心语言越界而被抓住，但这不是标准保证。
    3. **`[[assume(false)]]`** 这类"运行期未定义行为"是否被检测由实现定义（[[expr.const.core#3]]）。
    4. **编译器未必完全跟上标准**：例如当前草案要求有限浮点数溢出为无穷时非常量（[[expr.const.core#2.9]]），本站测试的 Clang 仍接受 `DBL_MAX * 2`。
    5. 只覆盖能 constexpr 的代码：I/O、线程、系统调用、`reinterpret_cast` 都不行。

## 分支：`if constexpr` vs `if consteval` vs `is_constant_evaluated()`

三者经常被混淆，因为它们看起来都在问"编译期吗？"：

| | `if constexpr (C)` | `if consteval` | `if (std::is_constant_evaluated())` |
|---|---|---|---|
| 问的问题 | C 的**值**是什么（C 必须是常量） | 当前求值是否是显然常量求值 | 同左 |
| 何时决定 | 模板实例化/翻译时，静态地 | 每次求值时 | 每次求值时 |
| 未选分支 | 被丢弃（模板中不实例化，可以不良构） | 正常编译，必须良构 | 正常编译，必须良构 |
| 第一分支能否调用 consteval 函数（用非常量实参） | 否 | **能**（立即函数语境） | 否 |
| 典型用途 | 按类型分派：`if constexpr (std::is_integral_v<T>)` | 编译期/运行期两套实现 | 同左（C++20 写法） |

```cpp
#include <cstring>
#include <type_traits>

template<class T>
constexpr void copy_n(T* dst, const T* src, std::size_t n) {
    if consteval {
        for (std::size_t i = 0; i < n; ++i) dst[i] = src[i];   // 编译期：逐元素
    } else {
        if constexpr (std::is_trivially_copyable_v<T>)
            std::memcpy(dst, src, n * sizeof(T));               // 运行期：memcpy（非 constexpr）
        else
            for (std::size_t i = 0; i < n; ++i) dst[i] = src[i];
    }
}
```

!!! pitfall "`if constexpr (std::is_constant_evaluated())`"
    `if constexpr` 的条件是显然常量求值的，`is_constant_evaluated()` 在那里**永远**为 true——运行期分支被直接丢弃。这是 C++20 最常见的误用之一，Clang 和 GCC 都会对此发出警告。

## 初始化：`constexpr` vs `constinit` vs `const`

| 声明 | 必须常量初始化？ | 隐含 const？ | 可用于常量表达式？ | 适用存储期 |
|---|---|---|---|---|
| `constexpr T x = e;` | 是 | 是 | 是 | 任意 |
| `constinit T x = e;` | 是 | 否 | 否（除非另加 const 且为整型等） | 静态/线程 |
| `const int x = e;` | 否（成功则是） | 是 | 若常量初始化则是（仅整型/枚举） | 任意 |
| `T x = e;`（静态存储期） | 否（成功则是） | 否 | 否 | — |

`constinit` 的价值在于把"这个全局变量是静态初始化的"从**默默的优化**变成**编译器检查的保证**，彻底排除静态初始化顺序问题；同时它允许变量之后被修改（`constexpr` 不允许）。见 [[expr.const.init]]。

```cpp
constinit int counter = 0;               // 可变，但保证无初始化顺序问题
constinit thread_local int depth = 0;    // 跨 TU 访问时编译器可以省去 TLS 初始化包装函数
```

## 模板、概念与常量表达式

在 constexpr 函数出现之前，编译期计算只能靠模板：

```cpp ok
// C++98 风格：类型即函数，特化即分支
template<int N> struct Fact { static const int value = N * Fact<N - 1>::value; };
template<>      struct Fact<0> { static const int value = 1; };
static_assert(Fact<5>::value == 120);

// C++11 风格：单一 return 的递归
constexpr int fact11(int n) { return n <= 1 ? 1 : n * fact11(n - 1); }

// C++14 起：普通代码
constexpr int fact14(int n) { int r = 1; while (n > 1) r *= n--; return r; }

static_assert(fact11(5) == 120 && fact14(5) == 120);
```

今天，**计算值**用 constexpr 函数；**计算类型**仍用模板（类型不是值，constexpr 函数不能返回类型——直到 C++26 反射把类型变成了 `std::meta::info` 值）。概念与 `requires` 子句是编译期谓词：其原子约束的代入结果是显然常量求值的（[[expr.const.defns#1.5]]），因此约束中可以调用 constexpr 函数：

```cpp ok
#include <concepts>
constexpr bool is_pow2(unsigned n) { return n && !(n & (n - 1)); }

template<unsigned N> requires (is_pow2(N))
struct RingBuffer { /* 用 & (N-1) 代替 % N */ };

RingBuffer<64> ok;
// RingBuffer<60> bad;   // error: 约束不满足
```

C++20 起非类型模板参数可以是浮点数和"结构化类型"的类对象（所有成员公开、非 mutable 等），这让常量值能以更丰富的形式在类型系统中流动：

```cpp ok
struct Point { int x, y; };
template<Point P> constexpr int manhattan = (P.x < 0 ? -P.x : P.x) + (P.y < 0 ? -P.y : P.y);
static_assert(manhattan<Point{3, -4}> == 7);
```

## consteval：必须在编译期

`consteval` 函数的每次调用（不在立即函数语境中时）都是立即调用，必须是常量表达式（[[expr.const.imm]]）。典型用途：

- **编译期校验输入**：`std::format` 的格式串在编译期解析，错误的格式说明符是编译错误；
- **不生成代码的元函数**：反射 API 全部是 consteval；
- **强制编译期计算**：`consteval auto hash(std::string_view)` 用于 `switch` 的标签。

```cpp ok
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
```

C++23 的**立即升级**（[[P2564R3]]）让 consteval 在泛型代码中可用：constexpr 函数模板如果调用了 consteval 函数而该调用不是常量，该实例化会自动变成 consteval。非模板的 constexpr 函数不会升级——在其中写非常量的 consteval 调用直接 ill-formed；需要两套实现时用 `if consteval`。

## 静态反射（C++26）

{{c++26}} [[P2996R13]] 让程序在编译期把自身的结构当作数据：`^^T` 得到类型 T 的反射（`std::meta::info` 值），`[: r :]` 把反射"拼接"回代码。配合 C++26 的展开语句（`template for`），经典的"枚举转字符串"可以这样写：

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

反射值是 **consteval-only 值**（[[expr.const.const#1]]）：它们不能进入运行期对象。`consteval { ... }` 块配合 `std::meta::define_aggregate` 甚至能在编译期**定义类**——这引入了"常量求值的副作用"，标准用合成点与求值上下文（[[expr.const.reflect]]）保证其确定性。

!!! impl "实现状态"
    截至写作时，本站使用的 Clang 23 发行版不支持反射；可在 Compiler Explorer 上使用实验性的 Clang 反射分支或其他实现试验上例。本节例子未经本地编译验证。

## 演进时间线

| 版本 | 关键变化 |
|---|---|
| C++98 | 整型常量表达式；模板元编程（类型即函数） |
| C++11 | `constexpr` 变量与函数（[[N2235]]）：单一 `return`；`static_assert` |
| C++14 | 放宽 constexpr（[[N3652]]）：局部变量、循环、修改本地对象 |
| C++17 | `if constexpr`（[[P0292R2]]）；constexpr lambda |
| C++20 | `consteval`（[[P1073R3]]）、`constinit`（[[P1143R2]]）、`is_constant_evaluated`（[[P0595R2]]）；瞬时分配与 constexpr `vector`/`string`（[[P0784R7]]）；constexpr 虚函数、`try`、`dynamic_cast`、联合体成员切换；概念；类类型 NTTP |
| C++23 | `if consteval`（[[P1938R3]]）；consteval 向上传播（[[P2564R3]]）；未知引用（[[P2280R4]]）；constexpr 函数中允许非字面变量、`goto`、`static constexpr` |
| C++26 | `void*` 转换、placement new、异常进入常量求值；constexpr 结构化绑定与对局部变量的 constexpr 引用；静态反射、consteval 块、展开语句 |

详细的条款级演进见 [[expr.const]]。

## 陷阱汇总

!!! pitfall "1. constexpr 函数的形参不是常量"
    `constexpr void f(int n) { static_assert(n > 0); }` 永远错误；`std::array<int, n>` 同理。形参的生命期不在 `static_assert` 这个独立常量表达式之内（[[expr.const.core#5]]）。要传常量，用模板参数。

!!! pitfall "2. 编译期与运行期两套实现必须等价"
    `if consteval` / `is_constant_evaluated()` 的两个分支若结果不同，同一个调用在 `constexpr int x = f();` 与 `int x = f();` 中会得到不同的值，而后者究竟走哪个分支还受"试算"规则影响（[[expr.const.defns#1]]）。

!!! pitfall "3. 全局 `const` 的'常量性'依赖初始化器能否试算成功"
    `const int n = g();` 中一个看似无关的改动（g 里加了日志）会让 n 从静态初始化变为动态初始化，并让 n 不再可用于常量表达式。需要常量时写 `constexpr`，需要静态初始化时写 `constinit`。

!!! pitfall "4. 函数内的 constexpr 变量是自动存储期的"
    `constexpr std::array<int, 1000> table = make();` 写在函数里，语义上每次调用都在栈上有一份。需要唯一地址或返回指针时写 `static constexpr`（C++23 起也可以出现在 constexpr 函数中）。

!!! pitfall "5. 编译期计算有代价"
    常量求值器是解释器，比原生代码慢几个数量级，并受实现限制约束（Clang `-fconstexpr-steps`、GCC `-fconstexpr-ops-limit` 等）。超过限制时，在要求常量的上下文中是编译错误，在 `const int x = ...` 中则**悄悄**变成动态初始化。

!!! pitfall "6. 浮点结果可能与运行期不同"
    标准不保证翻译期与运行期的浮点结果一致（[[expr.const.general]]），尤其在 x87、`-ffast-math`、FMA 收缩或修改舍入模式时。

## 思考题

!!! question "思考题 1"
    下面的 `g` 在不同调用方式下返回什么？

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

全部是 1。`if constexpr` 的条件是显然常量求值的，`is_constant_evaluated()` 在那里永远为 true，`else` 分支在定义 `g` 时就被丢弃——`g` 实际上就是 `return 1;`。与它是否在运行期被调用（`c` 是动态初始化）无关。若改为 `if consteval`，则 `a == 1`、`b == 1`（试算成功，静态初始化）、`c == 2`（读 `rt` 使试算失败，动态初始化）。
</details>

!!! question "思考题 2"
    以下哪种写法能保证 `table` 在编译期计算、程序中只有一份、并且运行期可以修改？

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

(B)，前提是写在命名空间作用域（或作为块作用域 `static constinit`）。`constinit` 保证静态初始化（编译期计算），且不隐含 const，运行期可以修改；命名空间作用域变量只有一份。(A) 不可修改；(C) 是 const 且不保证静态初始化（虽然实际上会是）；(D) 不保证静态初始化（虽然 `make()` 能常量求值时实际会被常量初始化，但这不受检查，改动 `make` 可能悄悄变成动态初始化）。
</details>

!!! question "思考题 3"
    为什么 C++ 选择"禁止常量求值中的 UB"而不是"常量求值中的 UB 结果未指定"？

<details markdown="1">
<summary>答案</summary>

常量表达式的值会进入类型系统（模板实参、数组边界）和 ODR：`X<f()>` 在两个翻译单元中必须是同一个类型。如果 UB 的结果可以是任意值，不同编译器、甚至同一编译器的不同 TU 可能得出不同的类型，程序就失去了一致的含义。而编译器在常量求值中本来就完整地模拟了对象模型，检测 UB 的成本很低。于是标准干脆要求：有 UB 就不是常量（[[expr.const.core#2.8]]），在要求常量的地方即为编译错误。
</details>

## 小结

- **constexpr 是"能"，consteval 是"必须"，constinit 是"静态初始化且可变"**。
- **常量性是属性，编译期是时机**：只有显然常量求值才保证编译期。
- **常量求值是一台不容忍 UB 的抽象机**：把测试写成 `static_assert`，编译器替你证明那组输入无 UB。
- **编译期内存不能逃逸**：用两步法或 C++26 的 `define_static_array`。
- **分支选择**：按类型分派用 `if constexpr`；编译期/运行期两套实现用 `if consteval`。
- **C++26 反射**让编译期代码能读写程序结构，并用合成点与求值上下文保证确定性。
