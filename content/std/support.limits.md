---
title: 实现属性
summary: <version> 的库特性测试宏，<limits> 的 numeric_limits 及其每个成员的精确含义（min 与 lowest、digits 与 digits10、is_modulo、traps……），以及 <climits>/<cfloat> 的 C 宏
status: done
covers: *
papers: P2614R2
related: support, basic.fundamental, conv.prom, conv.rank, cpp.predefined, expr.pre, support.types, support.arith.types, basic.extended.fp
tags: 标准库, numeric_limits, 特性测试宏, climits, cfloat
updated: 2026-10-18
---

[[basic.fundamental]] 故意把很多东西留给实现：`int` 有多宽、`char` 是否有符号、`long double` 用什么格式、浮点数是否遵循 IEEE 754……这些都是**由实现定义的**。程序要写得可移植，就需要一种在**编译期**查询这些属性的办法。[support.limits] 提供了三套工具：

- `<limits>` 的类模板 `std::numeric_limits<T>`：C++ 风格、可用于模板、全部 `constexpr`；
- `<climits>`、`<cfloat>`：继承自 C 的宏（`INT_MAX`、`DBL_EPSILON`……），可以在 `#if` 里用；
- `<version>`：不是数值类型的属性，而是**标准库本身**的属性——库实现了哪些特性（`__cpp_lib_*` 宏）。

¶1（[support.limits.general]）：`<limits>`、`<climits>`、`<cfloat>` 提供依赖于实现的算术类型（[[basic.fundamental]]）的特性。

## `<version>` 与库特性测试宏（[version.syn]）

¶1：`<version>` 提供依赖于实现的、关于 C++ 标准库的信息（例如版本号和发布日期）。它的主体是三百多个 `__cpp_lib_*` 宏。

¶2：每个宏除了在 `<version>` 中定义，还在概要注释所列的头文件被包含后定义。例如：

```cpp
#define __cpp_lib_launder           201606L // freestanding, also in <new>
#define __cpp_lib_three_way_comparison 201907L // freestanding, also in <compare>
#define __cpp_lib_source_location   201907L // freestanding, also in <source_location>
```

宏的值是一个 `yyyymmL` 形式的整数字面量，大致对应该特性被批准进工作草案的年月；注 1 提醒：标准的未来版本**可能会把这些值换成更大的值**（特性被扩充时）。所以正确的用法总是 `>=` 比较：

```cpp run title="feature-test.cpp" ok
#include <version>

#if defined(__cpp_lib_three_way_comparison) && __cpp_lib_three_way_comparison >= 201907L
#  include <compare>
constexpr bool has_spaceship_lib = true;
#else
constexpr bool has_spaceship_lib = false;
#endif

int main() { return has_spaceship_lib ? 0 : 1; }
```

和它配套的是 [[cpp.predefined]] 中的**语言**特性测试宏（`__cpp_concepts`、`__cpp_impl_coroutine`……），那些由编译器预定义，不需要包含任何头文件。`__cpp_lib_*` 由库定义，因此**必须先包含 `<version>` 或对应头文件**——在没有包含任何头文件时检查 `__cpp_lib_launder` 永远得到"未定义"。

本节还有几条特殊规则：

- ¶3：一组 `__cpp_lib_hardened_*` 宏（`__cpp_lib_hardened_vector` 等）只在**加固实现**（[[g:hardened-implementation]]）中定义；¶7 是推荐实践：非加固实现不应定义它们。
- ¶4：`__cpp_lib_freestanding_operator_new` 的值取决于实现：如果所有可替换全局分配函数的默认版本都满足宿主实现的要求，则为 `202306L`，否则为 `0`（[[new.delete]]）。这让独立实现可以只提供一个"总是失败"的 `operator new`。
- ¶5：`__cpp_lib_replaceable_contract_violation_handler`：契约违反处理函数可替换时为 `202603L`，否则为 `0`（[[basic.contract.handler]]）。
- ¶6：推荐实践：独立实现只在**完整提供**某一设施时才定义对应的宏。

!!! note "特性测试宏的值不是规范性承诺"
    宏的值是"该特性在哪一版论文时被加进标准"的记号，并不意味着实现在那个日期之后的所有修订都实现了。libc++ 在 `<version>` 头部注释中列出它定义的每个宏和值，并把尚未完成的特性以注释形式（`// # define __cpp_lib_...`）留在文件里。

