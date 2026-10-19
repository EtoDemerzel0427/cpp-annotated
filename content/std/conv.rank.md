---
title: 转换等级
summary: 整数转换等级、浮点转换等级与子等级：给算术类型排出先后，供整数提升、常用算术转换、浮点隐式转换、窄化判定和重载决议使用。
status: done
papers: P1467R9
related: basic.fundamental, basic.extended.fp, conv.prom, expr.arith.conv, conv.double, over.ics.rank, dcl.init.list
tags: 类型系统, 算术转换, 整数, 浮点
updated: 2026-10-19
---

!!! tldr
    - 等级本身不产生任何行为。它是给其他规则用的排序：整数提升、常用算术转换、浮点隐式转换、窄化和重载决议都按等级判断。
    - [[g:integer-conversion-rank|整数转换等级]]不等于宽度。`long` 和 `long long` 在 LP64 上同为 64 位，但 `long long` 等级更高，于是 `1LL + 1UL` 的类型是 `unsigned long long`。
    - 无符号类型与对应的有符号类型同级；字符类型与其底层类型同级；`bool` 最低。
    - [[g:floating-point-conversion-rank|浮点转换等级]]是偏序：一个类型的值集真包含另一个，它的等级才更高。`std::bfloat16_t` 和 `std::float16_t` 的等级无序，混合运算是非良构的。
    - 等级相同的浮点类型再按[[g:floating-point-conversion-subrank|子等级]]排序，`std::floatN_t` 优先于同级的标准类型，所以 `1.0f + 1.0f32` 的类型是 `std::float32_t`。

## 为什么要排等级

```cpp run ok
#include <type_traits>
// LP64（64 位 Linux、macOS）
static_assert(sizeof(long) == 8 && sizeof(long long) == 8);
static_assert(std::is_same_v<decltype(1LL + 1UL), unsigned long long>);
int main() {}
```

两个 64 位操作数相加，结果却是第三个类型。决定结果类型的常用算术转换（[[expr.arith.conv]]）需要知道哪个类型大，但这个大小不能用 `sizeof` 来定：同宽的类型可以不止一个，浮点类型之间甚至可能无法比较（一个范围大，另一个精度高）。本节给算术类型规定的顺序，就是**整数转换等级**（integer conversion rank）、**浮点转换等级**（floating-point conversion rank）和**浮点转换子等级**（floating-point conversion subrank）。

用到等级的规则：

