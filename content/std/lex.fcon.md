---
title: 浮点字面量
summary: 十进制与十六进制浮点字面量的形式、类型（含 C++23 扩展浮点后缀 f16/f32/f64/f128/bf16）、值的计算方式，以及超出范围或无法精确表示时的规则。
status: draft
papers: P0245R1, P1467R9
related: basic.fundamental, basic.extended.fp, lex.ppnumber, lex.icon
tags: 字面量, 浮点
updated: 2026-10-17
---

[[lex.fcon]] 规定浮点字面量。它比整数字面量简单之处在于类型只由后缀决定（不查表）；复杂之处在于**值**：十进制小数一般无法在二进制浮点类型中精确表示，标准必须说明取哪个近似值，以及"太大"、"太小"时怎么办。

## 文法

```
floating-point-literal:
    decimal-floating-point-literal
    hexadecimal-floating-point-literal
decimal-floating-point-literal:
    fractional-constant exponent-part(opt) floating-point-suffix(opt)
    digit-sequence exponent-part floating-point-suffix(opt)
hexadecimal-floating-point-literal:
    hexadecimal-prefix hexadecimal-fractional-constant binary-exponent-part floating-point-suffix(opt)
    hexadecimal-prefix hexadecimal-digit-sequence binary-exponent-part floating-point-suffix(opt)
fractional-constant:
    digit-sequence(opt) . digit-sequence
    digit-sequence .
hexadecimal-fractional-constant:
    hexadecimal-digit-sequence(opt) . hexadecimal-digit-sequence
    hexadecimal-digit-sequence .
exponent-part:         e sign(opt) digit-sequence  |  E sign(opt) digit-sequence
binary-exponent-part:  p sign(opt) digit-sequence  |  P sign(opt) digit-sequence
sign: one of  +  -
digit-sequence:  digit  |  digit-sequence '(opt) digit
floating-point-suffix: one of
    f  l  f16  f32  f64  f128  bf16  F  L  F16  F32  F64  F128  BF16
```

要点：

- 十进制浮点字面量需要**小数点或指数**（至少其一）：`1.`、`.5`、`1e10` 都是浮点字面量，`1` 是整数。所以 `1f` **非良构**（它是带无效后缀 `f` 的整数字面量），要写 `1.f` 或 `1.0f`。
- 十六进制浮点字面量**必须**有二进制指数 `p`：`0x1.8` 非良构，`0x1.8p0` 合法。原因是 `0x1.8f` 若无指数，`f` 到底是十六进制数字还是 `float` 后缀就有歧义；强制 `p` 之后，指数部分只能是十进制数字，后缀不会与之混淆。
- 指数总是**十进制**数字，即使在十六进制浮点字面量中：`0x1p10` 是 1 × 2¹⁰ = 1024。
- 数字分隔符可出现在有效数字和指数的数字序列中：`1.602'176'565e-19`、`1e1'0`。
- 后缀：`f`、`l`、`F`、`L`；C++23 起加上扩展浮点后缀，大小写只能**全小写或全大写**（`bf16`、`BF16`，没有 `Bf16`）。没有 `d`、`lf` 之类的后缀。

```cpp run title="fcon-forms.cpp" ok
static_assert(1. == 1.0 && .5 == 0.5 && 1e10 == 10000000000.0);
static_assert(0x1.8p1 == 3.0);       // 1.5 × 2¹
static_assert(0x.8p0 == 0.5);        // 0.5 × 2⁰
static_assert(0x1p10 == 1024.0);     // 指数是十进制的 10
static_assert(1e1'0 == 1e10);        // 指数里也能用分隔符
int main() {}
```

```cpp title="fcon-bad.cpp" error
auto a = 1f;        // error：整数字面量 1 带无效后缀 f
auto b = 0x1.8;     // error：十六进制浮点字面量必须有 p 指数
auto c = 1e;        // error：指数没有数字
auto d = 1.0lf;     // error：没有 lf 后缀
```

## ¶1：类型

¶1 浮点字面量的类型（[[basic.fundamental]]、[[basic.extended.fp]]）由后缀决定（表 11）：