## `float_round_style`（[round.style]）

一个**非作用域**枚举，描述浮点运算的舍入方式：

| 枚举项 | 值 | 含义 |
|---|---|---|
| `round_indeterminate` | -1 | 无法确定 |
| `round_toward_zero` | 0 | 向零舍入 |
| `round_to_nearest` | 1 | 舍入到最近的可表示值；两个一样近时，取最低有效位为偶数的那个（"银行家舍入"） |
| `round_toward_infinity` | 2 | 向正无穷 |
| `round_toward_neg_infinity` | 3 | 向负无穷 |

它是 `numeric_limits<T>::round_style` 的类型；它的取值和 C 的 `FLT_ROUNDS` 宏一一对应（脚注 164）。注意 `round_style` 是 `static constexpr`，描述的是**默认**舍入方式；程序在运行时用 `<cfenv>` 的 `fesetround` 改变舍入方向后，`round_style` 不会跟着变。

## `numeric_limits` 的总体规则（[numeric.limits.general]）

主模板长这样（节选）：

```cpp
template<class T> class numeric_limits {
public:
  static constexpr bool is_specialized = false;
  static constexpr T min() noexcept { return T(); }
  static constexpr T max() noexcept { return T(); }
  static constexpr int  digits = 0;
  // …… 共 30 余个成员，全部为 0 / false / T()
  static constexpr float_round_style round_style = round_toward_zero;
};
```

规则分五条：

- ¶2：所有 `static constexpr` 成员，特化都必须定义成**可用于常量表达式**的值。
- ¶3：主模板中所有数据成员都是**值初始化**的，所有成员函数都返回**值初始化**的对象。注 1：这意味着除非对某类型特化了 `numeric_limits`，否则所有成员都是 0 或 `false`——**对一个任意类型查询 `numeric_limits` 不会报错，只会悄悄得到 0**。因此泛型代码在使用之前必须先检查 `is_specialized`。
- ¶4：**每个算术类型**（包括 `bool`）都必须有特化，且 `is_specialized` 为 `true`。"算术类型"按 [[basic.fundamental]] 包括扩展整数类型和扩展浮点类型（[[basic.extended.fp]]，如 `std::float16_t`）。
- ¶5：对 cv 限定类型 *cv* `T` 的特化，各成员值必须和非限定的 `T` 相同。概要里因此有 `numeric_limits<const T>`、`numeric_limits<volatile T>`、`numeric_limits<const volatile T>` 三个偏特化。
- ¶6：**非算术的标准类型**，例如 `complex<T>`，**不得**有特化。

!!! pitfall "主模板不报错，只给 0"
    `std::numeric_limits<std::byte>::max()` 能编译，返回 `std::byte{0}`——`std::byte` 是枚举，不是算术类型。同理 `numeric_limits<std::string>::max()` 返回空字符串。

```cpp run title="limits-primary.cpp" ok
#include <cstddef>
#include <limits>

template<class T>
constexpr T saturating_max() {
    static_assert(std::numeric_limits<T>::is_specialized, "need numeric_limits<T>");
    return std::numeric_limits<T>::max();
}

static_assert(!std::numeric_limits<std::byte>::is_specialized);
static_assert(std::numeric_limits<std::byte>::max() == std::byte{0});   // 主模板：值初始化
static_assert(std::numeric_limits<const volatile int>::max()
              == std::numeric_limits<int>::max());                     // ¶5
// constexpr auto b = saturating_max<std::byte>();   // error: static_assert 失败

int main() { return saturating_max<unsigned char>() == 255 ? 0 : 1; }
```

**程序可以为自己定义的类型特化 `numeric_limits`**：[[namespace.std]] 允许对标准库类模板做程序定义的特化，只要特化依赖于程序定义类型并满足原模板的要求。大整数库、定点数库通常都这么做。

## 每个成员的含义（[numeric.limits.members]）

¶1：本小节定义的每个成员函数都是**信号安全**的（[[support.signal]]），可以在信号处理函数中调用。

每个成员都有一句"在什么条件下有意义"（Meaningful for…）。[numeric.special] ¶1 规定：**所有特化必须提供所有成员**，但"无意义"的值必须设为 0 或 `false`。下面按功能分组讲。

