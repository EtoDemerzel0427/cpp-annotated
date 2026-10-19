---
title: gcd、lcm、midpoint 与饱和算术
summary: <numeric> 中处理单个数值的工具，主题都是整数溢出：gcd、lcm 要求结果可表示，否则是未定义行为；midpoint 保证不溢出，整数结果向第一个实参取整；C++26 的饱和算术先按数学值计算，超出范围时取最接近的极值。
status: done
covers: numeric.sat.func, numeric.sat.cast, numeric.ops.gcd, numeric.ops.lcm, numeric.ops.midpoint
papers: P0295R0, P0811R3, P0543R3
related: numeric.ops, basic.fundamental, expr.const.core, numerics.c.ckdint, utility.intcmp
tags: 标准库, numeric, gcd, midpoint, 饱和算术, 整数溢出
updated: 2026-10-19
---

!!! tldr
    - `gcd`、`lcm` 只接受整数类型（不含 `bool`），结果总是非负；|m|、|n| 和 `lcm` 的结果都必须能用公共类型表示，否则是未定义行为，例如 `gcd(INT_MIN, 0)`。
    - `midpoint(a, b)` 保证不溢出；整数版本在和为奇数时向 `a` 取整，所以 `midpoint(1, 4) == 2` 而 `midpoint(4, 1) == 3`。
    - C++26 的 `saturating_add` 等先按无限精度计算，结果超出范围时返回最接近的最大值或最小值，不做整型提升。
    - 饱和函数只接受有符号和无符号整数类型，`char`、`bool` 等字符类型不行。
    - `saturating_div` 除以零是未定义行为，但在常量求值中会被诊断。

三组函数都在处理整数溢出，只是方式不同：`gcd`、`lcm` 把避免溢出的责任交给调用者，`midpoint` 保证内部不会溢出，饱和算术把溢出的结果钳制到类型的边界上。

## `gcd` 与 `lcm`（[numeric.ops.gcd]、[numeric.ops.lcm]）{{c++17}}

```cpp
template<class M, class N>
  constexpr common_type_t<M, N> gcd(M m, N n);
template<class M, class N>
  constexpr common_type_t<M, N> lcm(M m, N n);
```

两个函数由 [[P0295R0]] 引入，返回类型是两个实参类型的公共类型。

[numeric.ops.gcd] ¶1 *Mandates* 要求 `M` 和 `N` 都是整数类型，而且不是 `bool`（含 cv 限定）。传入 `double` 会编译失败。

¶2 前置条件是 |m| 和 |n| 都能表示为 `common_type_t<M, N>` 的值。注 1 解释了这样要求的原因：保证 `gcd(m, m)`，即 |m|，一定能表示。¶3 两者都为零时返回零，否则返回 |m| 与 |n| 的最大公约数，所以结果总是非负。

违反前置条件的典型例子是 `gcd(INT_MIN, 0)`：|INT_MIN| 无法用 `int` 表示。本机 libc++ 在 `-fsanitize=undefined` 下报告 `negation of -2147483648 cannot be represented in type 'int'`。

[numeric.ops.lcm] 有相同的 *Mandates*。¶2 的前置条件多了一条：最小公倍数本身也必须能用公共类型表示。所以 `lcm(65536, 65537)` 对 `int` 是 {{ub}}，本机 libc++ 不报任何错误，返回了 `65536`。¶3 任一实参为零时返回零。

## `midpoint`（[numeric.ops.midpoint]）{{c++20}}

`midpoint` 由 [[P0811R3]] 引入，同一个提案还加入了 `<cmath>` 的 `lerp`。

### 算术版本（¶1–¶3）

```cpp
template<class T> constexpr T midpoint(T a, T b) noexcept;
```

¶1 `T` 必须是除 `bool` 以外的算术类型。¶2 返回 `a` 与 `b` 之和的一半；`T` 是整数类型且和为奇数时，结果向 `a` 取整。¶3 计算过程中不会溢出；对浮点类型，至多发生一次不精确的运算。

不溢出很有用。朴素的 `(a + b) / 2` 对 `int` 会溢出，是 {{ub}}；`a + (b - a) / 2` 在 `a`、`b` 异号时同样可能溢出。实现（包括 libc++）在内部借助无符号运算避开这两种情况。

