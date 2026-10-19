---
title: 实现属性
summary: 在编译期查询实现的性质：numeric_limits 各成员的确切含义，<climits> 与 <cfloat> 的 C 宏，以及 <version> 中的库特性测试宏。
status: done
covers: *
papers: P2614R2
related: support, basic.fundamental, conv.prom, conv.rank, cpp.predefined, expr.pre, support.types, support.arith.types, basic.extended.fp
tags: 标准库, numeric_limits, 特性测试宏, climits, cfloat
updated: 2026-10-19
---

!!! tldr
    - 浮点类型的 `numeric_limits<T>::min()` 是最小的正规格化正数，不是最负的值；最负的有限值要用 `lowest()`。
    - 对没有特化的类型，`numeric_limits` 不报错，所有成员都是 0 或 `false`。泛型代码要先检查 `is_specialized`。
    - `digits10` 是十进制写进去再读出来不丢失的位数，`max_digits10` 是二进制值打印出来再读回去不丢失所需的位数。
    - `<climits>` 中 `SHRT_MAX`、`UCHAR_MAX` 的类型是提升后的 `int`；这些宏能用在 `#if` 里，这是它们相对 `numeric_limits` 的主要优势。
    - `__cpp_lib_*` 宏由库定义，检查之前要先包含 `<version>` 或对应的头文件，并且用 `>=` 比较。

[[basic.fundamental]] 把很多性质留给实现决定：`int` 有多宽，`char` 是否有符号，`long double` 用什么格式。¶1（[support.limits.general]）`<limits>`、`<climits>`、`<cfloat>` 让程序在编译期查询这些性质；`<version>` 则报告标准库本身实现了哪些特性。

## `min()` 不是最小值

```cpp run title="min-vs-lowest.cpp" ok
#include <algorithm>
#include <limits>
#include <vector>

double max_of(const std::vector<double>& v) {
    // 错误：min() 是一个很小的正数
    // double m = std::numeric_limits<double>::min();
    double m = std::numeric_limits<double>::lowest();
    for (double x : v) m = std::max(m, x);
    return m;
}

int main() { return max_of({-3.0, -1.5, -7.0}) == -1.5 ? 0 : 1; }
```

如果用 `min()` 作初值，全是负数的输入会得到一个约为 2.2e-308 的正数。整数和浮点在这里的语义不一致：

| 成员 | 整数类型 | 浮点类型 |
|---|---|---|
| `min()` | 最小值，如 `INT_MIN` | 最小的正规格化正数，如 `DBL_MIN` |
| `max()` | 最大值 | 最大的有限值 |
| `lowest()` | 同 `min()` | 最负的有限值，通常是 `-max()` |

[numeric.limits.members] ¶2–¶3 规定 `min()` 是最小的有限值，但对有次正规数（subnormal，比最小规格化数更接近 0 的那些值）的浮点类型，它返回最小的正规格化正数。脚注 150 说明它等价于 C 的 `FLT_MIN`、`DBL_MIN`，这个不一致是从 C 继承来的。

¶7 的 `lowest()` 是 C++11 加入的：一个有限值 x，不存在比它更小的有限值。脚注 152 解释了为什么不直接写成 `-max()`：并非所有浮点表示的最负值都恰好等于最大值取负。

## `numeric_limits` 的总体规则（[numeric.limits.general]）

主模板为每个成员提供了默认值：

```cpp
template<class T> class numeric_limits {
public:
  static constexpr bool is_specialized = false;
  static constexpr T min() noexcept { return T(); }
  static constexpr T max() noexcept { return T(); }
  static constexpr int  digits = 0;
  // …… 其余成员同样是 0、false 或 T()
};
```

¶3 主模板的数据成员和成员函数的返回值都是值初始化的。注 1 指出，这意味着对一个没有特化的类型查询 `numeric_limits`，不会报错，只会得到 0 或 `false`。