### 值域：`min`、`max`、`lowest`（¶2–¶8）

这是最容易出错的一组：

| 成员 | 整数类型 | 浮点类型 |
|---|---|---|
| `min()` | 最小值（如 `INT_MIN`） | **最小的正规格化值**（如 `DBL_MIN ≈ 2.2e-308`），**不是**最负的值 |
| `max()` | 最大值 | 最大有限值 |
| `lowest()` | 同 `min()` | 最负的有限值，通常是 `-max()` |

¶3 明确说：对于有次正规数（subnormal）的浮点类型，`min()` 返回最小的**正规格化**正数。这是从 C 的 `DBL_MIN` 继承来的历史包袱（脚注 150：等价于 `CHAR_MIN`、`FLT_MIN`、`DBL_MIN` 等），整数与浮点语义不一致，坑了无数人：

```cpp run title="min-vs-lowest.cpp" ok
#include <algorithm>
#include <limits>
#include <vector>

double max_of(const std::vector<double>& v) {
    // double m = std::numeric_limits<double>::min();    // 错误：min() 是一个很小的正数！
    double m = std::numeric_limits<double>::lowest();    // 正确：C++11 引入的 lowest()
    for (double x : v) m = std::max(m, x);
    return m;
}

int main() { return max_of({-3.0, -1.5, -7.0}) == -1.5 ? 0 : 1; }
```

¶7 定义 `lowest()` 为"有限值 x，不存在另一个有限值 y < x"。脚注 152 解释了为什么需要它：并非所有浮点表示的最负值都等于最正值取负（例如某些非 IEEE 格式的指数范围不对称）。

"Meaningful for" 条件：`min()` 在 `is_bounded` 为真时有意义，或者在 `is_bounded == false && is_signed == false`（无界无符号类型，如任意精度自然数，最小值是 0）时有意义。`max()` 和 `lowest()` 只在 `is_bounded` 为真时有意义。

### 精度：`digits`、`digits10`、`max_digits10`（¶9–¶15）

- `digits`：能**无损表示**的 `radix` 进制位数。整数类型是**非符号位的个数**（`int` 为 31，`unsigned` 为 32，`bool` 为 1；`char` 有符号时为 7）；浮点类型是有效数字（significand）的位数，包括隐含的首位（`float` 24、`double` 53）。
- `digits10`：能无损表示的十进制位数——**任何**这么多位的十进制数都能存进该类型而不丢失。`int` 是 9（任何 9 位十进制整数都放得下，但并非所有 10 位的都放得下），`double` 是 15。
- `max_digits10`：要保证**不同的值打印出来也不同**所需的十进制位数，只对浮点类型有意义（`float` 9、`double` 17）。这是浮点数**往返**（序列化后再解析得回原值）所需的位数。

二者方向相反：`digits10` 是"十进制 → 二进制 → 十进制"不丢失的上限；`max_digits10` 是"二进制 → 十进制 → 二进制"不丢失的下限。

```cpp run title="digits.cpp" ok
#include <limits>

using L = std::numeric_limits<double>;
static_assert(L::digits == 53 && L::digits10 == 15 && L::max_digits10 == 17);   // IEEE binary64
static_assert(std::numeric_limits<int>::digits == 31);                           // 32 位 int
static_assert(std::numeric_limits<unsigned>::digits == 32);
static_assert(std::numeric_limits<bool>::digits == 1);
static_assert(std::numeric_limits<int>::digits10 == 9);

int main() {}
```

（这个例子假定 IEEE 754 binary64 的 `double` 和 32 位 `int`，在主流平台上成立，但标准并不保证。）

### 类型分类：`is_signed`、`is_integer`、`is_exact`、`radix`（¶16–¶24）

- `is_exact`：使用精确表示。所有整数类型都精确，但精确的不一定是整数（¶20：有理数和定点数表示精确但不是整数）。
- `radix`：浮点类型的指数基数（通常 2，脚注 155 等价于 `FLT_RADIX`）；整数类型的表示基数（脚注 156：区分 BCD 等非 2 进制类型）。

