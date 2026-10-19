---
title: 基础类型
summary: 语言内建的类型：整数类型的宽度与补码表示、字符类型、bool、浮点类型与可选的扩展浮点类型、void、std::nullptr_t 和 std::meta::info。
status: draft
covers: basic.fundamental, basic.extended.fp
papers: P0907R4, P1236R1, P0482R6, P1467R9, P2996R13
related: basic.types, conv.rank, conv.prom, expr.arith.conv, conv.integral, basic.types.trivial, numeric.limits
tags: 类型系统, 整数, 浮点
updated: 2026-10-19
---

!!! tldr
    - C++20 起整数一律用补码表示，有符号与无符号之间的转换结果确定；但有符号运算溢出仍是 UB，无符号运算按模 2^N 回绕。
    - 整数类型的宽度由实现定义，标准只给下限：`int` 至少 16 位，`long` 至少 32 位。`long` 在 64 位 Linux 上是 64 位，在 64 位 Windows 上是 32 位。
    - `char`、`signed char`、`unsigned char` 是三个不同的类型；`char` 有没有符号取决于平台。
    - 浮点类型几乎不受约束：不要求 IEEE 754，只要求 `float` 的值都是 `double` 的值、`double` 的值都是 `long double` 的值。`std::float32_t` 等扩展浮点类型是可选的，而且与 `float` 是不同的类型。
    - 即使两个基础类型的表示完全相同（如 Windows 上的 `int` 和 `long`），它们仍是不同的类型。

**基础类型**（fundamental type）是语言内建、不由其他类型构造出来的类型：整数、字符、`bool`、浮点、`void`、`std::nullptr_t`，以及 C++26 新增的 `std::meta::info`（¶19）。本页讲 6.9.3 [[basic.fundamental]]，以及规定 `std::float16_t` 等可选浮点类型的 6.9.4 [[basic.extended.fp]]。

与整数相关的其他规则在转换等级 [[conv.rank]]、整数提升 [[conv.prom]]、常用算术转换 [[expr.arith.conv]] 和整数转换 [[conv.integral]]；各类型的取值范围可以用 `<limits>`（[[numeric.limits]]）查询。

## 整数类型

### 五种有符号整数类型（¶1、¶4）

¶1 **标准有符号整数类型**（standard signed integer type）有五种：`signed char`、`short int`、`int`、`long int`、`long long int`。列表中每个类型提供的存储至少和前面的一样多。实现还可以提供**扩展有符号整数类型**（extended signed integer type）。两者合称**有符号整数类型**。

一个有符号整数类型能表示的范围是 −2^(N−1) 到 2^(N−1)−1，其中 N 叫做这个类型的**宽度**（width）。这正是补码的范围。C++20 之前标准还允许反码和原码，它们的范围是对称的，而且有负零。

¶4 标准有符号整数类型的宽度不得小于表 14 的值，其余由实现决定。下表同时列出常见数据模型下的实际宽度：

| 类型 | 最小宽度 | ILP32（32 位系统） | LP64（64 位 Linux、macOS） | LLP64（64 位 Windows） |
|---|---|---|---|---|
| `signed char` | 8 | 8 | 8 | 8 |
| `short` | 16 | 16 | 16 | 16 |
| `int` | 16 | 32 | 32 | 32 |
| `long` | 32 | 32 | 64 | 32 |
| `long long` | 64 | 64 | 64 | 64 |
| 指针 | — | 32 | 64 | 64 |

`int` 的下限是 16 位而不是 32 位。需要确定宽度时，用 `<cstdint>` 的 `std::int32_t` 等类型（[[cstdint.syn]]）。`long` 在 LP64 和 LLP64 之间的差异，是跨平台代码中最常见的问题来源。