| 后缀 | 类型 |
|---|---|
| 无 | `double` |
| `f`、`F` | `float` |
| `l`、`L` | `long double` |
| `f16`、`F16` | `std::float16_t` {{c++23}} |
| `f32`、`F32` | `std::float32_t` {{c++23}} |
| `f64`、`F64` | `std::float64_t` {{c++23}} |
| `f128`、`F128` | `std::float128_t` {{c++23}} |
| `bf16`、`BF16` | `std::bfloat16_t` {{c++23}} |

注 1：扩展浮点后缀是**有条件支持**的，见 [[basic.extended.fp]]——只有实现提供了对应的 `std::floatN_t` 类型（定义了 `__STDCPP_FLOAT16_T__` 等宏）时，相应后缀才受支持。

几个值得强调的事实：

- `std::float32_t` **不是** `float`，即使二者格式完全相同（IEEE binary32）。它们是不同的类型（扩展浮点类型），有不同的转换等级规则（[[conv.rank]]）。所以 `1.0f32` 和 `1.0f` 的类型不同。
- 无后缀是 `double`，不是 `float`：`float x = 0.1;` 先产生一个 `double` 值，再转换（舍入两次的问题见下文）。

```cpp run title="fcon-types.cpp" ok
#include <type_traits>
static_assert(std::is_same_v<decltype(1.0), double>);
static_assert(std::is_same_v<decltype(1.0f), float>);
static_assert(std::is_same_v<decltype(1.0L), long double>);
int main() {}
```

!!! impl "实现现状"
    GCC 已实现这些类型与后缀（并提供 `<stdfloat>`，具体可用的类型取决于目标平台）。实测 Clang 23 + libc++：接受 `f16` 后缀，但给出的类型是 Clang 内建的 `_Float16`；不接受 `f32`、`f64`、`f128`、`bf16`；不提供 `<stdfloat>`，也不定义 `__STDCPP_FLOAT16_T__` 等宏。这在标准看来是"不支持这些有条件支持的特性"，是允许的。

## ¶2：值的计算

¶2 定义了三个量：

- [[g:significand|**有效数字**]]（significand）：十进制字面量的 *fractional-constant* 或 *digit-sequence*，十六进制字面量的 *hexadecimal-fractional-constant* 或 *hexadecimal-digit-sequence*。其中的数字和可选的小数点按基数 N（十进制 10，十六进制 16）解释为一个**实数** s。分隔用的单引号被忽略。
- **指数** e：若有指数部分，就是可选符号加数字按十进制解释的整数；否则为 0。
- **缩放值**（scaled value）：十进制为 s × 10^e，十六进制为 s × 2^e。

缩放值是一个精确的数学实数，接下来 ¶3 才把它映射到类型的值。

```cpp run title="fcon-value.cpp" ok
static_assert(49.625 == 0xC.68p+2);   // ¶2 的例子：0xC.68 = 12 + 6/16 + 8/256 = 12.40625；× 2² = 49.625
static_assert(1.602'176'565e-19 == 1.602176565e-19);
int main() {}
```

### 为什么要有十六进制浮点字面量

十进制字面量 `0.1` 的缩放值是 1/10，在二进制浮点中无法精确表示，结果依赖于舍入。十六进制浮点字面量的缩放值是 s × 2^e，其中 s 是有限位十六进制数——只要位数不超过类型的精度，它**总能精确表示**。这让人能精确写出特定的位模式，例如 `0x1p-1074`（最小的正 `double` 次正规数）、`0x1.fffffffffffffp+1023`（`DBL_MAX`）。这正是数学库实现者需要的。十六进制浮点字面量在 C99 中引入，C++17 才通过 [[P0245R1]] 加入 C++。

## ¶3：范围与舍入

¶3 若缩放值**不在**该类型的可表示值范围内，程序非良构。否则，若缩放值可以精确表示，值就是它；否则是**下一个更大或更小**的可表示值，二者择一的方式由**实现定义**。

### "范围"包括无穷大