`numeric_limits<char>::is_signed` 回答了 [[basic.fundamental]] 中 "`char` 是否有符号"这个由实现定义的问题：x86-64 Linux 与 Apple 平台上为 `true`，AArch64 Linux 上为 `false`。`wchar_t` 同理；`char8_t`、`char16_t`、`char32_t` 总是无符号的。

### 浮点特性：`epsilon` 到 `max_exponent10`（¶25–¶35）

- `epsilon()`：机器 epsilon，即 1 与"大于 1 的最小可表示值"之差（`double` 为 2⁻⁵²）。**它是 1 附近的间距**，不是一个通用的"比较容差"——在 1e10 附近，相邻两个 `double` 之差远大于 `epsilon()`。
- `round_error()`：最大舍入误差的度量。IEEE 就近舍入时为 0.5（单位是 ULP）。标准的措辞相当含糊。
- `min_exponent` / `max_exponent`：使 radix 的 (e − 1) 次方仍是规格化数 / 有限数的最小 / 最大整数 e。注意"减 1"：`double` 的 `min_exponent` 为 −1021，`max_exponent` 为 1024，而规格化数的实际指数范围是 [−1022, 1023]。这个"偏 1"是为了与 C 的 `DBL_MIN_EXP` 保持一致（C 把有效数字写成 0.1xxx 形式而非 1.xxx）。
- `min_exponent10` / `max_exponent10`：十进制版本，10 的该次幂落在规格化 / 有限范围内。

### 特殊值：无穷与 NaN（¶36–¶52）

- `has_infinity`、`has_quiet_NaN`、`has_signaling_NaN`：在 `is_iec559` 为真时**必须**为真（¶38、¶41、¶44）。
- `infinity()`、`quiet_NaN()`、`signaling_NaN()`：在对应 `has_*` 为真时有意义；在 `is_iec559` 为真时必须提供。
- `denorm_min()`：最小的正次正规数；如果不支持次正规数，则为最小的正规格化正数。

!!! note "`has_denorm` 去了哪里"
    C++23 之前，`numeric_limits` 还有 `has_denorm`（类型为 `float_denorm_style`）和 `has_denorm_loss`。它们在 C++23 被 [[P2614R2]] 弃用，现在已从 [numeric.limits] 移到附录 [[depr.numeric.limits.has.denorm]]。理由是：是否支持次正规数常常是**运行时**可切换的（例如 x86 的 FTZ/DAZ 模式），一个编译期常量无法如实描述。

### IEEE 一致性与有界性：`is_iec559`、`is_bounded`（¶53–¶56）

- `is_iec559`：**当且仅当**类型遵循 ISO/IEC 60559（即 IEEE 754，脚注 162）时为 `true`。注 1：`std::float16_t`、`float32_t`、`float64_t`、`float128_t`（若存在）都为 `true`（[[basic.extended.fp]]）。
- `is_bounded`：可表示值的集合是有限的。注 2：所有基本类型都是有界的，任意精度类型才会是 `false`。

!!! lawyer "`is_iec559` 为真意味着什么、不意味着什么"
    `is_iec559` 只说明**类型的表示和运算**遵循 IEEE 754。它并不保证编译器在任何优化选项下都保持 IEEE 语义：用 `-ffast-math` 编译时，编译器会假设没有 NaN 和无穷，`std::isnan(x)` 可能被直接折叠成 `false`，但 `numeric_limits<double>::is_iec559` 依然是 `true`。那已经是在标准之外了。

### 溢出与陷阱：`is_modulo`、`traps`、`tinyness_before`（¶57–¶63）

- `is_modulo`（¶57）：对 `+`、`-`、`*` 来说，若真实结果超出 `[min(), max()]`，返回值与真实值相差 `max() - min() + 1` 的整数倍——即**回绕**。无符号类型为 `true`（[[basic.fundamental]] 规定无符号运算按模 2ⁿ）。例 1（¶58）：**有符号整数类型为 `false`**，除非实现作为扩展把有符号溢出定义为回绕。有符号溢出在核心语言中是 UB（[[expr.pre]]），`is_modulo == false` 只是在库里如实反映这一点。
- `traps`（¶60）：程序开始时，存在某个值会使使用它的算术运算**陷入**（trap）。整数类型上最典型的例子是除以零引发硬件异常。
- `tinyness_before`（¶62）：在舍入**之前**检测下溢（tininess）。IEEE 754 允许两种检测时机，由硬件决定。