| 规则 | 怎样用等级 |
|---|---|
| [[conv.prom]] 整数提升 | 等级低于 `int` 的整数类型提升为 `int` 或 `unsigned int` |
| [[expr.arith.conv]] 常用算术转换 | 两个操作数转换到等级高的一方；有符号与无符号混合时比较等级和可表示性 |
| [[conv.double]] 浮点转换 | 只能隐式转换到等级不低于源类型的浮点类型，标准浮点类型之间除外 |
| [[dcl.init.list#7]] 窄化 | 转换到等级不高于也不等于源类型的浮点类型，属于窄化 |
| [[over.ics.rank#4.3]] 重载决议 | 等级相等的浮点类型之间的转换优于其他转换 |

## 整数转换等级（¶1）

¶1 每个整数类型都有一个整数转换等级，由九条规则确定：

- ¶1.1 任意两个有符号整数类型等级不同，即使表示相同。
- ¶1.2 有符号整数类型的等级高于任何宽度更小的有符号整数类型。
- ¶1.3 `long long` > `long` > `int` > `short` > `signed char`。
- ¶1.4 无符号整数类型的等级等于对应有符号类型的等级。
- ¶1.5 标准整数类型的等级高于同宽度的扩展整数类型。
- ¶1.6 `bool` 的等级低于其他所有整数类型。
- ¶1.7 字符类型（`char`、`wchar_t`、`char8_t`、`char16_t`、`char32_t`）的等级等于其底层类型的等级（[[basic.fundamental]]）。
- ¶1.8 两个同宽度的扩展有符号整数类型之间的相对等级由实现定义，但仍受其他规则约束。
- ¶1.9 等级是传递的。

¶1.1 保证有符号类型之间是全序，常用算术转换总能选出一个。¶1.3 把五个标准有符号类型的顺序固定下来，不随宽度改变，所以同宽的 `long` 和 `long long` 仍然分得出高低。¶1.5 让实现新增一个扩展整数类型时，不会改变已有表达式的类型。注 1 说明，整数转换等级用于整数提升和常用算术转换。

几个推论：

- `char` 与 `signed char`、`unsigned char` 中的一个同级，但三者仍是不同的类型。这不违反 ¶1.1，因为 `char` 不是有符号整数类型。
- `char16_t`、`char32_t` 的底层类型分别是 `uint_least16_t`、`uint_least32_t`，通常就是 `unsigned short` 和 `unsigned int`，等级也与它们相同。
- ¶1.2 和 ¶1.3 放在一起，要求标准有符号类型的宽度单调不减，否则两条矛盾。

## 等级怎样决定整数运算的类型

[[expr.arith.conv#1.5]] 对两个整数操作数先做整数提升，得到类型 T1、T2，然后：

1. T1、T2 相同，结果就是这个类型；
2. 同为有符号或同为无符号，取等级高的；
3. 否则设 U 是无符号的一方、S 是有符号的一方：
    - U 的等级不低于 S，结果为 U；
    - 否则，S 能表示 U 的全部值，结果为 S；
    - 否则，结果为 S 对应的无符号类型。

第 3 步同时看等级和宽度，平台差异就从这里来：

```cpp run ok
#include <type_traits>

// 以下断言在 LP64（64 位 Linux、macOS）上成立
static_assert(sizeof(long) == 8 && sizeof(int) == 4);

static_assert(std::is_same_v<decltype(1 + 1U),   unsigned>);   // 同级，取 U
static_assert(std::is_same_v<decltype(1L + 1U),  long>);       // long 更高且能表示所有 unsigned
static_assert(std::is_same_v<decltype(1LL + 1UL), unsigned long long>);
// unsigned long 等级低于 long long，long long 又表示不了
// 全部 64 位 unsigned long 的值，结果取 long long 对应的无符号类型

static_assert(std::is_same_v<decltype('a' + 'b'),  int>);      // char 提升为 int
static_assert(std::is_same_v<decltype(true + true), int>);     // bool 提升为 int
static_assert(std::is_same_v<decltype(u'a' + 1),  int>);       // char16_t 提升为 int
static_assert(std::is_same_v<decltype(U'a' + 1),  unsigned>);  // char32_t 提升为 unsigned
static_assert(std::is_same_v<decltype((unsigned short)1 + (unsigned short)1), int>);

int main() {}
```

`1L + 1U` 在 LLP64（64 位 Windows，`long` 是 32 位）上得到 `unsigned long`，因为 32 位的 `long` 表示不了全部 `unsigned int` 的值。

有符号和无符号同级（¶1.4），是为了让第 3 步的结果尽量保值：`long` 比 `unsigned int` 宽时，`long` 能装下所有 `unsigned int` 的值，结果就保持有符号。这是从 C89 继承的保值（value preserving）方案。

整数提升也以等级为界。[[conv.prom#2]] 规定，`bool` 和几种字符类型以外，等级低于 `int` 的整数类型提升为 `int`（`int` 能表示它的全部值时），否则提升为 `unsigned int`。`char8_t`、`char16_t`、`char32_t`、`wchar_t` 由 [[conv.prom#6]] 提升为第一个能表示其底层类型全部值的类型，`bool` 由 [[conv.prom#7]] 提升为 `int`。

## 浮点转换等级（¶2）

C++23 之前只有三个浮点类型，`float < double < long double` 直接写在常用算术转换里。C++23 的 [[P1467R9]] 引入扩展浮点类型（[[basic.extended.fp]]），例如 `std::float16_t`、`std::bfloat16_t`，于是需要一条能处理任意多个浮点类型的规则。

¶2 每个浮点类型都有一个浮点转换等级：

- ¶2.1 某浮点类型的值集是 `T` 的值集的真子集时，`T` 的等级更高。
- ¶2.2 `long double` > `double` > `float`。
- ¶2.3 值集相同的两个扩展浮点类型等级相等。
- ¶2.4 扩展浮点类型与恰好一个标准浮点类型值集相同时，等级等于那个标准类型。
- ¶2.5 扩展浮点类型与不止一个标准浮点类型值集相同时，等级等于 `double`。

与整数等级不同，浮点等级是偏序。注 3 指出，两个类型的值集互不包含时，等级无序；一个范围更大、精度更低时就会这样。`std::bfloat16_t`（8 位指数、8 位有效数字）和 `std::float16_t`（5 位指数、11 位有效数字）就是这样一对。

假设 `float`、`double` 是 IEEE binary32、binary64，扩展类型都可用：

| 类型 | x86-64 Linux（`long double` 为 80 位） | Windows、Apple arm64（`long double` 与 `double` 相同） |
|---|---|---|
| `std::bfloat16_t`、`std::float16_t` | 低于 `float`，两者之间无序 | 同左 |
| `std::float32_t` | 等于 `float`（¶2.4） | 同左 |
| `std::float64_t` | 等于 `double`（¶2.4） | 等于 `double`（¶2.5，它与 `double`、`long double` 值集都相同） |
| `long double` | 高于 `double` | 仍高于 `double`（¶2.2，即使值集相同） |
| `std::float128_t` | 高于 `long double` | 高于 `long double` |

注 2 指出了一处与 C 的差异：在 `long double`、`double`、`std::float64_t` 值集都相同的平台上，C 对类似的 `_Float64` 处理方式不同（ISO/IEC 9899:2024 H.4.3）。

## 浮点转换子等级（¶3）

等级相等的浮点类型之间还要分先后，否则 `float + std::float32_t` 的类型定不下来。

¶3 等级相等的浮点类型按浮点转换子等级排序，子等级在同级的类型之间是全序。`std::float16_t`、`std::float32_t`、`std::float64_t`、`std::float128_t` 的子等级高于与之同级的任何标准浮点类型；其余情况下子等级的顺序由实现定义。

让扩展类型优先，是因为程序员显式写了 `std::float32_t`，通常就是想要格式确定的结果。混合运算如果退回 `float`，从类型上就看不出格式了。`std::bfloat16_t` 不在这个列表里，它的值集与任何标准浮点类型都不同，不会和它们同级。

¶4 是一个注：浮点转换等级和子等级用于常用算术转换。

## 浮点等级怎样决定运算的类型

[[expr.arith.conv#1.4]] 对浮点操作数的规定：类型相同则不转换；一方不是浮点类型则转换到浮点的一方；等级有序且不等则转换到等级高的；等级相等则转换到子等级高的；等级无序则非良构。

```cpp
#include <stdfloat>
#include <type_traits>

// 假设 float/double 为 binary32/binary64，且下列类型都可用
static_assert(std::is_same_v<decltype(1.0f + 1.0f16), float>);            // float16_t 等级低
static_assert(std::is_same_v<decltype(1.0f + 1.0f32), std::float32_t>);   // 同级，float32_t 子等级高
static_assert(std::is_same_v<decltype(1.0 + 1.0f64), std::float64_t>);    // 同上
static_assert(std::is_same_v<decltype(1.0L + 1.0f64), long double>);      // long double 等级更高
auto x = 1.0bf16 + 1.0f16;   // error: 等级无序
```

本机 Clang 23 和 libc++ 还没有提供 `<stdfloat>`，这段代码按标准推演，没有标注判定。对三个标准浮点类型，这套规则的结果与 C++20 完全相同。

### 隐式转换、窄化、重载

- [[conv.double#1]]：浮点 prvalue 可以隐式转换为等级不低于源类型的浮点类型；标准浮点类型之间可以任意方向转换。所以 `float f = d;`（`d` 是 `double`）仍然合法，`std::float32_t g = d;` 是非良构的。
- [[dcl.init.list#7.2]]：从浮点类型 `T` 转换到等级既不高于也不等于 `T` 的浮点类型是窄化（转换结果是常量表达式、值有限且没有溢出等情形除外）。等级无序也属于窄化。
- [[over.ics.rank#4.3]]：`FP1` 与同级的 `FP2` 之间的转换，优于 `FP1` 与其他算术类型之间的转换。标准的例子：

```cpp
int f(std::float32_t);
int f(std::float64_t);
int f(long long);
float x;
std::float16_t y;
int i = f(x);   // 调用 f(std::float32_t)：float 与 float32_t 同级
int j = f(y);   // error: 二义，没有与 float16_t 同级的候选
```

三个转换在 [[over.ics.scs]] 里都只是 Conversion 等级。没有 ¶4.3，`f(x)` 也会二义；有了它，同级浮点类型之间的转换胜出。`f(y)` 没有同级的候选，这条决胜规则用不上，仍然二义。

!!! impl "实现视角"
    - GCC 和 Clang 的 `__int128` 等级高于 `long long`，所以 `__int128 + unsigned long long` 的类型是 `__int128`。
    - Clang 的 `_Float16` 和 `__bf16` 没有按 C++23 扩展浮点类型实现：本机 libc++ 中 `std::is_floating_point_v<_Float16>` 为 `false`。它们的混合运算按 Clang 自己的规则进行，不能用来验证本节。

!!! history "历史与演进"
    - C++98 没有整数转换等级，常用算术转换直接逐个列举类型（若一方是 `long double`……否则若一方是 `double`……）。
    - C++11 加入 `long long` 和扩展整数类型时，从 C99 引入了整数转换等级，常用算术转换改用等级描述。
    - C++23 的 [[P1467R9]] 引入浮点转换等级和子等级，取代 `float < double < long double` 的硬编码；常用算术转换增加了等级无序时非良构的规定，浮点转换、窄化和重载决议随之修改。

## 常见误解

!!! pitfall "两个 64 位类型相加，结果是其中之一"
    `long long + unsigned long` 在 LP64 上是 `unsigned long long`。依赖结果类型的代码（模板分派、`auto` 变量、`printf` 格式符）应该用 `std::common_type_t` 或显式转换。

!!! pitfall "`long` 和 `unsigned` 混合运算在各平台上一样"
    LP64 上 `long + unsigned` 是 `long`，LLP64 上是 `unsigned long`。后者使 `-1L < 1U` 为假，因为 `-1L` 被转换成了 `unsigned long` 的最大值。GCC 和 Clang 的 `-Wsign-compare` 会警告这类比较，C++20 起可以改用 `std::cmp_less` 等函数（[[utility.intcmp]]）。

!!! pitfall "`std::float32_t` 可以像 `float` 一样从 `double` 初始化"
    `std::float32_t x = 0.1;` 是非良构的，要写 `0.1f32`。`float x = 0.1;` 合法，是因为标准浮点类型之间保留了任意方向的隐式转换。

## 思考题

!!! question "1. 某实现提供 64 位的扩展有符号整数类型 `__ext64`，`long long` 也是 64 位。`__ext64 + unsigned long long` 的类型是什么？"

<details markdown="1">
<summary>答案</summary>

`unsigned long long`。按 ¶1.5，标准整数类型的等级高于同宽度的扩展整数类型，所以 `unsigned long long` 的等级高于 `__ext64`。按 [[expr.arith.conv#1.5.3.1]]，无符号一方的等级不低于有符号一方，结果取无符号的一方。
</details>

!!! question "2. ¶2.5 为什么让 `std::float64_t` 取 `double` 的等级，而不是 `long double` 的？"

<details markdown="1">
<summary>答案</summary>

标准没有说明理由。一个合理的解释是让 `std::float64_t` 的行为不随平台变化。在 x86-64 Linux 上，`float64_t` 按 ¶2.4 与 `double` 同级，低于 `long double`。如果在 `long double` 与 `double` 相同的平台上让它取 `long double` 的等级，`float64_t + long double` 的结果就会变成 `float64_t`（子等级更高），与 Linux 上的 `long double` 不一致。取 `double` 的等级后，两个平台上 `float64_t` 都与 `double` 同级、低于 `long double`。
</details>

!!! question "3. `char` 与 `signed char` 同级，那么 `char + signed char` 的类型是什么？"

<details markdown="1">
<summary>答案</summary>

`int`。两个操作数的等级都低于 `int`，`int` 又能表示它们的全部值，整数提升后都是 `int`，按 [[expr.arith.conv#1.5.1]] 结果就是 `int`。这里用不到它们是否同级，整数等级主要在 `int` 及以上的类型之间起作用。
</details>