关键在于"可表示值范围"的定义（[[basic.fundamental#13]]）：浮点类型的最小范围是从最负的有限值到最正的有限值；但**如果类型能表示正（负）无穷大，范围就扩展到所有正（负）实数**。IEEE 754 格式都有无穷大，所以：

- 对 IEEE `double`，`1e400` **在范围内**，不是非良构！它无法精确表示，于是取"下一个更大"（+∞）或"下一个更小"（`DBL_MAX`），由实现定义。
- 同理，`1e-400` 的值是 0 或最小的正次正规数，由实现定义。
- 只有对**没有无穷大**的浮点格式，过大的字面量才非良构。

```cpp run title="fcon-range.cpp" impl
#include <limits>
constexpr double big = 1e400;     // 实现定义：+∞ 或 DBL_MAX；Clang 给出 +∞ 并警告
static_assert(big == std::numeric_limits<double>::infinity()
           || big == std::numeric_limits<double>::max());
int main() {}
```

标准的例 2 正是这样写的（假设支持 `std::float32_t`）：`1e1000000000f32`"要么是最大有限值，要么是正无穷"。Clang 对 `1e400` 给出 `-Wliteral-range` 警告（"magnitude of floating-point constant too large for type 'double'"），这只是警告，程序是良构的。

### 舍入方向由实现定义

标准**不**要求"舍入到最近"——只要求在两个相邻的可表示值中取一个。实践中所有主流编译器都按 IEEE 754 的"舍入到最近，平局取偶"在编译期转换字面量（与运行时的舍入模式无关）。

```cpp run title="fcon-round.cpp" impl
static_assert(0.1 + 0.2 != 0.3);   // 在 IEEE double + 舍入到最近的实现上成立
int main() {}
```

### 双重舍入

`float f = 0.1;` 先把 1/10 舍入到 `double`，再把这个 `double` 值转换到 `float`（[[conv.double]]）。这与直接写 `0.1f`（1/10 一次舍入到 `float`）在极少数值上结果不同——双重舍入可能跨过平局点。需要精确的 `float` 值时，用 `f` 后缀。

## 历史与演进

!!! history
    | 版本 | 变化 |
    |---|---|
    | C++98 | 十进制浮点字面量；`f`、`l` 后缀 |
    | C++14 | 数字分隔符 |
    | C++17 | 十六进制浮点字面量（[[P0245R1]]）；pp-number 加入 `p sign`（[[diff.cpp14.lex]]） |
    | C++23 | 扩展浮点类型与后缀 `f16` `f32` `f64` `f128` `bf16`（[[P1467R9]]） |

## 陷阱

!!! pitfall "`1f` 不是 float"
    它根本不合法。`1.f`、`1.0f` 或 `1e0f` 才是。

!!! pitfall "以为 `1e400` 非良构"
    在 IEEE 平台上它是良构的，值为 +∞ 或 `DBL_MAX`（实现定义）。想写无穷大请用 `std::numeric_limits<double>::infinity()`，意图更清楚。

!!! pitfall "以为 `f32` 后缀给出 `float`"
    `1.0f32` 的类型是 `std::float32_t`，与 `float` 是不同的类型：`std::is_same_v<std::float32_t, float>` 为 `false`，`auto x = 1.0f32;` 后 `x` 不能绑定到 `float&`。

## 思考题

!!! question "思考题"
    下列字面量哪些良构？各自类型是什么？

    ```cpp
    0x1p-1074      1e-400f      0x1.0p      .e1      1.e+5L      0xAp1F
    ```

<details markdown="1">
<summary>答案</summary>

- `0x1p-1074`：良构，`double`，值为 2⁻¹⁰⁷⁴，在 IEEE `double` 中是最小的正次正规数，可精确表示。
- `1e-400f`：良构，`float`；缩放值在范围内（0 与最小正次正规数之间），值为二者之一（实现定义）。
- `0x1.0p`：非良构，二进制指数没有数字。
- `.e1`：不是浮点字面量：`.` 后面必须跟数字。它被切成 `.` 和标识符 `e1`。
- `1.e+5L`：良构，`long double`，值 100000。
- `0xAp1F`：良构，`float`，值 10 × 2¹ = 20。这里 `F` 不会被当成十六进制数字，因为 `p` 之后的指数只能是十进制数字——这正是十六进制浮点必须带 `p` 的原因。
</details>

## 小结

!!! summary
    - 十进制浮点需要小数点或指数；十六进制浮点必须有 `p` 指数（指数本身是十进制）。
    - 类型只由后缀决定：无 → `double`，`f` → `float`，`l` → `long double`；C++23 的 `f16` 等后缀给出 `std::floatN_t`，有条件支持。
    - 值 = 有效数字 × 10^e（或 2^e）；不能精确表示时取相邻两个值之一（实现定义）。
    - IEEE 类型的"范围"包括所有实数（因为有无穷大），所以 `1e400` 良构；只有无无穷大的类型才会因越界而非良构。
