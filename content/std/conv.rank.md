---
title: 转换等级
summary: 整数转换等级的九条规则、浮点转换等级与子等级；它们如何决定整数提升、常用算术转换、浮点隐式转换与重载决议
status: draft
papers: P1467R9
related: basic.fundamental, basic.extended.fp, conv.prom, expr.arith.conv, conv.double, over.ics.rank, dcl.init.list
tags: 类型系统, 算术转换, 整数, 浮点
updated: 2026-10-17
---

`int + unsigned` 的结果是什么类型？`long long + unsigned long` 呢？`float + std::float32_t` 呢？回答这些问题需要给算术类型排一个大小顺序，但这个顺序不能直接用 `sizeof` 或宽度来定：不同类型可以同宽（LP64 上 `long` 与 `long long` 都是 64 位），浮点类型之间甚至可能无法比较（一个范围大、一个精度高）。本节（[[conv.rank]]，6.9.7）定义的就是这个顺序：**整数转换等级**（integer conversion rank）与**浮点转换等级**（floating-point conversion rank）及**子等级**（subrank）。

等级本身不直接决定任何程序行为，它是供其他规则引用的工具：

| 使用者 | 用途 |
|---|---|
| [[conv.prom]] 整数提升 | 等级低于 `int` 的整数类型提升到 `int`/`unsigned int` |
| [[expr.arith.conv]] 常用算术转换 | 两个操作数转换到等级更高者；有符号/无符号混合时的判定 |
| [[conv.double]] 浮点转换 | 只允许隐式转换到等级不低于源类型的浮点类型（标准浮点类型之间除外） |
| [[dcl.init.list#7]] 窄化 | 浮点到等级更低的浮点类型是窄化 |
| [[over.ics.rank#4.3]] 重载决议 | 等级相等的浮点类型之间的转换优于其他转换 |

本节放在第 6 章"基础"而不是第 7 章"转换"中，因为它描述的是类型的性质，而不是一种转换。

## 整数转换等级（¶1）

¶1：每个整数类型都有一个整数转换等级，由以下九条规定：

| 条款 | 规则 | 为什么 |
|---|---|---|
| ¶1.1 | 任意两个有符号整数类型等级不同，即使表示相同 | 保证有符号类型之间是全序，常用算术转换总能选出等级更高的一个 |
| ¶1.2 | 有符号整数类型的等级高于任何宽度更小的有符号整数类型 | 等级大体跟随宽度 |
| ¶1.3 | `long long int` > `long int` > `int` > `short int` > `signed char` | 标准类型之间的顺序与宽度无关地固定下来（宽度相同时也能区分） |
| ¶1.4 | 无符号整数类型的等级等于对应有符号类型的等级 | 有符号/无符号混合运算时按同级处理，再看能否表示 |
| ¶1.5 | 标准整数类型的等级高于同宽度的扩展整数类型 | 避免实现加一个扩展类型就改变已有表达式的类型 |
| ¶1.6 | `bool` 的等级低于所有其他整数类型 | |
| ¶1.7 | 字符类型（`char`、`wchar_t`、`char8_t`、`char16_t`、`char32_t`）的等级等于其底层类型的等级（[[basic.fundamental]]） | 字符类型不是有/无符号整数类型，需要借用底层类型的位置 |
| ¶1.8 | 两个同宽度的扩展有符号整数类型之间的相对等级由实现定义（但仍受其他规则约束） | |
| ¶1.9 | 等级是传递的 | 保证是一个（严格偏）序 |

Note 1：整数转换等级用于定义整数提升（[[conv.prom]]）和常用算术转换（[[expr.arith.conv]]）。

几个容易忽略的推论：

- `char` 与 `signed char`、`unsigned char` 之一同级（¶1.7），但三者仍是不同类型。`char` 与 `signed char` 同级并不违反 ¶1.1，因为 `char` 不是有符号整数类型。
- `char16_t` 与 `uint_least16_t`（通常是 `unsigned short`）同级，`char32_t` 与 `uint_least32_t`（通常是 `unsigned int`）同级，`wchar_t` 与其底层类型同级。
- 宽度相同不代表等级相同。LP64 上 `long` 与 `long long` 同为 64 位，等级却不同（¶1.3）；LLP64 上 `int` 与 `long` 同为 32 位，等级也不同。
- ¶1.2 与 ¶1.3 合起来还推出：标准有符号类型的宽度必须单调不减（否则二者矛盾），见 [[basic.fundamental]]。

## 等级如何决定算术结果的类型

[[expr.arith.conv#1.5]] 规定了整数操作数的处理方法（先做整数提升，得到 T1、T2）：

1. T1、T2 相同 → 就是它；
2. 同为有符号或同为无符号 → 取等级更高者；
3. 否则设 U 为无符号者、S 为有符号者：
    - U 的等级 ≥ S 的等级 → 结果为 U；
    - 否则，若 S 能表示 U 的全部值 → 结果为 S；
    - 否则 → 结果为 S 对应的无符号类型。

第 3 步同时用到了等级和宽度（能否表示），平台差异就来源于此：

```cpp run ok
#include <type_traits>

// 以下断言在 LP64（Linux/macOS 64 位）上成立
static_assert(sizeof(long) == 8 && sizeof(int) == 4);

static_assert(std::is_same_v<decltype(1 + 1U),   unsigned>);   // int 与 unsigned 同级 → U
static_assert(std::is_same_v<decltype(1L + 1U),  long>);       // long 等级更高且能表示所有 unsigned → S
                                                                // （LLP64 上 long 不能 → unsigned long）
static_assert(std::is_same_v<decltype(1LL + 1UL), unsigned long long>);
// ↑ 最反直觉的一个：unsigned long 等级低于 long long，而 64 位的 long long
//   不能表示 64 位 unsigned long 的全部值 → 结果为 long long 对应的无符号类型

static_assert(std::is_same_v<decltype('a' + 'b'),  int>);      // 提升：char → int
static_assert(std::is_same_v<decltype(true + true), int>);     // 提升：bool → int
static_assert(std::is_same_v<decltype(u'a' + 1),  int>);       // char16_t → int（int 能表示 uint_least16_t 的全部值）
static_assert(std::is_same_v<decltype(U'a' + 1),  unsigned>);  // char32_t → unsigned int
static_assert(std::is_same_v<decltype((unsigned short)1 + (unsigned short)1), int>);

int main() {}
```

`1LL + 1UL` 的结果是 `unsigned long long`，不是两个操作数类型中的任何一个。这完全由等级规则造成：如果 `long` 与 `long long` 同级（按宽度算），结果会是 `unsigned long`。

!!! note "为什么无符号与有符号同级（¶1.4）？"
    如果让 `unsigned int` 等级高于 `int`，那么规则 3 的第一支就会把一切 `int` + `unsigned int` 都转为无符号，这与现在的结果一样；但对于 `long` + `unsigned int` 这类宽度不同的组合，同级的规定让能否表示成为决定因素，从而在 `long` 更宽时保住有符号的结果。这延续了 C89 的值保留（value preserving）方案，与早期 Unix 编译器的无符号保留（unsigned preserving）方案相对。

## 整数提升中的等级

[[conv.prom#2]]：除 `bool`、`char8_t`、`char16_t`、`char32_t`、`wchar_t` 外，等级低于 `int` 的整数类型的 prvalue 可以提升为 `int`（若 `int` 能表示其全部值），否则提升为 `unsigned int`。被排除的那几种字符类型由 [[conv.prom#6]] 单独处理（选择第一个能表示其底层类型全部值的类型），`bool` 则由 [[conv.prom#7]] 单独提升为 `int`。

所以等级的一个作用是界定哪些是小整数类型：`signed char`、`short`、`unsigned char`、`unsigned short`、`char`。扩展整数类型若等级低于 `int`（例如一个实现提供的 24 位整数），也会被提升。

## 浮点转换等级（¶2）

C++23 之前，浮点类型只有三个，`float < double < long double` 的顺序直接写在常用算术转换里。C++23 引入扩展浮点类型（[[basic.extended.fp]]、[[P1467R9]]）后，需要一个能容纳任意多个浮点类型的一般规则。¶2 规定每个浮点类型都有一个浮点转换等级：

- ¶2.1 若某浮点类型的值集是 `T` 值集的真子集，则 `T` 的等级更高。
- ¶2.2 `long double` > `double` > `float`。
- ¶2.3 值集相同的两个扩展浮点类型等级相等。
- ¶2.4 与恰好一个 cv 无限定标准浮点类型值集相同的扩展浮点类型，等级等于该标准类型的等级。
- ¶2.5 与多个 cv 无限定标准浮点类型值集相同的扩展浮点类型，等级等于 `double` 的等级。

与整数等级的关键区别在于，**浮点等级是偏序**。Note 3：若 `T1` 的值集既不是 `T2` 的子集也不是超集，二者的等级无序；一个类型范围更大而精度更低时就会如此。`std::bfloat16_t`（8 位指数、8 位精度）与 `std::float16_t`（5 位指数、11 位精度）正是这样一对。

### 典型平台上的等级

假设 `float`/`double` 为 IEEE binary32/binary64，扩展类型都可用：

| 类型 | x86-64 Linux（`long double` 为 80 位） | Windows / Apple arm64（`long double` = `double`） |
|---|---|---|
| `std::bfloat16_t` | 低于 `float`（值集是 `float` 的真子集）；与 `float16_t` 无序 | 同左 |
| `std::float16_t` | 低于 `float` | 同左 |
| `float`、`std::float32_t` | 等级相等（¶2.4） | 同左 |
| `double`、`std::float64_t` | 等级相等（¶2.4：只与 `double` 值集相同） | `float64_t` 与 `double`、`long double` 值集都相同 → ¶2.5：等于 `double` 的等级 |
| `long double` | 高于 `double`（¶2.1 与 ¶2.2） | 仍高于 `double`（¶2.2，即使值集相同） |
| `std::float128_t` | 高于 `long double`（80 位扩展精度的值集是 binary128 的真子集） | 高于 `long double` |

Note 2 指出了一处与 C 的差异：在 `long double`、`double`、`std::float64_t` 三者值集相同的平台上，C++ 把 `float64_t` 的等级定为与 `double` 相同（¶2.5），而 C 对类似的 `_Float64` 有不同的处理（ISO/IEC 9899:2024 H.4.3）。

## 浮点转换子等级（¶3）

等级相等的浮点类型之间需要再分出先后，否则 `float + std::float32_t` 的结果类型无法确定。¶3：等级相等的浮点类型按浮点转换子等级排序，子等级在等级相同的类型间构成全序。`std::float16_t`、`std::float32_t`、`std::float64_t`、`std::float128_t` 的子等级高于任何与之等级相等的标准浮点类型；其余情况的子等级顺序由实现定义。

为什么让扩展类型优先？程序员显式使用 `std::float32_t` 时，通常希望得到格式确定的结果；混合运算的结果如果退回 `float`，就不能再从类型看出格式。（`std::bfloat16_t` 没有列在 ¶3 中，因为它的值集与任何标准浮点类型都不同，不会与之等级相等。）

Note 4：浮点转换等级和子等级用于常用算术转换（[[expr.arith.conv]]）。

## 浮点等级如何决定算术结果

[[expr.arith.conv#1.4]] 对浮点操作数的规定是：

1. 类型相同 → 不转换；
2. 一方不是浮点类型 → 转换到浮点那一方；
3. 等级有序且不等 → 转换到等级高者；
4. 等级相等 → 转换到子等级高者；
5. 否则（等级无序）→ 非良构。

```cpp
#include <stdfloat>
#include <type_traits>

// 假设 float/double 为 binary32/binary64，且下列类型均可用
static_assert(std::is_same_v<decltype(1.0f + 1.0f16), float>);            // float16_t 等级低
static_assert(std::is_same_v<decltype(1.0f + 1.0f32), std::float32_t>);   // 等级相等，float32_t 子等级高
static_assert(std::is_same_v<decltype(1.0 + 1.0f64), std::float64_t>);    // 同上
static_assert(std::is_same_v<decltype(1.0L + 1.0f64), long double>);      // long double 等级更高
auto x = 1.0bf16 + 1.0f16;   // error: bfloat16_t 与 float16_t 等级无序
```

（本机 Clang 23/libc++ 未提供 `<stdfloat>`，上例按标准推演，未经本机编译。）

对标准浮点类型，这套规则与 C++20 及之前完全一致：`float < double < long double` 由 ¶2.2 保证。

## 浮点等级与隐式转换、窄化、重载

引入扩展浮点类型的同时，标准也收紧了隐式转换（标准类型之间为保持兼容而不变）：

- [[conv.double#1]]：浮点 prvalue 可以隐式转换为等级大于或等于源类型的浮点类型；标准浮点类型之间则可以任意方向转换。所以 `double d; float f = d;` 仍然合法，但 `double d; std::float32_t g = d;` 非良构。
- [[dcl.init.list#7.2]]：从浮点类型 `T` 转换到等级既不大于也不等于 `T` 的浮点类型是窄化（常量表达式且有限不溢出等情况除外）。因此等级无序也算窄化。
- [[over.ics.rank#4.3]]：`FP1` 与等级相等的 `FP2` 之间的转换，优于 `FP1` 与其他算术类型之间的转换。标准中的例子：

```cpp
int f(std::float32_t);
int f(std::float64_t);
int f(long long);
float x;
std::float16_t y;
int i = f(x);   // 选 f(std::float32_t)：float 与 float32_t 等级相等（在二者格式相同的实现上）
int j = f(y);   // error: 二义——没有与 float16_t 等级相等的候选
```

没有 ¶4.3 时，`float → std::float32_t`、`float → std::float64_t`、`float → long long` 都只是 Conversion 等级（[[over.ics.scs]]），三者无法区分，`f(x)` 将是二义的；¶4.3 让等级相等的浮点类型之间的转换胜出。`y` 的情形下没有与 `float16_t` 等级相等的候选，决胜规则不适用，仍然二义。

## 实现视角

!!! impl
    - 整数等级在实现中通常被编码为一个小整数（Clang 的 `ASTContext::getIntegerRank`），`char`/`signed char`/`unsigned char` 共享一个值，`long` 与 `long long` 即使同宽也取不同的值。
    - `__int128` 在 GCC/Clang 中被赋予高于 `long long` 的等级，因此 `__int128 + unsigned long long` 的结果是 `__int128`（能表示全部 64 位无符号值）。
    - Clang 的 `_Float16`/`__bf16` 并未按 C++23 的扩展浮点类型实现（本机 libc++ 中 `std::is_floating_point_v<_Float16>` 为 `false`），因此它们的混合运算规则是 Clang 自己的扩展规则，不能用来验证本节。

## 历史与演进

!!! history
    - **C++98**：C++ 中还没有整数转换等级的概念，常用算术转换直接逐一列举类型（"若一方为 `long double`……否则若一方为 `double`……否则若一方为 `unsigned long`……"）。
    - **C++11**：随 `long long` 与扩展整数类型的加入，从 C99 引入整数转换等级（C99 6.3.1.1），常用算术转换改用等级描述。
    - **C++20**：整数提升与常用算术转换的措辞随补码化调整，但等级规则本身不变。
    - **C++23**：[[P1467R9]] 引入浮点转换等级与子等级，替代 `float < double < long double` 的硬编码；常用算术转换增加"等级无序则非良构"；`conv.double`、窄化、重载决议同步修改。

## 陷阱

!!! pitfall "按宽度推测结果类型"
    认为"两个 64 位类型相加，结果是其中之一"是错的：`long long + unsigned long` 在 LP64 上得 `unsigned long long`，两个操作数都不是这个类型。依赖结果类型的代码（模板分派、`auto` 变量、`printf` 格式符）应该用 `std::common_type_t` 或显式转换，而不是心算。

!!! pitfall "`long + unsigned` 跨平台不同"
    在 LP64 上结果为 `long`，在 LLP64（Windows）上为 `unsigned long`。后者会使 `-1L < 1U` 为假（`-1L` 被转换为 `unsigned long` 的最大值）。这类比较在 GCC/Clang 中有 `-Wsign-compare` 警告，C++20 起可用 `std::cmp_less` 等安全比较函数（[[utility.intcmp]]）。

!!! pitfall "`float32_t` 不能从 `double` 隐式初始化"
    `std::float32_t x = 0.1;` 非良构，要写 `0.1f32`，这与 `float x = 0.1;` 不同。迁移代码时，这是最常见的编译错误。

## 思考题

!!! question "1. 某实现提供 64 位扩展有符号整数类型 `__ext64`，且 `long long` 也是 64 位。`__ext64 + unsigned long long` 的类型是什么？"

<details markdown="1">
<summary>答案</summary>

¶1.5：标准整数类型的等级高于同宽度的扩展整数类型，所以 `long long` > `__ext64`；¶1.4：`unsigned long long` 与 `long long` 同级，因此 `unsigned long long` 的等级 > `__ext64` 的等级。按 [[expr.arith.conv#1.5.3.1]]，U 的等级 ≥ S 的等级 → 结果为 `unsigned long long`。
</details>

!!! question "2. 为什么 ¶2.5 在 `float64_t` 与 `double`、`long double` 值集都相同时选择 `double` 的等级，而不是 `long double` 的？"

<details markdown="1">
<summary>答案</summary>

标准没有在注中给出理由。一个合理的解释是让 `float64_t` 的行为尽量不随平台改变：在 x86-64 Linux 上（`long double` 更宽），`float64_t` 按 ¶2.4 与 `double` 同级；在 Windows 上若选 `long double` 的等级，`float64_t + long double` 的结果就会变成 `float64_t`（子等级更高），而在 Linux 上是 `long double`。选 `double` 使两个平台上 `float64_t` 都与 `double` 同级、低于 `long double`，`float64_t` 与 `double` 的混合运算结果都是 `float64_t`。
</details>

!!! question "3. `char` 与 `signed char` 同级，那么 `char + signed char` 的类型是什么？"

<details markdown="1">
<summary>答案</summary>

`int`。两个操作数都先经过整数提升（等级低于 `int`，且 `int` 能表示它们的全部值），提升后 T1 = T2 = `int`，[[expr.arith.conv#1.5.1]] 直接得出 `int`。这里根本用不到等级是否相同，等级规则主要在 `int` 及以上的类型之间起作用。
</details>

## 小结

!!! summary
    - [[g:integer-conversion-rank|整数转换等级]]：有符号类型两两不同级；`long long > long > int > short > signed char`；无符号与对应有符号同级；字符类型与底层类型同级；`bool` 最低；同宽时标准类型高于扩展类型；传递。
    - 等级 ≠ 宽度：LP64 上 `long` 与 `long long` 同宽不同级，导致 `long long + unsigned long` → `unsigned long long`。
    - [[g:floating-point-conversion-rank|浮点转换等级]]（C++23）：值集真包含决定高低；`long double > double > float`；值集相同的扩展类型与对应标准类型同级（多个时取 `double`）；可能无序。
    - [[g:floating-point-conversion-subrank|子等级]]：等级相同时，`std::floatN_t` 高于标准类型，所以混合运算得到 `floatN_t`。
    - 用途：整数提升、常用算术转换（无序 → 非良构）、浮点隐式转换只能向更高或相等的等级进行、窄化判定、重载决胜。
