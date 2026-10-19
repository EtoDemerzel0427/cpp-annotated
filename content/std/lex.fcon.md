---
title: 浮点字面量
summary: 十进制与十六进制浮点字面量怎么写，类型怎样由后缀决定，以及值怎样计算：无法精确表示时取相邻两个值之一，超出范围才非良构，而 IEEE 类型的范围包括所有实数。
status: done
papers: P0245R1, P1467R9
related: basic.fundamental, basic.extended.fp, lex.ppnumber, lex.icon, conv.double
tags: 字面量, 浮点
updated: 2026-10-19
---

!!! tldr
    - 十进制浮点字面量必须有小数点或指数：`1.f` 是 `float`，`1f` 非良构。
    - 十六进制浮点字面量 `0x1.8p1` 必须带 `p` 指数，它的值是有效数字乘以 2 的幂，可以精确写出任意二进制浮点值。
    - 类型只由后缀决定：无后缀是 `double`，`f` 是 `float`，`l` 是 `long double`；C++23 的 `f16`、`f32`、`f64`、`f128`、`bf16` 给出扩展浮点类型，有条件支持。
    - 值无法精确表示时，取紧邻的较大或较小的可表示值，选哪一个由实现定义。
    - IEEE 浮点类型有无穷大，按标准它的范围包括所有实数，所以 `1e400` 是良构的，值为 +∞ 或 `DBL_MAX`。

## 两种写法

```cpp run title="fcon-forms.cpp" ok
static_assert(1. == 1.0 && .5 == 0.5 && 1e10 == 10000000000.0);
static_assert(0x1.8p1 == 3.0);    // 1.5 × 2¹
static_assert(0x.8p0 == 0.5);     // 0.5 × 2⁰
static_assert(0x1p10 == 1024.0);  // 指数是十进制的 10
static_assert(1e1'0 == 1e10);     // 指数里也可以用数字分隔符
int main() {}
```

**十进制浮点字面量**至少要有小数点或指数部分（`e` 或 `E` 加可选符号和十进制数字）之一，所以 `1.`、`.5`、`1e10` 都是浮点字面量，`1` 是整数字面量。

**十六进制浮点字面量**以 `0x` 开头，有效数字是十六进制，后面必须跟 `p` 或 `P` 引出的二进制指数。指数总是用十进制书写，表示 2 的幂：`0x1p10` 是 1 × 2¹⁰。

`p` 指数之所以是必需的，是为了避免歧义。如果允许省略，`0x1.8f` 里的 `f` 既可能是十六进制数字，也可能是 `float` 后缀。有了 `p`，指数部分只能是十进制数字，后缀就不会和它混淆。

```cpp title="fcon-bad.cpp" error
auto a = 1f;      // error: 这是整数字面量 1 加上无效后缀 f
auto b = 0x1.8;   // error: 十六进制浮点字面量必须有 p 指数
auto c = 1e;      // error: 指数没有数字
auto d = 1.0lf;   // error: 没有 lf 后缀
```

有效数字和指数中都可以使用数字分隔符 `'`。后缀有 `f`、`l` 以及 C++23 的扩展浮点后缀，后者只能全小写或全大写，例如 `bf16` 或 `BF16`，没有 `Bf16`。

## 类型（¶1）

¶1 浮点字面量的类型由后缀决定：

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

```cpp run title="fcon-types.cpp" ok
#include <type_traits>
static_assert(std::is_same_v<decltype(1.0), double>);
static_assert(std::is_same_v<decltype(1.0f), float>);
static_assert(std::is_same_v<decltype(1.0L), long double>);
int main() {}
```

注 1 说明，后五种后缀是有条件支持的：只有实现提供了对应的扩展浮点类型时，这些后缀才可用（[[basic.extended.fp]]）。

`std::float32_t` 不是 `float`。即使两者的格式都是 IEEE binary32，`std::float32_t` 仍是另一个类型，转换等级的规则也不同（[[conv.rank]]）。所以 `1.0f32` 和 `1.0f` 的类型不同。

!!! impl "实现现状"
    GCC 实现了这些类型和后缀，并提供 `<stdfloat>`，具体有哪些类型取决于目标平台。本机 Clang 23 + libc++ 接受 `f16` 后缀，但得到的类型是 Clang 内建的 `_Float16`；`f32`、`f64`、`f128`、`bf16` 都被拒绝；没有 `<stdfloat>`，也不定义 `__STDCPP_FLOAT16_T__` 等宏。按标准，这相当于不支持这些有条件支持的特性，是允许的。

## 值（¶2–¶3）

### 缩放值（¶2）

¶2 字面量的值分两步得到。第一步，算出一个精确的实数：

- **有效数字**（significand）是字面量里指数之前的那部分数字和小数点，按十进制或十六进制解释为实数 s，数字分隔符不影响值；
- 指数 e 是指数部分按十进制解释得到的整数，没有指数部分时为 0；
- **缩放值**（scaled value）对十进制字面量是 s × 10^e，对十六进制字面量是 s × 2^e。

```cpp run title="fcon-value.cpp" ok
// 0xC.68 = 12 + 6/16 + 8/256 = 12.40625，乘以 2² 得 49.625
static_assert(49.625 == 0xC.68p+2);
static_assert(1.602'176'565e-19 == 1.602176565e-19);
int main() {}
```