向 `a` 取整，而不是向零或向下取整，使得 `midpoint` 不对称：`midpoint(1, 4) == 2`，`midpoint(4, 1) == 3`，`midpoint(-3, 0) == -2`。二分查找可以利用这一点：`midpoint(lo, hi)` 偏向 `lo`，`midpoint(hi, lo)` 偏向 `hi`。

### 指针版本（¶4–¶7）

```cpp
template<class T> constexpr T* midpoint(T* a, T* b);
```

¶4 `T` 必须是对象类型，¶5 而且是完整类型。¶6 前置条件是 `a`、`b` 分别指向同一个数组对象的第 i 和第 j 个元素。注 1 说明，不是数组元素的对象视为只有一个元素的数组，尾后指针视为指向假想的第 n 个元素（[[basic.compound]]）。

¶7 返回指向第 i + (j − i)/2 个元素的指针，除法向零截断。写法与算术版本不同，效果同样是偏向 `a`。指针版本没有 `noexcept`；指向不同数组的两个指针违反前置条件，是 {{ub}}。

```cpp run title="midpoint_gcd.cpp" ok
#include <cassert>
#include <climits>
#include <numeric>

int main() {
    assert(std::midpoint(INT_MAX, INT_MAX - 2) == INT_MAX - 1); // 不溢出
    assert(std::midpoint(1, 4) == 2);       // 向 a 取整
    assert(std::midpoint(4, 1) == 3);
    assert(std::midpoint(-3, 0) == -2);     // 向 a，不是向零
    int arr[5] = {};
    assert(std::midpoint(arr, arr + 5) == arr + 2);
    assert(std::midpoint(arr + 5, arr) == arr + 3); // 5 + (-5)/2 = 3
    assert(std::midpoint(1e308, 1e308) == 1e308);   // 浮点也不溢出

    assert(std::gcd(-12, 18) == 6);         // 结果非负
    assert(std::lcm(4, -6) == 12);
    assert(std::gcd(0, 0) == 0 && std::lcm(0, 5) == 0);
    static_assert(std::gcd(12u, 18L) == 6); // common_type_t<unsigned, long>
}
```

## 饱和算术（[numeric.sat]）{{c++26}}

```cpp
template<class T> constexpr T saturating_add(T x, T y) noexcept;
template<class T> constexpr T saturating_sub(T x, T y) noexcept;
template<class T> constexpr T saturating_mul(T x, T y) noexcept;
template<class T> constexpr T saturating_div(T x, T y) noexcept;
template<class R, class T> constexpr R saturating_cast(T x) noexcept;
```

这组函数来自 [[P0543R3]]，提案里的名字是 `add_sat`、`sub_sat`、`mul_sat`、`div_sat`、`saturate_cast`，当前草案中已经改成上面的名字。本机 libc++ 提供的是新名字，`__cpp_lib_saturation_arithmetic` 为 `202603L`。

```cpp run title="saturating.cpp" ok
#include <climits>
#include <cstdint>
#include <numeric>

using std::int8_t, std::int16_t, std::uint8_t;
static_assert(std::saturating_add<int8_t>(100, 100) == 127);
static_assert(std::saturating_sub(0u, 1u) == 0u);  // 无符号不再回绕
static_assert(std::saturating_mul<int16_t>(-300, 300) == INT16_MIN);
static_assert(std::saturating_div(INT_MIN, -1) == INT_MAX);
static_assert(std::saturating_cast<uint8_t>(-5) == 0);
static_assert(std::saturating_cast<int8_t>(1000) == 127);

int main() {}
```

### 先按数学值计算，再钳制（¶1–¶7）

!!! std
    In the following descriptions, an arithmetic operation is performed as a mathematical operation with infinite range and then it is determined whether the mathematical result fits into the result type.

¶1 每个运算都先按无限范围的数学运算求值，再看结果能否放进结果类型。¶3、¶5、¶7 规定：能表示时返回这个结果；否则返回 `T` 的最大值和最小值中更接近数学结果的那个。

这里没有整型提升。`saturating_add<int8_t>(100, 100)` 的结果是 127，而不是先提升成 `int` 得到 200。两个形参的类型相同，所以 `x` 是 `int8_t` 时，`saturating_add(x, 1)` 推导冲突，要写成 `saturating_add<int8_t>(x, 1)`。