```cpp run title="limits-primary.cpp" ok
#include <cstddef>
#include <limits>

template<class T>
constexpr T saturating_max() {
    static_assert(std::numeric_limits<T>::is_specialized,
                  "need numeric_limits<T>");
    return std::numeric_limits<T>::max();
}

static_assert(!std::numeric_limits<std::byte>::is_specialized);
static_assert(std::numeric_limits<std::byte>::max() == std::byte{0});
static_assert(std::numeric_limits<const volatile int>::max()
              == std::numeric_limits<int>::max());
// constexpr auto b = saturating_max<std::byte>();  // error: static_assert 失败

int main() { return saturating_max<unsigned char>() == 255 ? 0 : 1; }
```

`std::byte` 是枚举，不是算术类型，所以 `numeric_limits<std::byte>::max()` 悄悄返回 `byte{0}`。其他规则：

- ¶2 所有 `static constexpr` 成员都要能用在常量表达式中。
- ¶4 每个算术类型都必须有特化，`is_specialized` 为 `true`。这包括 `bool`，也包括扩展整数类型和扩展浮点类型（[[basic.extended.fp]]）。
- ¶5 *cv* `T` 的特化与 `T` 的成员值相同，上例的第三个 `static_assert` 验证了这一点。
- ¶6 非算术的标准类型，例如 `complex<T>`，不得有特化。

程序可以为自己定义的类型特化 `numeric_limits`：[[namespace.std]] 允许为依赖于程序定义类型的标准库类模板写特化。大整数库、定点数库通常都会这样做。

## 各成员的含义（[numeric.limits.members]）

¶1 本小节的每个成员函数都是信号安全的（[[support.signal]]），可以在信号处理函数中调用。

每个成员都注明了在什么条件下有意义（meaningful），比如 `epsilon()` 只对浮点类型有意义。[numeric.special] ¶1 规定所有特化都必须提供所有成员，无意义的值设为 0 或 `false`，所以整数类型的 `epsilon()` 是 0。

### 精度：`digits`、`digits10`、`max_digits10`（¶9–¶15）

- `digits`：能不加改变地表示的 `radix` 进制位数。对整数类型是除符号位以外的位数：`int` 为 31，`unsigned` 为 32，`bool` 为 1。对浮点类型是有效数字的位数，包括隐含的首位：`float` 为 24，`double` 为 53。
- `digits10`：能不加改变地表示的十进制位数，任何这么多位的十进制数都能存进去再原样取出。`int` 是 9：任何 9 位整数都放得下，但并非所有 10 位整数都放得下。`double` 是 15。
- `max_digits10`：保证不同的值打印出来也不同所需的十进制位数，只对浮点类型有意义（`float` 为 9，`double` 为 17）。把浮点数序列化成文本再解析回来、得到完全相同的值，需要这么多位。

```cpp run title="digits.cpp" ok
#include <limits>

using L = std::numeric_limits<double>;
static_assert(L::digits == 53 && L::digits10 == 15
              && L::max_digits10 == 17);
static_assert(std::numeric_limits<int>::digits == 31);
static_assert(std::numeric_limits<unsigned>::digits == 32);
static_assert(std::numeric_limits<bool>::digits == 1);
static_assert(std::numeric_limits<int>::digits10 == 9);

int main() {}
```

这个例子假定 `double` 是 IEEE 754 binary64、`int` 是 32 位。主流平台都是这样，但标准并不保证。

### 类型分类：`is_signed`、`is_integer`、`is_exact`、`radix`（¶16–¶24）

- `is_signed`、`is_integer` 顾名思义。`numeric_limits<char>::is_signed` 回答了 `char` 是否有符号这个由实现决定的问题：x86-64 Linux 和 Apple 平台上是 `true`，AArch64 Linux 上是 `false`。
- `is_exact`：使用精确表示。¶20 指出，整数类型都是精确的，但精确的不一定是整数，例如有理数和定点数表示。
- `radix`：浮点类型的指数基数，通常是 2；整数类型的表示基数。

### 浮点特性：`epsilon` 到 `max_exponent10`（¶25–¶35）

