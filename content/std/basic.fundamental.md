---
title: 基础类型
summary: 有符号/无符号整数类型（宽度、补码、最小宽度）、字符类型、bool、浮点类型与可选扩展浮点类型、void、nullptr_t、std::meta::info
status: draft
covers: basic.fundamental, basic.extended.fp
papers: P0907R4, P1236R1, P0482R6, P1467R9, P2996R13
related: basic.types, conv.rank, conv.prom, expr.arith.conv, conv.integral, basic.types.trivial, numeric.limits
tags: 类型系统, 整数, 浮点
updated: 2026-10-17
---

**基础类型**（fundamental types，¶19）是语言内建、不由其他类型构造而来的类型：整数、字符、`bool`、浮点、`void`、`std::nullptr_t`，以及 C++26 新增的 `std::meta::info`。本节（[[basic.fundamental]]，6.9.3）规定它们的取值范围、表示和相互关系；随后的 [[basic.extended.fp]]（6.9.4）规定 C++23 起可选提供的 `std::float16_t` 等扩展浮点类型，本页一并注释。

读本节要抓住一条主线：**C++20 之后，整数类型的表示几乎完全确定了**，即补码、没有陷阱表示、无符号与有符号的对应位一致；但宽度（width）仍由实现定义，标准只给出下限。浮点类型则相反，标准几乎什么都不规定（不强制 IEEE 754），只规定了包含关系。

相关条款有转换等级 [[conv.rank]]、整数提升 [[conv.prom]]、常用算术转换 [[expr.arith.conv]]、整数转换 [[conv.integral]]、`<limits>`（[[numeric.limits]]）。

## 有符号整数类型（¶1）

¶1 规定有五种**标准有符号整数类型**（standard signed integer types）：`signed char`、`short int`、`int`、`long int`、`long long int`。列表中每个类型提供的存储至少与前面的一样多。实现还可以提供实现定义的**扩展有符号整数类型**（extended signed integer types）。两者合称有符号整数类型。

!!! std
    "The range of representable values for a signed integer type is −2^(N−1) to 2^(N−1)−1 (inclusive), where N is called the *width* of the type."

这一句是 C++20 规定有符号整数采用补码的核心：范围精确地规定为补码范围（`int` 宽 32 时是 −2147483648..2147483647），不再允许反码、原码那种对称范围和负零。