### 映射到类型（¶3）

¶3 第二步，把缩放值映射到类型的值。缩放值超出类型的可表示范围时，程序非良构。否则，能精确表示就取它本身；不能精确表示，就取紧邻的较大值或较小值，选哪一个由实现定义。

标准没有要求舍入到最近。实际上 GCC 和 Clang 都在编译期按 IEEE 754 的就近舍入、平局取偶来转换字面量，与运行时的舍入模式无关。

```cpp run title="fcon-round.cpp" impl
// 0.1、0.2、0.3 都不能精确表示；
// 在 IEEE double、就近舍入的实现上，下式成立
static_assert(0.1 + 0.2 != 0.3);
int main() {}
```

### 范围包括所有实数

什么叫超出范围，由 [[basic.fundamental#13]] 规定。浮点类型的可表示范围至少是从最小的有限值到最大的有限值；如果类型能表示正无穷大，范围就扩展到所有正实数，负的一侧同理。IEEE 754 格式都有无穷大，所以任何实数都在范围之内：

- 对 IEEE `double`，`1e400` 在范围内，不是非良构。它不能精确表示，于是取 +∞ 或 `DBL_MAX`，由实现定义。
- `1e-400` 的值是 0 或最小的正次正规数，同样由实现定义。
- 只有对没有无穷大的浮点格式，过大的字面量才非良构。

```cpp run title="fcon-range.cpp" impl
#include <limits>
constexpr double big = 1e400;   // +∞ 或 DBL_MAX；Clang 给出 +∞ 并警告
static_assert(big == std::numeric_limits<double>::infinity()
           || big == std::numeric_limits<double>::max());
int main() {}
```

本机 Clang 23 对 `1e400` 给出 `-Wliteral-range` 警告 "magnitude of floating-point constant too large for type 'double'"。这只是警告，程序是良构的。标准的例 2 也这样写：假设支持 `std::float32_t`，`1e1000000000f32` 的值是最大有限值或正无穷。

### 为什么需要十六进制浮点字面量

十进制的 `0.1` 是 1/10，在二进制浮点中无法精确表示，结果取决于舍入。十六进制字面量的缩放值是 s × 2^e，只要有效数字的位数不超过类型的精度，就能精确表示。

所以它可以精确写出特定的值，例如 `0x1p-1074` 是最小的正 `double` 次正规数，`0x1.fffffffffffffp+1023` 是 `DBL_MAX`。数学库的实现和测试经常需要这种写法。C99 就有十六进制浮点字面量，C++17 才通过 [[P0245R1]] 加入。

### 两次舍入

`float f = 0.1;` 先把 1/10 舍入到 `double`，再把这个 `double` 转换为 `float`（[[conv.double]]）。`0.1f` 则把 1/10 一次舍入到 `float`。两次舍入可能跨过平局点，所以在极少数值上两者结果不同。需要准确的 `float` 值时，应当直接写 `f` 后缀。

## 历史与演进

!!! history
    | 版本 | 变化 |
    |---|---|
    | C++98 | 十进制浮点字面量；`f`、`l` 后缀 |
    | C++14 | 数字分隔符 |
    | C++17 | 十六进制浮点字面量（[[P0245R1]]）；预处理数字中可以出现 `p+`、`p-`（[[diff.cpp14.lex]]） |
    | C++23 | 扩展浮点类型和后缀 `f16`、`f32`、`f64`、`f128`、`bf16`（[[P1467R9]]） |

## 常见误解

!!! pitfall "`1f` 是 float"
    它根本不合法。要写 `1.f`、`1.0f` 或 `1e0f`。

!!! pitfall "`1e400` 非良构"
    在 IEEE 平台上它是良构的，值为 +∞ 或 `DBL_MAX`。要表示无穷大，用 `std::numeric_limits<double>::infinity()`，意图更清楚。

!!! pitfall "`f32` 后缀给出 `float`"
    `1.0f32` 的类型是 `std::float32_t`，与 `float` 是不同的类型，`auto x = 1.0f32;` 之后 `x` 不能绑定到 `float&`。

## 思考题

!!! question "思考题"
    下列写法哪些是良构的浮点字面量？各自的类型是什么？

    ```cpp
    0x1p-1074      1e-400f      0x1.0p      .e1      1.e+5L      0xAp1F
    ```

<details markdown="1">
<summary>答案</summary>

- `0x1p-1074`：良构，`double`，值为 2⁻¹⁰⁷⁴，是 IEEE `double` 最小的正次正规数，可以精确表示。
- `1e-400f`：良构，`float`。缩放值在范围内，介于 0 和最小的正次正规数之间，值是两者之一，由实现定义。Clang 会给出 `-Wliteral-range` 警告。
- `0x1.0p`：非良构，二进制指数没有数字。
- `.e1`：不是浮点字面量，`.` 后面必须跟数字。它被切分成 `.` 和标识符 `e1`。
- `1.e+5L`：良构，`long double`，值为 100000。
- `0xAp1F`：良构，`float`，值为 10 × 2¹ = 20。`F` 不会被当成十六进制数字，因为 `p` 之后的指数只能是十进制数字。
</details>