!!! lawyer "宽度也是单调的吗"
    ¶1 只说存储（`sizeof`）不减，没有直接说宽度不减。但 [[conv.rank#1.2]] 规定宽度更小的有符号类型等级更低，[[conv.rank#1.3]] 又规定 `long long`、`long`、`int`、`short`、`signed char` 的等级依次降低。如果某个实现让 `int` 比 `long` 宽，前一条推出 `int` 的等级高于 `long`，与后一条矛盾。所以宽度单调是这两条规则合起来的推论。

### 无符号类型与模算术（¶2）

¶2 每种有符号整数类型都有一个对应的、不同的无符号整数类型：`unsigned char`、`unsigned short`、`unsigned int`、`unsigned long`、`unsigned long long`，扩展有符号整数类型也各有对应的扩展无符号整数类型。无符号类型与对应的有符号类型宽度 N 相同，范围是 0 到 2^N−1，运算按模 2^N 进行。

```cpp run ub
#include <climits>

int main() {
  unsigned u = UINT_MAX;
  u = u + 1;            // OK: 按模 2^N，结果为 0
  int i = INT_MAX;
  i = i + 1;            // UB: 有符号溢出
  return u + i;
}
```

注 1 点出了这里的不对称：无符号运算不会溢出，结果总是取模；有符号运算溢出是未定义行为（[[expr.pre]]）。C++20 改用补码并没有改变这一点。保留这个 UB 的原因是编译器依赖它做优化，例如假设循环变量 `i + 1 > i` 恒成立。用 `-fsanitize=undefined` 运行上面的程序，UBSan 报告 `signed integer overflow`。

### 有符号与无符号共享表示（¶3、¶5）

¶3 无符号类型与对应的有符号类型具有相同的对象表示、值表示和对齐要求。对有符号类型的每个值 `x`，对应无符号类型中与 `x` 模 2^N 同余的那个值，值表示中的各位与 `x` 完全相同。例如有符号的 `-1` 与对应无符号类型的最大值表示相同。脚注说明这就是补码。

¶5 用**base-2 表示**把这一点形式化：无符号值 x 的 base-2 表示是 x = x₀·2⁰ + x₁·2¹ + … + x_{N−1}·2^(N−1)，每个系数是 0 或 1；有符号值的 base-2 表示就是对应无符号类型中同余值的 base-2 表示。`<bit>` 里的 `std::popcount`、`std::countl_zero` 等函数都按这个表示定义。

有了共享表示，再加上 [[conv.integral#3]]（整数转换的结果是模 2^N 同余的那个值），有符号与无符号之间的转换就不再有实现定义的成分：

```cpp run ok
#include <cassert>

int main() {
  int x = -1;
  unsigned u = x;                       // 4294967295（unsigned 为 32 位时）
  assert(u == ~0u);
  assert(static_cast<int>(u) == -1);    // C++20 起：取同余值，不再是实现定义
  assert((-8 >> 1) == -4);              // C++20 起：负数右移是算术移位
}
```

最后一行的规则在 [[expr.shift]]。[[basic.lval#11]] 允许通过 `unsigned int` 的 glvalue 读取 `int` 对象，读到的也正是同余值。

### 填充位（¶4）

¶4 还规定，整数类型的值表示恰好由 N 位构成。对象表示中如果还有多余的位，它们就是填充位（[[basic.types.general#2]]），填充位的每一种取值都只是同一个值的另一种表示。注 2 强调填充位的值未指定，但不会导致陷入。这一点与 C 不同，C 允许整数有陷阱表示。

### 标准整数类型与扩展整数类型（¶5）

¶5 标准有符号和标准无符号整数类型合称**标准整数类型**（standard integer type），扩展的两类合称**扩展整数类型**（extended integer type）。

!!! impl "`__int128` 不是扩展整数类型"
    GCC 和 Clang 在 64 位目标上提供 `__int128` 和 `unsigned __int128`，但通常不把它们作为标准意义上的扩展整数类型。原因之一是 `intmax_t` 必须能表示任何有符号整数类型的值，承认 128 位扩展整数类型就要把 `intmax_t` 改成 128 位，这会破坏已有的 ABI。各个库的 trait 结果并不统一：本机 libc++ 的 `std::is_integral_v<__int128>` 为 `true`，libstdc++ 的结果取决于是否启用 GNU 扩展模式。`_BitInt(N)` 在 C++ 里同样只是扩展。

## 底层类型（¶6）

¶6 如果规定某个基础类型以一个有符号或无符号整数类型为**底层类型**（underlying type），那么这两个类型的对象表示、值表示、对齐要求和取值范围都相同，每个值在两个类型中的表示也相同。

下面的 `char`、`wchar_t`、`char8_t`、`char16_t`、`char32_t` 都按这个模式定义：它们是独立的类型，表示却与某个整数类型完全一样。枚举的底层类型（[[dcl.enum]]）是同一个概念。

## 字符类型（¶7–¶9）

### `char` 是第三个类型（¶7）

```cpp run ok
#include <climits>
#include <cstdio>
#include <type_traits>

void f(char)          { std::puts("char"); }
void f(signed char)   { std::puts("signed char"); }
void f(unsigned char) { std::puts("unsigned char"); }

static_assert(!std::is_same_v<char, signed char>);
static_assert(!std::is_same_v<char, unsigned char>);

int main() {
  f('a');                            // char
  f(static_cast<signed char>(1));    // signed char
  f(static_cast<unsigned char>(1));  // unsigned char
  std::printf("char is %s\n", CHAR_MIN < 0 ? "signed" : "unsigned");
}
```

¶7 `char` 是一个独立的类型，底层类型由实现在 `signed char` 和 `unsigned char` 之间选择。不论选哪个，`char` 都不是那个类型，重载决议和模板特化都区分这三者。本机（arm64 macOS）运行打印 `char is signed`。

`char`、`signed char`、`unsigned char` 合称**普通字符类型**（ordinary character type），它们再加上 `char8_t` 合称[[g:narrow-character-type|窄字符类型]]（narrow character type）。窄字符类型的对象表示的每一种位模式都表示一个不同的值，没有填充位，也没有无效的位模式，所以可以安全地承载任意字节。注 5 补充，宽度大于类型宽度的窄字符类型位域仍然有填充位。

!!! impl "`char` 的符号性"
    x86 和 x86-64 的主流 ABI 中 `char` 有符号；AArch64、AArch32、PowerPC、RISC-V 的 Linux ABI 中 `char` 无符号。Apple arm64 是例外，`char` 有符号。GCC 和 Clang 可以用 `-funsigned-char` 或 `-fsigned-char` 改变，MSVC 用 `/J`，但这会改变 ABI 语义，整个程序必须一致。用 `c < 0` 判断非 ASCII 字节这类代码不可移植。

### `wchar_t`（¶8）

¶8 `wchar_t` 是独立的类型，底层类型是实现定义的某个整数类型。Windows 上它是 16 位的 `unsigned short`，存放 UTF-16 码元；x86-64 Linux 和 macOS 上是 32 位的 `int`，AArch64 Linux 上是 32 位的 `unsigned int`。

### `char8_t`、`char16_t`、`char32_t`（¶9）

¶9 `char8_t` 的底层类型是 `unsigned char`；`char16_t` 和 `char32_t` 的底层类型分别是 `std::uint_least16_t` 和 `std::uint_least32_t`（[[cstdint.syn]]）。

`char8_t` 是 C++20 加入的（[[P0482R6]]），它给 `u8` 字面量一个专属的类型。这是一个不兼容的改动：C++17 中 `u8"x"` 的类型是 `const char[2]`，C++20 起是 `const char8_t[2]`。

```cpp run error
const char*    a = u8"x";   // error（C++20 起）：const char8_t[2] 不能转为 const char*
const char8_t* b = u8"x";   // OK
```

`char8_t` 是窄字符类型，但不是普通字符类型。[[basic.lval#11]] 允许用来访问任意对象字节的只有 `char`、`unsigned char` 和 `std::byte`，不包括 `char8_t`。这是引入它的另一个好处：编译器可以假定 `char8_t*` 不会和其他类型的对象别名，优化更积极。

## `bool`（¶10）

¶10 `bool` 是独立的类型，与某个实现定义的无符号整数类型具有相同的对象表示、值表示和对齐要求。`bool` 的值只有 `true` 和 `false`。注 6 说明没有 `signed bool`、`unsigned bool`、`short bool` 和 `long bool`。

如果 `bool` 的值表示与 `unsigned char` 相同，它就有 8 位、256 种位模式，其中只有两种对应 `bool` 的值。用 `memcpy` 把字节 `0x02` 放进一个 `bool`，读取它就是 UB，例子见 [[basic.types.trivial]]。`sizeof(bool)` 由实现定义，主流平台上是 1。

`bool` 是整型，参与整数提升（提升为 `int`，[[conv.prom]]），等级低于所有其他整数类型（[[conv.rank#1.6]]）。C++17 移除了 `bool` 的 `++`，`--` 从来就不允许。

## 整型：术语的层次（¶11）

¶11 `char`、`wchar_t`、`char8_t`、`char16_t`、`char32_t` 合称**字符类型**（character type）。字符类型、`bool`、有符号和无符号整数类型以及它们的 cv 版本，合称**整型**（integral type），也叫整数类型（integer type）。注 7 指出枚举不是整型，但无作用域枚举可以提升为整型（[[conv.prom]]）。

这些名称相互交叠，容易混淆：

| 术语 | 包含 |
|---|---|
| 有符号整数类型 | `signed char` `short` `int` `long` `long long`，加上扩展类型 |
| 无符号整数类型 | `unsigned char` 到 `unsigned long long`，加上扩展类型 |
| 标准整数类型 | 上面两行中的标准类型，不含 `char`、`bool`、`wchar_t` 等 |
| 字符类型 | `char` `wchar_t` `char8_t` `char16_t` `char32_t` |
| 普通字符类型 | `char` `signed char` `unsigned char` |
| 窄字符类型 | 普通字符类型和 `char8_t` |
| 整型（整数类型） | 字符类型、`bool`、有符号和无符号整数类型，以及 cv 版本 |

所以 `signed char` 是有符号整数类型和普通字符类型，却不是字符类型；`char` 是字符类型和普通字符类型，却既不是有符号整数类型也不是无符号整数类型，即使它的底层类型是 `signed char`。这个区别在 [[expr.arith.conv]] 和 [[conv.prom]] 里有实际后果。

## 浮点类型（¶12–¶14）

¶12 `float`、`double`、`long double` 是三个不同的类型。`double` 的精度至少与 `float` 相同，`long double` 至少与 `double` 相同；`float` 的值集合是 `double` 值集合的子集，`double` 的又是 `long double` 的子集。这三个类型及其 cv 版本合称**标准浮点类型**。

实现还可以提供其他表示浮点值的类型，并把它们规定为[[g:extended-floating-point-type|扩展浮点类型]]（extended floating-point type）。标准浮点类型和扩展浮点类型合称[[g:floating-point-type|浮点类型]]（floating-point type）。

注 8 提醒，实现提供了、但没有规定为扩展浮点类型的那些类型，不算浮点类型，标准对它们不作任何要求。本机 Clang 23 的 `_Float16` 就是这样：它能做算术，但 libc++ 的 `std::is_floating_point_v<_Float16>` 为 `false`。

除了 [[basic.extended.fp]] 规定的部分，浮点类型的对象表示、值表示和运算精度都由实现定义。C++ 不要求 IEEE 754（ISO/IEC 60559），可以用 `std::numeric_limits<T>::is_iec559` 查询。

!!! impl "`long double` 的几种实现"
    - x86-64 Linux：x87 的 80 位扩展精度，`sizeof` 为 16，其中 48 位是填充。
    - Windows（MSVC）和 Apple arm64：与 `double` 相同，64 位。本机 `__SIZEOF_LONG_DOUBLE__` 为 8。
    - AArch64 Linux 和部分 PowerPC：128 位四精度（binary128，通常由软件实现）或 double-double。

    `long double` 是最不可移植的算术类型。需要四精度时，应使用 `std::float128_t`（如果实现提供）。

¶13 浮点类型的**可表示值范围**至少是从最小的有限负数到最大的有限正数。如果类型能表示负无穷，范围扩展到全部负实数；能表示正无穷，则扩展到全部正实数。注 9 指出，符合 ISO/IEC 60559 的类型有两种无穷，所以全部实数（不包括无穷和 NaN 本身）都在可表示范围内。

这条规则决定了浮点运算何时是 UB。[[expr.pre#4]] 规定，算术表达式的数学结果既不在可表示范围内、也不是该类型的无穷或 NaN 时，行为未定义。对 IEEE 类型，任何实数结果都在范围内，所以 `FLT_MAX * 2.0f` 不是 UB，结果是正无穷。按 [[expr.pre]] 注 4，这种类型上唯一会导致 UB 的算术运算是除以零。没有无穷的浮点格式上，溢出仍是 UB。

¶14 整型和浮点类型合称**算术类型**（arithmetic type）。

## `void`（¶15）

¶15 cv `void` 是无法完成的不完整类型，值集合为空。所以没有 `void` 对象、`void` 数组和 `void&`，但有 `void*`（[[basic.compound]]）。

`void` 类型的表达式仍然可以出现在一些地方，注 11 列出了它们：

```cpp run ok
void v() {}
void w() { return v(); }       // return 的操作数可以是 void 表达式

template<class F> auto call(F f) { return f(); }   // F 返回 void 时也能用

int main() {
  (void)0;                     // 显式转换为 void
  static_cast<void>(42);
  int k = (v(), 1);            // 逗号表达式的操作数
  true ? v() : w();            // ?: 的两个分支都是 void
  decltype(v())* p = nullptr;  // decltype(v()) 是 void
  (void)p; (void)k;
  call(v);
}
```

除此之外，`void` 表达式还可以是表达式语句、括号表达式、*requires-expression* 中的要求，以及 `typeid`、`noexcept` 的操作数。

允许 `return v();` 是有意的设计：`call` 这样的转发包装因此不必为返回 `void` 的函数单独特化。

## `std::nullptr_t`（¶16）

```cpp run ok
#include <cstddef>
#include <cstdio>

void f(int)   { std::puts("int"); }
void f(char*) { std::puts("char*"); }

static_assert(sizeof(std::nullptr_t) == sizeof(void*));

int main() {
  f(nullptr);              // char*：nullptr 不能转换为 int
  std::nullptr_t n;        // 未初始化
  char* p = n;             // OK：读取 n 并不访问它的存储
  f(p);
}
```

¶16 cv `std::nullptr_t` 是独立的类型。`std::nullptr_t` 类型的 prvalue 是**空指针常量**，可以转换为任何指针和成员指针类型（[[conv.ptr]]、[[conv.mem]]）。它的大小和对齐要求与 `void*` 相同。

注 12 指出，它的值表示可以不含任何位，因为这个类型只有一个值。所以 [[conv.lval#3.1]] 规定，对 `nullptr_t` 的 glvalue 做左值到右值转换，结果直接是空指针常量，并不访问对象。上例读取了未初始化的 `n`，却完全合法。

`f(nullptr)` 调用 `f(char*)`，因为 `nullptr` 不能转换为 `int`。如果写 `f(NULL)`，结果取决于 `NULL` 的定义，可能调用 `f(int)`，也可能有歧义。

`nullptr_t` 是标量类型，但不是指针类型：`std::is_pointer_v<std::nullptr_t>` 为 `false`，它有自己的主类别 `std::is_null_pointer`。

## `std::meta::info` {{c++26}}（¶17–¶18）

```cpp
#include <meta>

struct S { int mem; };
constexpr std::meta::info r1 = ^^S;         // 表示一个类型
constexpr std::meta::info r2 = ^^S::mem;    // 表示一个类成员
constexpr std::meta::info r0{};             // 空反射
static_assert(r1 != r2 && r0 == std::meta::info{});
```

本机 Clang 23 还没有实现静态反射，这段代码没有经过编译验证。

¶17 `std::meta::info` 类型的值叫做**反射**（reflection）。它们来自 C++26 的静态反射（[[P2996R13]]）：`^^S` 这样的表达式产生一个反射，表示 `S` 这个构造。存在唯一的**空反射**（null reflection）；其他每个反射都表示下列构造之一：标量类型的值、静态存储期的对象、变量、结构化绑定、函数、函数形参、枚举项、注解、类型别名、类型、类成员、无名位域、类模板、函数模板、变量模板、别名模板、概念、命名空间别名、命名空间、直接基类关系、数据成员描述。

¶18 是推荐做法：实现不应把标准规定的其他构造表示为 `std::meta::info` 的值，例如 *using-declarator*、偏特化、属性、占位类型、语句和表达式。注 14 说明将来的标准可能会规定它们的语义，实现现在自行支持，将来就可能与标准冲突。

`std::meta::info` 是基础类型，也是标量类型（[[basic.types.general#7]]），所以可以用作非类型模板形参的类型。它的主类别 trait 是 `std::is_reflection`（[[meta.unary.cat]]）。

## 表示相同也是不同的类型（¶19）

```cpp run error
void g(long*);
int main() {
  int i = 0;
  g(&i);       // error: int* 不能转换为 long*，即使两者表示相同
}
```

¶19 本节描述的类型统称基础类型。注 15 指出，即使实现让两个基础类型的值表示相同，它们仍是不同的类型。在 LLP64 上，`int` 和 `long` 都是 32 位补码，但 `int*` 不能隐式转换为 `long*`，`f(int)` 和 `f(long)` 是两个重载，`int` 与 `long` 也不布局兼容（[[basic.types.general#9]]）。

## 可选的扩展浮点类型（[[basic.extended.fp]]）{{c++23}}

C++23 的 [[P1467R9]] 为常见的浮点格式规定了标准名称。实现如果支持具有相应性质的扩展浮点类型，就要在 `<stdfloat>` 中声明对应的类型别名，定义对应的宏（[[cpp.predefined]]），并支持对应的字面量后缀（[[lex.fcon]]）。¶1–¶5 各规定一种：

| 别名（`<stdfloat>`） | ISO/IEC 60559 格式 | 总位数 | 精度 | 指数位 | 宏 | 后缀 |
|---|---|---|---|---|---|---|
| `std::float16_t` | binary16 | 16 | 11 | 5 | `__STDCPP_FLOAT16_T__` | `f16` `F16` |
| `std::float32_t` | binary32 | 32 | 24 | 8 | `__STDCPP_FLOAT32_T__` | `f32` `F32` |
| `std::float64_t` | binary64 | 64 | 53 | 11 | `__STDCPP_FLOAT64_T__` | `f64` `F64` |
| `std::float128_t` | binary128 | 128 | 113 | 15 | `__STDCPP_FLOAT128_T__` | `f128` `F128` |
| `std::bfloat16_t` | 无名称 | 16 | 8 | 8 | `__STDCPP_BFLOAT16_T__` | `bf16` `BF16` |

¶6 的注说明，精度包括有效数字开头隐含的那 1 位，所以有效数字字段实际占精度减一位。bfloat16 是机器学习硬件推广开的格式，指数位与 `float` 相同，因此范围也相同，但精度只有 8 位；ISO/IEC 60559 没有给这组参数命名。

¶7 建议实现在 `<stdfloat>` 之外提供的其他名字，与 C 的 `_Float16`、`_Float32`、`_Float64`、`_Float128` 保持兼容。

使用时要注意三点：

1. 这些类型全部是可选的，代码里应先用宏检测，如 `#ifdef __STDCPP_FLOAT16_T__`。
2. 它们是扩展浮点类型，不是 `float`、`double` 的别名。即使 `std::float32_t` 与 `float` 格式完全相同，两者也是不同的类型。[[conv.rank#2]] 规定二者转换等级相同、`float32_t` 的子等级更高，所以 `float32_t` 与 `float` 混合运算的结果是 `float32_t`。
3. 不能隐式地转换为等级更低的类型。[[conv.double#1]] 只允许浮点值隐式转换为等级大于或等于源类型的浮点类型；标准浮点类型之间出于兼容，任何方向都允许。所以 `std::float16_t h = 1.0;` 是非良构的，`1.0` 是 `double`，要写 `1.0f16` 或者显式转换。

```cpp
#include <stdfloat>
#ifdef __STDCPP_FLOAT16_T__
std::float16_t a = 1.0f16;                            // OK
std::float16_t b = 1.0;                               // error: double → float16_t 等级降低
std::float16_t c = static_cast<std::float16_t>(1.0);  // OK
#endif
```

本机 Clang 23 和 libc++ 没有提供 `<stdfloat>`，这段代码没有在本机编译验证；GCC 和 libstdc++ 已经实现了这些类型。

## 历史与演进

!!! history
    - C++98：整数可以用补码、反码或原码；没有 `long long`；`wchar_t` 已经是独立的类型（在 C 里是 typedef）。
    - C++11：加入 `long long`、扩展整数类型、`char16_t`、`char32_t` 和 `std::nullptr_t`。
    - C++17：移除 `bool` 的 `++`。加入 `std::byte`，它是 `enum class byte : unsigned char {}`，不是基础类型。
    - C++20：有符号整数一律用补码（[[P0907R4]]，措辞由 [[P1236R1]] 落实），包括精确的取值范围、没有陷阱表示、有符号与无符号之间的转换取同余值、负数右移为算术移位；有符号溢出仍是 UB。加入 `char8_t`（[[P0482R6]]），`u8` 字面量的类型随之改变。
    - C++23：扩展浮点类型和 `<stdfloat>`（[[P1467R9]]），并重新定义了浮点转换等级。
    - C++26：`std::meta::info`（[[P2996R13]]）。

## 常见误解

!!! pitfall "`char` 就是 `signed char`"
    `std::is_signed_v<char>` 的结果取决于平台，但 `char` 永远是第三个独立的类型。只为 `signed char` 和 `unsigned char` 写了重载或特化，调用时传 `char` 就可能选中意料之外的转换，甚至出现歧义。

!!! pitfall "`std::uint8_t` 会按数字输出"
    `std::int8_t` 和 `std::uint8_t` 几乎总是 `signed char` 和 `unsigned char` 的别名，所以 `std::cout << std::uint8_t(65)` 打印 `A` 而不是 `65`。

!!! pitfall "补码意味着有符号溢出会回绕"
    C++20 只规定了表示和转换，没有规定算术溢出的结果，`INT_MAX + 1` 仍然是 UB。需要回绕时，先转换到无符号类型做运算，再转回来；转回来得到的是确定的同余值。

!!! pitfall "`std::float32_t` 就是 `float`"
    即使格式完全相同，二者也是不同的类型，重载决议、模板特化、`std::format` 都会区分它们。两者混合运算的结果类型是 `float32_t`。

## 思考题

!!! question "1. 一个实现能否让 `signed char` 宽 9 位、`int` 宽 18 位？`unsigned char` 呢？"

<details markdown="1">
<summary>答案</summary>

能。表 14 只给下限（`signed char` 至少 8 位，`int` 至少 16 位），其余由实现决定（¶4）。无符号类型与对应的有符号类型宽度相同（¶2），所以 `unsigned char` 也是 9 位，此时 `CHAR_BIT == 9`。¶7 要求窄字符类型的每种位模式都表示不同的值，所以这 9 位全是值位，没有填充。历史上确实有 36 位字长、9 位字节的机器。
</details>

!!! question "2. `std::nullptr_t n; void* p = n;` 读取了未初始化的变量，为什么不是 UB？换成 `int i; int j = i;` 呢？"

<details markdown="1">
<summary>答案</summary>

按 [[conv.lval#3.1]]，glvalue 的类型是 cv `std::nullptr_t` 时，左值到右值转换的结果直接是空指针常量，不访问对象，所以对象的值是否确定无关紧要（¶16 注 12：值表示可以不含任何位）。

`int i; int j = i;` 则读取了一个自动存储期变量的值。C++26 起这是**错误行为**（erroneous behavior，[[basic.indet]]）：标准认定它是错误，但结果是一个确定的、由实现选择的错误值，实现也可以诊断或终止程序。C++23 及以前它是 UB。
</details>

!!! question "3. `char` 的底层类型是 `signed char` 时，`char` 是有符号整数类型吗？`std::is_signed_v<char>` 是什么？"

<details markdown="1">
<summary>答案</summary>

不是。¶1 的有符号整数类型只有五个标准类型和扩展类型，`char` 不在其中；它是字符类型、普通字符类型和整型。但 `std::is_signed<T>` 的定义是 `T` 为算术类型且 `T(-1) < T(0)`（[[meta.unary.prop]]），所以此时 `std::is_signed_v<char>` 为 `true`。trait 的名字与标准术语并不一一对应。
</details>