- `epsilon()`：1 与大于 1 的最小可表示值之差（`double` 为 2⁻⁵²）。它只是 1 附近相邻两个值的间距，在 1e10 附近，相邻两个 `double` 的差远大于 `epsilon()`。
- `round_error()`：最大舍入误差的度量。按就近舍入时通常为 0.5。
- `min_exponent`、`max_exponent`：使 radix 的 (e − 1) 次方仍是规格化数、有限数的最小、最大整数 e。`double` 的这两个值是 −1021 和 1024，而规格化数的指数范围是 [−1022, 1023]。减 1 是为了与 C 的 `DBL_MIN_EXP`、`DBL_MAX_EXP` 一致，C 把有效数字写成 0.1xxx 的形式。
- `min_exponent10`、`max_exponent10`：十进制的对应值。

### 无穷与 NaN（¶36–¶52）

- `has_infinity`、`has_quiet_NaN`、`has_signaling_NaN`：类型是否有这些特殊值。`is_iec559` 为 `true` 时它们都必须为 `true`。
- `infinity()`、`quiet_NaN()`、`signaling_NaN()`：对应的值，在相应的 `has_*` 为 `true` 时有意义。
- `denorm_min()`：最小的正次正规数；类型不支持次正规数时，返回最小的正规格化正数。

!!! note "`has_denorm` 去了哪里"
    C++23 之前还有 `has_denorm` 和 `has_denorm_loss` 两个成员。[[P2614R2]] 在 C++23 弃用了它们，现在它们在附录 [[depr.numeric.limits.has.denorm]]。是否支持次正规数常常可以在运行时切换（例如 x86 的 FTZ/DAZ 模式），编译期常量无法如实描述。

### IEEE 一致性与有界性（¶53–¶56）

- `is_iec559`：当且仅当类型遵循 ISO/IEC 60559（即 IEEE 754）时为 `true`。注 1 指出 `std::float16_t`、`float32_t`、`float64_t`、`float128_t` 若存在，都为 `true`。
- `is_bounded`：可表示的值是有限集合。注 2 指出所有基本类型都是有界的，只有任意精度类型才会是 `false`。

!!! lawyer "`is_iec559` 不保证优化器遵守 IEEE 语义"
    `is_iec559` 只说明类型的表示和运算遵循 IEEE 754。用 `-ffast-math` 编译时，编译器假设不存在 NaN 和无穷，`std::isnan(x)` 可能被直接折叠成 `false`，而 `numeric_limits<double>::is_iec559` 仍然是 `true`。这种编译选项已经不在标准的范围之内。

### 溢出与陷入：`is_modulo`、`traps`、`tinyness_before`（¶57–¶63）

¶57 如果 `+`、`-`、`*` 的真实结果超出 `[min(), max()]` 时，返回值与真实值相差 `max() - min() + 1` 的整数倍，这个类型就是模（modulo）类型，也就是溢出时回绕。无符号类型的 `is_modulo` 为 `true`，因为 [[basic.fundamental]] 规定无符号运算按模 2ⁿ 进行。

¶58 例 1 说明，有符号整数类型的 `is_modulo` 为 `false`，除非实现作为扩展把有符号溢出定义为回绕。有符号溢出在核心语言中是未定义行为（[[expr.pre]]），这里只是如实反映。

¶60 `traps`：程序开始时存在某个值，用它做算术运算会陷入（trap，触发硬件异常）。整数类型上最典型的例子是除以零。¶62 `tinyness_before`：在舍入之前检测下溢。IEEE 754 允许两种检测时机，由硬件决定。

!!! impl "libc++ 中 `traps` 与 `tinyness_before` 的取值"
    libc++ 对整数类型的 `traps` 按目标平台取值：在 x86 和 WebAssembly 上，对不会被整型提升的类型（`int` 及更宽的类型）为 `true`，因为这些平台上整数除以零会引发 SIGFPE；在 AArch64 等平台上为 `false`，那里整数除以零的结果是 0。浮点类型的 `tinyness_before` 在 ARM 和 AArch64 上为 `true`，其他平台为 `false`。所以本机 Apple Silicon 上 `numeric_limits<int>::traps` 为 `false`、`numeric_limits<double>::tinyness_before` 为 `true`，x86-64 Linux 上两者恰好相反。