!!! lawyer "宽度也是单调的吗？"
    ¶1 只说存储（即 `sizeof`）不减，没有直接说宽度不减。但 [[conv.rank#1.2]] 规定宽度更小的有符号类型等级更低，[[conv.rank#1.3]] 又规定了 `long long > long > int > short > signed char` 的等级顺序。如果某实现让 `int` 比 `long` 宽，由前者可推出 `int` 的等级高于 `long`，与后者矛盾。所以宽度单调是两条规则合起来的推论。

## 无符号整数类型与模算术（¶2）

¶2 规定，每种标准有符号整数类型都有一个对应（但不同）的**标准无符号整数类型**：`unsigned char`、`unsigned short int`、`unsigned int`、`unsigned long int`、`unsigned long long int`；每种扩展有符号整数类型也有对应的扩展无符号整数类型。无符号类型与对应有符号类型的宽度 N 相同，范围是 0 到 2^N−1，**算术按模 2^N 进行**。

Note 1 点出了 C++ 整数运算最重要的不对称：**无符号运算不会溢出**（结果总是取模），**有符号运算溢出是未定义行为**（[[expr.pre]]）。改为补码并没有改变这一点。C++20 保留了有符号溢出的 UB，因为编译器依赖它做循环优化（例如假设 `i + 1 > i`）。

```cpp run ub
#include <climits>

int main() {
  unsigned u = UINT_MAX;
  u = u + 1;            // OK: 模 2^N，结果为 0
  int i = INT_MAX;
  i = i + 1;            // UB: 有符号溢出（UBSan: signed integer overflow）
  return u + i;
}
```

## 有符号与无符号共享表示（¶3）

¶3 规定，无符号整数类型与对应的有符号类型具有相同的对象表示、值表示和对齐要求。对有符号类型的每个值 `x`，对应无符号类型中与 `x` 模 2^N 同余的那个值，在值表示中的对应位相同（脚注：这就是补码）。例如有符号的 `-1` 与对应无符号类型的最大值表示相同。

有了这条规则，[[basic.lval#11]] 允许通过 `unsigned int` glvalue 访问 `int` 对象就有了确切含义：读到的就是同余值。再配合 [[conv.integral#3]]（C++20 起整数转换的结果是模 2^N 同余的唯一值），有符号与无符号之间的转换不再有实现定义的成分：

```cpp run ok
#include <cassert>

int main() {
  int x = -1;
  unsigned u = x;                       // 4294967295（若 unsigned 宽 32）
  assert(u == ~0u);
  assert(static_cast<int>(u) == -1);    // C++20 起：同余值，不再是实现定义
  assert((-8 >> 1) == -4);              // C++20 起：负数右移是算术移位 [expr.shift]
}
```

## 最小宽度与填充位（¶4）

表 14 是最小宽度（[tab:basic.fundamental.width]），下面同时列出常见数据模型下的实际宽度：

| 类型 | 最小宽度 N | ILP32（32 位 Linux/Windows） | LP64（64 位 Linux/macOS） | LLP64（64 位 Windows） |
|---|---|---|---|---|
| `signed char` | 8 | 8 | 8 | 8 |
| `short int` | 16 | 16 | 16 | 16 |
| `int` | 16 | 32 | 32 | 32 |
| `long int` | 32 | 32 | **64** | **32** |
| `long long int` | 64 | 64 | 64 | 64 |
| 指针 | — | 32 | 64 | 64 |

¶4 的其余内容：

- 标准有符号整数类型的宽度不得小于表中的值；
- 有符号或无符号整数类型的**值表示恰好由 N 位构成**；
- 如果对象表示中还有填充位（[[basic.types.general#2]]），填充位的每一种取值都只是同一个值的替代表示。Note 2 明确指出，填充位的值未指定，但不会造成陷阱（这一点与 C 不同，C 允许陷阱表示）；
- 除此之外，整数类型的宽度由实现定义。

注意表中 `int` 的最小宽度是 16，不是 32，在 16 位平台上 `int` 仍然可以只有 16 位。可移植代码需要确定宽度时，应使用 `<cstdint>` 的 `std::int32_t` 等类型（[[cstdint.syn]]）。`long` 在 LP64 与 LLP64 之间的差异是跨平台代码中最常见的问题。

## base-2 表示、标准/扩展整数类型（¶5）

¶5 先为无符号值定义唯一的 **base-2 表示** x = Σ xᵢ·2ⁱ（每个 xᵢ ∈ {0,1}），再规定有符号值的 base-2 表示就是对应无符号类型中同余值的 base-2 表示。这就是补码的形式化定义。`<bit>` 中的 `std::popcount`、`std::countl_zero` 等函数都依据这个表示来描述（它们只接受无符号类型）。

术语上，标准有符号整数类型和标准无符号整数类型合称**标准整数类型**；扩展有符号和扩展无符号整数类型合称**扩展整数类型**。

!!! impl "`__int128` 是扩展整数类型吗？"
    GCC 与 Clang 在 64 位目标上提供 `__int128`/`unsigned __int128`，但通常不宣称它是标准意义上的扩展整数类型。一个重要原因是，C 把 `intmax_t` 定义为能表示任何有符号整数类型的值，一旦承认 128 位扩展整数类型，`intmax_t` 就必须变成 128 位，这会改变已有的 ABI。不过各个库的 trait 结果并不统一：本机 libc++ 的 `std::is_integral_v<__int128>` 为 `true`；libstdc++ 的结果取决于是否启用 GNU 扩展模式。Clang 的 `_BitInt(N)` 在 C++ 中同样只是扩展，不是标准整数类型。

## 底层类型（¶6）

¶6 规定：如果一个基础类型被规定以某个有符号或无符号整数类型为**底层类型**（underlying type），则两者具有相同的对象表示、值表示、对齐要求和取值范围，且每个值在两个类型中的表示相同。

后面的 `char`、`wchar_t`、`char8_t`、`char16_t`、`char32_t` 都遵循这一模式：它们是不同的类型，但在表示上与某个整数类型完全一样。这里的底层类型与枚举的底层类型（[[dcl.enum]]）是同一个词，也是同一种思想。

## 字符类型（¶7–¶9）

### `char` 与三个普通字符类型（¶7）

¶7 规定，`char` 是一个不同的类型，其底层类型由实现定义为 `signed char` 或 `unsigned char` 之一。`char`、`signed char`、`unsigned char` 合称**普通字符类型**（ordinary character types）；普通字符类型加上 `char8_t` 合称**窄字符类型**（narrow character types）。对窄字符类型，对象表示的每一种比特模式都表示一个不同的值。也就是说，它们没有填充位，也没有无效值，可以安全地承载任意字节。Note 5 补充：宽度超过类型宽度的窄字符类型位域会有填充位。

`char` 是独立的第三个类型，既不是 `signed char`，也不是 `unsigned char`，重载决议与模板特化都区分这三者：

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
  f('a');                       // char
  f(static_cast<signed char>(1));
  f(static_cast<unsigned char>(1));
  std::printf("char is %s\n", CHAR_MIN < 0 ? "signed" : "unsigned");
}
```

!!! impl "`char` 的符号性"
    在 x86/x86-64 的主流 ABI 中 `char` 有符号；在 ARM（AArch32/AArch64 的 AAPCS）、PowerPC、RISC-V 的 Linux ABI 中 `char` 无符号。Apple arm64 是例外，`char` 有符号（本机 `CHAR_MIN` 为 −128）。GCC/Clang 可用 `-funsigned-char`/`-fsigned-char` 改变这一点（会改变 ABI 语义，需要全程序一致），MSVC 用 `/J`。依赖 `char` 符号性的代码（如用 `c < 0` 判断非 ASCII 字节）不可移植。

### `wchar_t`（¶8）

¶8 规定，`wchar_t` 是一个不同的类型，底层类型是实现定义的某个有符号或无符号整数类型。Windows 上它是 16 位无符号类型（存放 UTF-16 码元）；Linux 与 macOS 上通常是 32 位有符号 `int`（本机 `__WCHAR_TYPE__` 为 `int`）。

### `char8_t`、`char16_t`、`char32_t`（¶9）

¶9 规定，`char8_t` 的底层类型是 `unsigned char`；`char16_t`、`char32_t` 的底层类型分别是 `std::uint_least16_t`、`std::uint_least32_t`（[[cstdint.syn]]）。

`char8_t` 是 C++20 加入的（[[P0482R6]]），它让 `u8` 字面量有了专属类型。这是一个**破坏性变更**：C++17 中 `u8"x"` 的类型是 `const char[2]`，C++20 起是 `const char8_t[2]`。

```cpp run error
const char*    a = u8"x";   // error（C++20 起）：const char8_t[2] 不能转为 const char*
const char8_t* b = u8"x";   // OK
```

注意 `char8_t` 是窄字符类型，但不是普通字符类型：[[basic.lval#11]] 允许别名访问的是 `char`、`unsigned char`、`std::byte`，不包括 `char8_t`。这也是引入它的另一个动机：`char8_t*` 不会与任何其他类型别名，编译器可以更积极地优化。

## `bool`（¶10）

¶10 规定，`bool` 是一个不同的类型，与某个实现定义的无符号整数类型具有相同的对象表示、值表示和对齐要求。`bool` 的值是 `true` 和 `false`。Note 6 说明，没有 `signed bool`、`unsigned bool`、`short bool`、`long bool`。

这句话的微妙之处在于：值表示与（比如）`unsigned char` 相同，有 8 位，但值只有两个。8 位能组成 256 种值表示，其中只有两种对应 `bool` 的值，其余对应空集（按 [[basic.types.trivial#1]] 的模型）。所以用 `memcpy` 把字节 `0x02` 放进 `bool` 会导致 UB（见 [[basic.types.trivial]] 的例子）。`sizeof(bool)` 由实现定义，主流平台上为 1。

`bool` 是整型（¶11），参与整数提升（[[conv.prom]]：提升为 `int`），但等级低于所有其他整数类型（[[conv.rank#1.6]]）。C++17 移除了 `bool` 的 `++`（此前已弃用），`--` 则从来不允许。

## 整型（¶11）

¶11 规定，`char`、`wchar_t`、`char8_t`、`char16_t`、`char32_t` 合称**字符类型**（character types）。字符类型、`bool`、有符号与无符号整数类型以及它们的 cv 版本，合称**整型**（integral types），同义词是**整数类型**（integer type）。Note 7 指出，枚举不是整型，但无作用域枚举可以提升为整型（[[conv.prom]]）。

要注意这些术语的层次：

| 术语 | 包含 |
|---|---|
| 有符号整数类型 | `signed char` `short` `int` `long` `long long` + 扩展 |
| 无符号整数类型 | `unsigned char` … `unsigned long long` + 扩展 |
| 标准整数类型 | 上面两行中的标准者（**不含** `char`、`bool`、`wchar_t` 等） |
| 字符类型 | `char` `wchar_t` `char8_t` `char16_t` `char32_t` |
| 普通字符类型 | `char` `signed char` `unsigned char` |
| 窄字符类型 | 普通字符类型 + `char8_t` |
| 整型 = 整数类型 | 字符类型 + `bool` + 有/无符号整数类型（含 cv） |

于是 `signed char` 既是有符号整数类型，又是普通字符类型，却不是字符类型；`char` 是字符类型和普通字符类型，却既不是有符号整数类型，也不是无符号整数类型，哪怕它的底层类型是 `signed char`。这个区分在 [[expr.arith.conv]] 与 [[conv.prom]] 中有实际后果。

## 浮点类型（¶12–¶13）

¶12 规定，`float`、`double`、`long double` 是三个不同的类型。`double` 的精度至少与 `float` 相同，`long double` 至少与 `double` 相同；`float` 的值集是 `double` 值集的子集，`double` 的值集是 `long double` 值集的子集。这三者及其 cv 版本合称**标准浮点类型**。实现还可以提供额外的表示浮点值的类型，并把它们（及 cv 版本）定义为**扩展浮点类型**（extended floating-point types）。标准与扩展浮点类型合称**浮点类型**。

Note 8 很重要：实现提供了、但没有由实现定义为扩展浮点类型的那些浮点类型，**不算浮点类型**，标准对它们以及它们与浮点类型的交互不作任何要求。本机 Clang 23 的 `_Float16` 就属于这种情况：它能做算术，但 libc++ 的 `std::is_floating_point_v<_Float16>` 为 `false`，Clang 也没有提供 `<stdfloat>`。

除 [[basic.extended.fp]] 规定的以外，浮点类型的对象表示、值表示和运算精度都是实现定义的。C++ 不强制 IEEE 754（ISO/IEC 60559），可以用 `std::numeric_limits<T>::is_iec559` 查询。

!!! impl "`long double` 的三种实现"
    - x86-64 Linux（System V）：x87 80 位扩展精度，`sizeof` 为 16（48 位填充）。
    - Windows（MSVC）与 Apple arm64：与 `double` 相同，64 位（本机 `__SIZEOF_LONG_DOUBLE__` 为 8）。
    - AArch64 Linux、部分 PowerPC：128 位四精度（binary128，软件实现）或 double-double。

    所以 `long double` 是最不可移植的算术类型；需要四精度时应使用 `std::float128_t`（若可用）。

¶13 规定，浮点类型的**可表示值范围**至少是从最小的有限负数到最大的有限正数；如果该类型能表示负无穷，范围扩展到所有负实数，正无穷同理。Note 9 指出，遵循 ISO/IEC 60559 的类型能表示两种无穷，因此所有实数都在其可表示范围内（无穷和 NaN 本身不是实数）。

这条规则的实际后果体现在转换和运算的 UB 判定上。[[conv.double#2]] 说："若源值不在目标类型的可表示范围内，行为未定义"。有了 ¶13，对 IEEE 类型而言，把 `double` 的 `1e300` 转为 `float` 是在范围内的（介于 `FLT_MAX` 与 `+∞` 这两个相邻值之间），结果是二者之一（实现定义），**不是 UB**。没有无穷的浮点格式则仍可能出现 UB。

## 算术类型（¶14）

¶14 规定，整型和浮点类型合称**算术类型**（arithmetic types）。Note 10 指向可查询其属性的头文件 `<limits>`、`<climits>`、`<cfloat>`。

## `void`（¶15）

¶15 规定，cv `void` 是**无法完成的不完整类型**，其值集为空。所以不存在 `void` 对象、`void` 数组、`void&`，但存在 `void*`（[[basic.compound]]）。

Note 11 列出了 `void` 类型的表达式可以出现的地方：表达式语句、返回类型为 cv `void` 的函数中 `return` 的操作数、逗号表达式的操作数、括号表达式、*requires-expression* 中的要求、`?:` 的第二/三操作数、`typeid`、`noexcept`、`decltype` 的操作数，以及显式转换到 cv `void` 的操作数。

```cpp run ok
void v() {}
void w() { return v(); }           // OK: return 一个 void 表达式（对泛型代码很有用）

template<class F> auto call(F f) { return f(); }   // F 返回 void 时也能工作

int main() {
  (void)0;                         // 显式转换为 void
  static_cast<void>(42);
  (v(), 1);                        // 逗号表达式
  true ? v() : w();                // ?: 的两支都是 void
  decltype(v())* p = nullptr;      // decltype(v()) 是 void
  (void)p;
  call(v);
}
```

C++ 允许把返回 `void` 的调用作为 `return` 的操作数，这是有意为之：`template<class F> auto call(F f) { return f(); }` 这类转发包装因此不必为 `void` 特化。社区曾有 regular void 的提案（让 `void` 成为普通对象类型），但没有被采纳。

## `std::nullptr_t`（¶16）

¶16 规定，cv `std::nullptr_t` 表示一个不同的类型。`std::nullptr_t` 类型的 prvalue 是**空指针常量**（[[conv.ptr]]），参与指针与成员指针转换。`std::nullptr_t` 的大小和对齐要求与 `void*` 相同。Note 12 指出，因为只有一个值，它的值表示可以不含任何位。

于是 [[conv.lval#3.1]] 规定，对 `nullptr_t` glvalue 做左值到右值转换，结果直接是空指针常量，**并不访问内存**。下面这段代码读取了一个未初始化的 `nullptr_t` 变量，却完全合法：

```cpp run ok
#include <cstddef>
#include <cstdio>

void f(int)   { std::puts("int"); }
void f(char*) { std::puts("char*"); }

static_assert(sizeof(std::nullptr_t) == sizeof(void*));

int main() {
  f(nullptr);              // char*：nullptr 不能转换为 int
  // f(NULL);              // 可能调用 f(int) 或有歧义，取决于 NULL 的定义
  std::nullptr_t n;        // 未初始化
  char* p = n;             // OK：左值到右值转换不访问 n 的存储
  f(p);
}
```

`nullptr_t` 是标量类型，也是基础类型，但不是指针类型（`std::is_pointer_v<std::nullptr_t>` 为 `false`），它有自己的主类别 `is_null_pointer`。

## `std::meta::info` 与反射 {{c++26}}（¶17–¶18）

¶17 规定，`std::meta::info` 类型的值叫**反射**（reflection）。存在唯一的**空反射**（null reflection）；其余每个反射都表示（represent）以下构造之一：标量类型的值、静态存储期对象、变量、结构化绑定、函数、函数形参、枚举项、注解、类型别名、类型、类成员、无名位域、类模板、函数模板、变量模板、别名模板、概念、命名空间别名、命名空间、直接基类关系、数据成员描述（共 21 项，¶17.1–¶17.21）。

¶18 是推荐实践：实现不应把本标准规定的其他构造，即 *using-declarator*、偏特化、属性、占位类型、语句、表达式，表示为 `std::meta::info` 的值；Note 14 说明未来版本可能会规定它们。这是为未来演进保留空间：如果实现现在就自行支持反射一个表达式，将来标准化时就可能出现语义冲突。

`std::meta::info` 是一个基础类型（¶19 统称本节描述的类型），又是标量类型（[[basic.types.general#7]]），因此可以作为非类型模板形参的类型。它有自己的主类别 trait `std::is_reflection`（[[meta.unary.cat]]）。这些都是静态反射（[[P2996R13]]）带来的，C++23 及之前不存在。

```cpp
#include <meta>

struct S { int mem; };
constexpr std::meta::info r1 = ^^S;         // 表示一个类型
constexpr std::meta::info r2 = ^^S::mem;    // 表示一个类成员
constexpr std::meta::info r0{};             // 空反射
static_assert(r1 != r2 && r0 == std::meta::info{});
```

（本机 Clang 23 尚未实现静态反射，上例未经编译验证。）

## 基础类型的总称（¶19）

¶19 规定，本节描述的类型统称**基础类型**。Note 15 指出，即使实现让两个或更多基础类型具有相同的值表示，它们仍然是**不同的类型**。典型的例子是 LLP64：`int` 与 `long` 都是 32 位补码，但 `int*` 不能隐式转为 `long*`，`f(int)` 与 `f(long)` 是两个重载，`int` 与 `long` 也不布局兼容（[[basic.types.general#9]]）。

```cpp run error
void g(long*);
int main() {
  int i = 0;
  g(&i);       // error: int* 不能转换为 long*，即使二者表示相同
}
```

## 可选扩展浮点类型（[[basic.extended.fp]]）{{c++23}}

C++23（[[P1467R9]]）为常见的浮点格式规定了标准名称。如果实现支持具有相应性质的扩展浮点类型，就要在 `<stdfloat>` 中声明对应的类型别名，定义对应的宏（[[cpp.predefined]]），并支持对应的字面量后缀（[[lex.fcon]]）。

| 别名（`<stdfloat>`） | ISO/IEC 60559 格式 | 宽度 k | 精度 p | emax | 指数位 w | 宏 | 后缀 |
|---|---|---|---|---|---|---|---|
| `std::float16_t`（¶1） | binary16 | 16 | 11 | 15 | 5 | `__STDCPP_FLOAT16_T__` | `f16` `F16` |
| `std::float32_t`（¶2） | binary32 | 32 | 24 | 127 | 8 | `__STDCPP_FLOAT32_T__` | `f32` `F32` |
| `std::float64_t`（¶3） | binary64 | 64 | 53 | 1023 | 11 | `__STDCPP_FLOAT64_T__` | `f64` `F64` |
| `std::float128_t`（¶4） | binary128 | 128 | 113 | 16383 | 15 | `__STDCPP_FLOAT128_T__` | `f128` `F128` |
| `std::bfloat16_t`（¶5） | （无名称） | 16 | 8 | 127 | 8 | `__STDCPP_BFLOAT16_T__` | `bf16` `BF16` |

¶6 是一个注：精度 p 包括有效数字开头隐含的 1 位，所以有效数字字段实际占 p−1 位。ISO/IEC 60559 没有为 bfloat16 的参数组合命名。它是由机器学习硬件（起源于 Google TPU）推广开的格式，与 `float` 有相同的 8 位指数（因此范围相同），但只有 8 位精度。

¶7 是推荐实践：如果实现在 `<stdfloat>` 之外为这些类型提供其他名字，应与 C 的 `_Float16`、`_Float32`、`_Float64`、`_Float128` 兼容。

几个关键细节：

1. 全部可选。代码中应当用宏检测，如 `#ifdef __STDCPP_FLOAT16_T__`。
2. 它们是扩展浮点类型，**不是 `float`/`double` 的别名**。即使 `std::float32_t` 与 `float` 的格式完全相同，它们也是不同的类型（`std::is_same_v<std::float32_t, float>` 为 `false`）。转换等级规则（[[conv.rank#2]]）规定二者等级相同、`float32_t` 的子等级更高，所以 `float32_t + float` 的结果是 `float32_t`。
3. 隐式窄化受到限制。[[conv.double#1]] 只允许把浮点值隐式转换为转换等级大于或等于源类型的浮点类型；在标准浮点类型之间，出于历史兼容，任何方向都允许。所以 `std::float16_t h = 1.0;`（`double` → `float16_t`）是**非良构**的，需要写 `1.0f16` 或显式转换。

```cpp
#include <stdfloat>
#ifdef __STDCPP_FLOAT16_T__
std::float16_t a = 1.0f16;                            // OK
std::float16_t b = 1.0;                               // error: double → float16_t 降低等级，不能隐式转换
std::float16_t c = static_cast<std::float16_t>(1.0);  // OK
#endif
```

（本机 Clang 23/libc++ 未提供 `<stdfloat>`，上例未经本机编译验证；GCC/libstdc++ 已实现这些类型。）

## 历史与演进

!!! history
    - **C++98**：整数可以是补码、反码或原码；`long long` 不存在；`wchar_t` 已是独立类型（C 中是 typedef）。
    - **C++11**：加入 `long long`、扩展整数类型、`char16_t`/`char32_t`、`std::nullptr_t`。
    - **C++17**：移除 `bool` 的 `++`。加入 `std::byte`，但它是 `enum class byte : unsigned char {}`，不是基础类型。
    - **C++20**：有符号整数一律采用补码（[[P0907R4]]，措辞由 [[P1236R1]] 落实），包括范围精确规定、无陷阱表示、有符号与无符号之间的转换取同余值、负数右移为算术右移；但有符号溢出仍是 UB。加入 `char8_t`（[[P0482R6]]），`u8` 字面量的类型随之改变。
    - **C++23**：扩展浮点类型与 `<stdfloat>`（[[P1467R9]]），并重新定义浮点转换等级（[[conv.rank#2]]）。
    - **C++26**：`std::meta::info`（[[P2996R13]]）{{c++26}}。

## 陷阱

!!! pitfall "`char` 不是 `signed char`"
    `std::is_signed_v<char>` 的结果取决于平台，但 `char` 永远是独立的第三个类型。如果为 `signed char` 和 `unsigned char` 写了重载或特化，却没有为 `char` 写，调用时就可能意外地选中其他转换，甚至产生二义。

!!! pitfall "`int8_t` 是字符类型"
    `std::int8_t`/`std::uint8_t` 几乎总是 `signed char`/`unsigned char` 的别名，所以 `std::cout << std::uint8_t(65)` 打印 `A` 而不是 `65`。

!!! pitfall "补码不等于有符号溢出回绕"
    C++20 只规定了表示与转换，没有规定算术溢出的结果。`INT_MAX + 1` 仍然是 UB。需要回绕时，先转换到无符号类型运算，再转回来（转回得到的是良定义的同余值）。

!!! pitfall "`float32_t` 不是 `float`"
    即使格式完全相同，二者也是不同的类型：重载决议、模板特化、`std::format` 等都会区分它们；`float32_t` 与 `float` 混合运算的结果类型是 `float32_t`。

## 思考题

!!! question "1. 一个实现能否让 `char` 宽 9 位、`int` 宽 18 位？`unsigned char` 呢？"

<details markdown="1">
<summary>答案</summary>

能。表 14 只给下限（`signed char` ≥ 8，`int` ≥ 16），宽度由实现定义（¶4）；无符号类型的宽度与对应有符号类型相同（¶2），所以 `unsigned char` 也是 9 位，此时 `CHAR_BIT == 9`。¶7 要求窄字符类型的每个比特模式都表示一个不同的值，所以 9 位全部是值位，没有填充。历史上确实有 36 位字长、9 位字节的机器。
</details>

!!! question "2. `std::nullptr_t n; void* p = n;` 读了未初始化的变量，为什么不是 UB？换成 `int i; int j = i;` 呢？"

<details markdown="1">
<summary>答案</summary>

按 [[conv.lval#3.1]]，当 glvalue 的类型是 cv `std::nullptr_t` 时，左值到右值转换的结果直接是空指针常量，不访问所引用的对象，所以对象的值是否不确定无关紧要（¶16 Note 12：值表示可以不含任何位）。`int i; int j = i;` 则读取了一个自动存储期变量的值：C++26 起这是**错误行为**（erroneous behavior，[[basic.indet]]），结果是一个实现定义的错误值；C++23 及之前是 UB。
</details>

!!! question "3. `char` 的底层类型是 `signed char` 时，`char` 是有符号整数类型吗？`std::is_signed_v<char>` 又是什么？"

<details markdown="1">
<summary>答案</summary>

不是。¶1 列举的有符号整数类型只有五个标准类型加上扩展类型，`char` 不在其中；它是字符类型、普通字符类型和整型。但 `std::is_signed<T>` 的定义是"`T` 是算术类型且 `T(-1) < T(0)`"（[[meta.unary.prop]]），所以此时 `std::is_signed_v<char>` 为 `true`。trait 的名字与标准术语并不完全对应，这是一个经典的术语陷阱。
</details>

## 小结

!!! summary
    - 整数：5 个标准有符号类型 + 对应的无符号类型 + 可选的扩展类型；宽度由实现定义，但有下限（8/16/16/32/64）；采用补码，值表示恰好 N 位，填充位不造成陷阱；无符号算术取模，有符号溢出是 UB。
    - 字符：`char`（底层类型为 `signed char` 或 `unsigned char`，但它是第三个类型）、`wchar_t`（实现定义）、`char8_t`（`unsigned char`）、`char16_t`/`char32_t`（`uint_least16/32_t`）；[[g:narrow-character-type|窄字符类型]]的每个比特模式都是不同的值。
    - `bool`：表示与某个无符号整数类型相同，值只有 `true`/`false`；其余比特模式不对应任何值。
    - [[g:floating-point-type|浮点]]：值集满足 `float ⊆ double ⊆ long double`，表示与精度由实现定义；有无穷时可表示范围覆盖全体实数；C++23 起可选的 `std::float16_t`/`float32_t`/`float64_t`/`float128_t`/`bfloat16_t` 是不同于标准浮点类型的[[g:extended-floating-point-type|扩展浮点类型]]。
    - `void`：无法完成的不完整类型；`nullptr_t`：与 `void*` 同大小，值表示可以为空，读取时不访问内存；`std::meta::info`：C++26 的反射值类型，属于标量。