!!! impl "libc++ 的 `traps` 与 `tinyness_before`"
    libc++ 对整数类型的 `traps` 按目标平台给值：在 x86（`__i386__`/`__x86_64__`）和 WebAssembly 上，对不发生整型提升的类型（`int` 及以上）为 `true`，因为这些平台上整数除以零会触发 SIGFPE；在其他平台（例如 AArch64，整数除以零结果为 0 而不陷入）为 `false`。浮点类型的 `tinyness_before` 在 ARM/AArch64 上为 `true`，其他平台为 `false`——这是 IEEE 754 留给硬件的选择。

    这些都是 "property of the implementation"，在 Apple Silicon 上：`numeric_limits<int>::traps == false`，`numeric_limits<double>::tinyness_before == true`；在 x86-64 Linux 上两者恰好相反。

### `round_style`（¶64–¶65）

类型的舍入方式（脚注 164：等价于 `FLT_ROUNDS`）。整数类型的特化必须给 `round_toward_zero`（整数除法向零截断，[[expr.mul]]）。

## 特化（[numeric.special]）

¶1：所有特化都必须提供所有成员；"无意义"的值置 0 或 `false`（例如整数类型的 `epsilon()` 为 0）。¶2 给出了 `float` 特化的一个**示例**（非规范性）：`digits = 24`、`epsilon() = 1.19209290E-07F` 等，其中 `traps = true` 只是示例中的选择，并不是要求。

¶3 是规范性的：`numeric_limits<bool>` **必须**完全按给出的定义提供。几个有意思的值：`digits = 1`、`digits10 = 0`（一位二进制连一位十进制都不能无损表示）、`is_signed = false`、`is_integer = true`、`is_modulo = false`（`bool` 不回绕：`true + true` 先提升为 `int` 得到 2，再转回 `bool` 是 `true`）。

!!! impl "`__int128` 也有特化"
    libc++ 对 `__int128` 和 `unsigned __int128` 提供 `numeric_limits` 特化（`is_specialized == true`）。按标准，Clang/GCC 的 `__int128` 不是"扩展整数类型"——实现没有这么文档化，因为把它算作扩展整数类型会迫使 `intmax_t` 变宽，破坏 ABI。所以这个特化是一个扩展。

## `<climits>` 与 `<cfloat>`（[climits.syn]、[cfloat.syn]）

两个头文件都是 freestanding 的，宏的定义与 C 的 `<limits.h>`、`<float.h>` 相同，例外是 `<climits>` **不定义 `BITINT_MAXWIDTH`**（C23 的 `_BitInt` 在 C++ 中不存在）。

`<climits>` 里有 C23 新增的 `*_WIDTH` 宏（`INT_WIDTH`、`LONG_WIDTH`、`BOOL_WIDTH`……），对应 [[basic.fundamental]] 中的**宽度**（[[g:integer-width]]）。`<cfloat>` 里有 C23 新增的 `FLT_SNAN`、`INFINITY`、`NAN`、`FLT_TRUE_MIN`（即 `denorm_min()`）以及 `__STDC_VERSION_FLOAT_H__`。

[climits.syn] 注 1 指出一个细节：除了 `*_WIDTH`、`CHAR_BIT` 和 `MB_LEN_MAX` 之外，指代整数类型 `T` 的宏定义的常量，其类型是 `T` 的**提升后类型**（[[conv.prom]]）。所以 `SHRT_MAX` 的类型是 `int`，`UCHAR_MAX` 的类型也是 `int`（而不是 `unsigned char`）：

```cpp run title="climits-type.cpp" ok
#include <climits>
#include <type_traits>

static_assert(std::is_same_v<decltype(SHRT_MAX), int>);
static_assert(std::is_same_v<decltype(UCHAR_MAX), int>);
static_assert(std::is_same_v<decltype(UINT_MAX), unsigned>);
static_assert(std::is_same_v<decltype(LONG_MAX), long>);

int main() {}
```