### `round_style`（¶64–¶65）

类型的舍入方式，类型是枚举 `float_round_style`（[round.style]），对应 C 的 `FLT_ROUNDS`（脚注 164）。整数类型的特化必须是 `round_toward_zero`，因为整数除法向零截断（[[expr.mul]]）。

| 枚举项 | 值 | 含义 |
|---|---|---|
| `round_indeterminate` | −1 | 无法确定 |
| `round_toward_zero` | 0 | 向零舍入 |
| `round_to_nearest` | 1 | 舍入到最近的可表示值 |
| `round_toward_infinity` | 2 | 向正无穷舍入 |
| `round_toward_neg_infinity` | 3 | 向负无穷舍入 |

`round_style` 是编译期常量，描述的是默认的舍入方式。程序在运行时用 `<cfenv>` 的 `fesetround` 改变舍入方向后，它不会跟着变。

## 标准规定的特化（[numeric.special]）

¶2 给出了一个 `float` 特化的示例，例如 `digits = 24`、`epsilon() = 1.19209290E-07F`。这只是示例，不是要求。

¶3 是规范性的：`numeric_limits<bool>` 必须完全按给出的定义提供。其中 `digits = 1`，`digits10 = 0`（一位二进制连一位十进制都表示不了），`is_modulo = false`。`bool` 不回绕：`true + true` 先提升为 `int` 得到 2，再转回 `bool` 仍是 `true`。

!!! impl "`__int128` 也有特化"
    libc++ 为 `__int128` 和 `unsigned __int128` 提供了 `numeric_limits` 特化。GCC 和 Clang 并没有把 `__int128` 文档化为标准意义上的扩展整数类型，所以这个特化是一项扩展。过去的一个障碍是 `intmax_t` 必须能表示所有扩展整数类型的值，加入 128 位类型就要加宽 `intmax_t` 而破坏 ABI；当前草案已经放宽了这条要求（[[support.arith.types]]）。

## `<climits>` 与 `<cfloat>`（[climits.syn]、[cfloat.syn]）

两个头文件都要求独立实现也提供，宏的定义与 C 的 `<limits.h>`、`<float.h>` 相同。唯一的例外是 `<climits>` 不定义 C23 的 `BITINT_MAXWIDTH`，因为 C++ 没有 `_BitInt`。

[climits.syn] 注 1 指出，除了 `*_WIDTH`、`CHAR_BIT` 和 `MB_LEN_MAX`，描述整数类型 `T` 的宏，其类型是 `T` 提升后的类型（[[conv.prom]]）。所以 `SHRT_MAX` 和 `UCHAR_MAX` 的类型都是 `int`：

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
    在 32 位 `int` 上，`-2147483648` 不是一个字面量，而是对字面量 `2147483648` 取负。`2147483648` 超出了 `int` 的范围，按 [[lex.icon]] 它的类型是 `long` 或 `long long`，整个表达式的类型也就不是 `int`。实现通常把 `INT_MIN` 定义为 `(-INT_MAX - 1)`。

C23 给 `<climits>` 加了 `INT_WIDTH`、`LONG_WIDTH` 等宽度宏，给 `<cfloat>` 加了 `FLT_TRUE_MIN`（即 `denorm_min()`）、`INFINITY`、`NAN` 等。这些宏可以用在 `#if INT_MAX > 0x7FFF` 这样的预处理条件里；在模板和 `constexpr` 代码中，`numeric_limits` 更好用。