¶2 等各段的 *Constraints* 要求 `T` 是**有符号或无符号整数类型**（[[basic.fundamental]]）。这个术语不包括 `bool`、`char`、`wchar_t`、`char8_t`、`char16_t`、`char32_t`：它们是整型（integral type），但不属于有符号或无符号整数类型。所以 `saturating_add('a', 'b')` 找不到可用的重载，编译失败。

### `saturating_div`（¶8–¶11）

¶9 前置条件是 `y != 0`。¶10 唯一可能溢出的情形是有符号类型的 `numeric_limits<T>::min() / -1`，此时返回 `max()`。

¶11 规定，违反前置条件的调用不是核心常量表达式（[[expr.const.core]]）。所以在常量求值中除以零必须被诊断：

```cpp run title="saturating_div0.cpp" error
#include <numeric>
// error: 违反前置条件的调用不是核心常量表达式
constexpr int x = std::saturating_div(1, 0);
int main() {}
```

在运行时除以零仍是 {{ub}}。

### `saturating_cast`（[numeric.sat.cast]）

¶1 `R` 和 `T` 都必须是有符号或无符号整数类型。¶2 `x` 能表示为 `R` 时返回它，否则返回 `R` 中最接近的极值。

`static_cast` 转换到较窄的无符号类型时按模 2ⁿ 回绕，`saturating_cast` 则钳制到边界：`saturating_cast<uint8_t>(-5) == 0`，`saturating_cast<int8_t>(1000) == 127`。比较大小时它要正确处理有符号与无符号的混合，libc++ 内部用的是 `cmp_less`、`cmp_greater`（[[utility.intcmp]]）。

!!! note "与 `<stdckdint.h>` 的分工"
    C23 的 `ckd_add` 等函数（[[numerics.c.ckdint]]）报告是否溢出，同时给出回绕后的结果。饱和算术不报告溢出，直接钳制。前者适合溢出就是错误的场合，后者适合信号处理、像素运算等溢出时取边界值即可的场合。

## 思考题

!!! question "思考题 1"
    二分查找写成 `while (lo < hi) { auto mid = std::midpoint(lo, hi); ... }`，取整方向会不会导致死循环？

<details markdown="1">
<summary>答案</summary>

`lo < hi` 时，`midpoint(lo, hi)` 向 `lo` 取整，`mid` 落在 `[lo, hi)` 中。如果更新方式是 `lo = mid + 1` 或 `hi = mid`，区间每次都严格缩小，不会死循环。

如果更新方式是 `lo = mid` 或 `hi = mid - 1`（找最后一个满足条件的位置），就需要偏向 `hi` 的中点，应写 `std::midpoint(hi, lo)`。否则 `hi == lo + 1` 时 `mid == lo`，`lo = mid` 不改变区间，循环不会结束。
</details>

!!! question "思考题 2"
    `std::gcd(-5, 10u)` 的类型和值是什么？有没有未定义行为？

<details markdown="1">
<summary>答案</summary>

`common_type_t<int, unsigned>` 是 `unsigned`。前置条件要求 |−5| = 5 和 10 能表示为 `unsigned`，满足，所以没有未定义行为，结果是 `5u`。

标准讨论的是数学值 |m| 能否表示，而不是先把 −5 转换成 `unsigned`（那会得到 4294967291）。实现必须先取绝对值再转换。
</details>

## 小结

| 函数 | 类型要求 | 前置条件 | 溢出时 |
|---|---|---|---|
| `gcd`、`lcm` | 整数类型，非 `bool`（*Mandates*） | \|m\|、\|n\| 以及 `lcm` 的结果可表示 | 违反前置条件，UB |
| `midpoint`（算术） | 算术类型，非 `bool`（*Constraints*） | 无 | 保证不溢出；整数向 `a` 取整 |
| `midpoint`（指针） | 完整的对象类型 | 指向同一数组 | 不适用 |
| `saturating_add`、`_sub`、`_mul` | 有符号或无符号整数类型 | 无 | 钳制到最接近的极值 |
| `saturating_div` | 同上 | `y != 0`，常量求值中会被诊断 | `min / -1` 返回 `max` |
| `saturating_cast` | 同上 | 无 | 钳制 |