!!! pitfall "`INT_MIN` 为什么不写成 `-2147483648`"
    在 32 位 `int` 上，`-2147483648` 不是一个字面量，而是对字面量 `2147483648` 应用一元负号。`2147483648` 装不下 `int`，按 [[lex.icon]] 它的类型是 `long`（LP64）或 `long long`——于是整个表达式类型不是 `int`。实现通常把 `INT_MIN` 定义为 `(-2147483647 - 1)` 或 `(-INT_MAX - 1)` 来得到类型正确的值。

`<climits>`/`<cfloat>` 相对 `numeric_limits` 的唯一优势是**可以在预处理指令里用**：`#if INT_MAX > 0x7FFF`。在模板和 `constexpr` 代码里，`numeric_limits` 更好。

| `numeric_limits` 成员 | 对应 C 宏（脚注 150–164） |
|---|---|
| `min()` | `INT_MIN`、`FLT_MIN`、`DBL_MIN`…… |
| `max()` | `INT_MAX`、`FLT_MAX`、`DBL_MAX`…… |
| `digits`（浮点） | `FLT_MANT_DIG`、`DBL_MANT_DIG`、`LDBL_MANT_DIG` |
| `digits10`（浮点） | `FLT_DIG`、`DBL_DIG`、`LDBL_DIG` |
| `max_digits10` | `FLT_DECIMAL_DIG`、`DBL_DECIMAL_DIG`（C11 引入，标准未写入脚注） |
| `radix` | `FLT_RADIX` |
| `epsilon()` | `FLT_EPSILON`、`DBL_EPSILON`、`LDBL_EPSILON` |
| `min_exponent` / `max_exponent` | `*_MIN_EXP` / `*_MAX_EXP` |
| `min_exponent10` / `max_exponent10` | `*_MIN_10_EXP` / `*_MAX_10_EXP` |
| `round_style` | `FLT_ROUNDS` |

## 思考题

!!! question "思考题"
    1. `std::numeric_limits<long double>::digits` 在 Apple Silicon 上是多少？在 x86-64 Linux 上呢？这对 [[basic.fundamental]] 的哪句话构成了例证？
    2. `std::numeric_limits<int&>::max()` 能编译吗？
    3. 有人写 `if (std::abs(a - b) < std::numeric_limits<double>::epsilon())` 来比较两个浮点数是否"相等"。这有什么问题？

<details markdown="1">
<summary>展开查看答案与解析</summary>

1. Apple Silicon 上 `long double` 与 `double` 相同，`digits == 53`；x86-64 Linux 上是 x87 80 位扩展精度，`digits == 64`。[[basic.fundamental]] 只要求 `long double` 提供至少与 `double` 一样的精度，其值表示由实现定义。
2. 不能。`int&` 没有特化，落到主模板；主模板的 `max()` 声明为返回 `T` 并 `return T();`，而 `T()` 对引用类型是非良构的（无法值初始化一个引用）。由于类模板的成员函数定义只在使用时实例化，仅仅写 `numeric_limits<int&>` 不出错，调用 `max()` 才出错。
3. `epsilon()` 是 1 附近相邻 `double` 之间的距离（¶25）。对于量级远大于 1 的数，相邻值之差远大于 `epsilon()`，这个条件退化为"严格相等"；对于量级远小于 1 的数，它又过于宽松。正确的容差应当按量级缩放，或者用 ULP 距离。
</details>

## 小结

!!! summary
    - `<version>`：`__cpp_lib_*` 宏，值为 `yyyymmL`，用 `>=` 比较；必须先包含 `<version>` 或对应头文件；加固宏只在加固实现中定义。
    - `numeric_limits` 主模板对任何类型都能实例化，成员一律为 0/`false`/`T()`——先查 `is_specialized`。
    - 每个算术类型（含 `bool`、扩展类型）都有特化；cv 限定版本与非限定版本值相同；非算术标准类型（如 `complex`）不得特化。
    - 浮点 `min()` 是最小正规格化数，最负值请用 `lowest()`。
    - `digits10`：十进制写进去不丢；`max_digits10`：二进制打出来不丢。
    - `is_modulo`：无符号为真，有符号为假（溢出是 UB）；`traps`、`tinyness_before` 依平台而定。
    - `has_denorm`/`has_denorm_loss` 已弃用并移入附录 D。
    - `<climits>` 宏的类型是提升后类型；它们能在 `#if` 中使用，这是相对 `numeric_limits` 唯一的优势。