| `numeric_limits` 成员 | 对应的 C 宏 |
|---|---|
| `min()`、`max()` | `INT_MIN`、`INT_MAX`、`DBL_MIN`、`DBL_MAX` 等 |
| `digits`（浮点） | `FLT_MANT_DIG`、`DBL_MANT_DIG`、`LDBL_MANT_DIG` |
| `digits10`（浮点） | `FLT_DIG`、`DBL_DIG`、`LDBL_DIG` |
| `max_digits10` | `FLT_DECIMAL_DIG`、`DBL_DECIMAL_DIG` |
| `radix` | `FLT_RADIX` |
| `epsilon()` | `FLT_EPSILON`、`DBL_EPSILON`、`LDBL_EPSILON` |
| `min_exponent`、`max_exponent` | `DBL_MIN_EXP`、`DBL_MAX_EXP` 等 |
| `min_exponent10`、`max_exponent10` | `DBL_MIN_10_EXP`、`DBL_MAX_10_EXP` 等 |
| `round_style` | `FLT_ROUNDS` |

## 库特性测试宏（[version.syn]）

¶1 `<version>` 提供关于标准库实现的信息，主体是三百多个 `__cpp_lib_*` 宏。¶2 每个宏除了在 `<version>` 中定义，还在 synopsis 注释所列的头文件中定义，例如 `__cpp_lib_three_way_comparison` 也在 `<compare>` 中定义。

宏的值是 `yyyymmL` 形式的整数，大致对应该特性进入工作草案的年月。注 1 提醒，特性被扩充时，以后的标准可能把值改大，所以要用 `>=` 比较：

```cpp run title="feature-test.cpp" ok
#include <version>

#if defined(__cpp_lib_three_way_comparison) \
    && __cpp_lib_three_way_comparison >= 201907L
#  include <compare>
constexpr bool has_spaceship_lib = true;
#else
constexpr bool has_spaceship_lib = false;
#endif

int main() { return has_spaceship_lib ? 0 : 1; }
```

语言特性测试宏（`__cpp_concepts` 等）由编译器预定义（[[cpp.predefined]]），不需要包含任何头文件。`__cpp_lib_*` 由库定义，所以一定要先包含 `<version>` 或对应的头文件，否则检查的结果永远是未定义。

几个宏有特殊规定：

- ¶3 一组 `__cpp_lib_hardened_*` 宏（如 `__cpp_lib_hardened_vector`）只在加固实现（[[g:hardened-implementation]]）中定义。¶7 建议非加固实现不要定义它们。
- ¶4 所有可替换全局分配函数的默认版本都满足宿主实现的要求时，`__cpp_lib_freestanding_operator_new` 为 `202306L`，否则为 0（[[new.delete]]）。这让独立实现可以只提供一个总是失败的 `operator new`。
- ¶5 契约违反处理函数可替换时，`__cpp_lib_replaceable_contract_violation_handler` 为 `202603L`，否则为 0（[[basic.contract.handler]]）。
- ¶6 建议独立实现只在完整提供某项设施时才定义对应的宏。

## 思考题

!!! question "思考题"
    1. `std::numeric_limits<long double>::digits` 在 Apple Silicon 上是多少？在 x86-64 Linux 上呢？
    2. `std::numeric_limits<int&>::max()` 能编译吗？
    3. 有人写 `if (std::abs(a - b) < std::numeric_limits<double>::epsilon())` 来判断两个浮点数是否相等。这有什么问题？

<details markdown="1">
<summary>答案</summary>

1. Apple Silicon 上 `long double` 与 `double` 相同，`digits` 是 53；x86-64 Linux 上 `long double` 是 x87 的 80 位扩展精度，`digits` 是 64。[[basic.fundamental]] 只要求 `long double` 的精度不低于 `double`，具体格式由实现决定。
2. 不能。`int&` 没有特化，使用主模板，而主模板的 `max()` 写的是 `return T();`，引用类型不能值初始化。类模板的成员函数只在被使用时才实例化，所以只写 `numeric_limits<int&>` 不会出错，调用 `max()` 才出错。本机 Clang 23 报告 reference to type 'int' requires an initializer。
3. `epsilon()` 是 1 附近相邻两个 `double` 的间距（¶25）。对于远大于 1 的数，相邻值的差远大于 `epsilon()`，这个条件实际上退化为严格相等；对于远小于 1 的数，它又过于宽松。容差应该按数值的量级缩放，或者改用 ULP 距离比较。
</details>
