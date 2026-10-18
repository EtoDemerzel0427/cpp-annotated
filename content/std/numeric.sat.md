---
title: gcd、lcm、midpoint 与饱和算术
summary: <numeric> 中的标量工具——gcd/lcm 的 Mandates（整数类型且非 bool）与 |m|、|n| 可表示的前置条件；midpoint 的“不溢出、整数向 a 取整、浮点至多一次不精确运算”与指针版本；C++26 饱和算术 saturating_add/sub/mul/div/cast 的“无限精度再夹紧”语义、对字符类型和 bool 的排除、saturating_div 除零在常量求值中被诊断
status: done
covers: numeric.sat.func, numeric.sat.cast, numeric.ops.gcd, numeric.ops.lcm, numeric.ops.midpoint
papers: P0295R0, P0811R3, P0543R3
related: numeric.ops, basic.fundamental, expr.const.core, numerics.c.ckdint, utility.intcmp
tags: 标准库, numeric, gcd, midpoint, 饱和算术, 整数溢出
updated: 2026-10-18
---

[numeric.ops] 的最后几节不是序列算法，而是**标量**数值工具。它们的共同主题是**整数溢出**：`gcd`/`lcm` 用前置条件把溢出推给调用者，`midpoint` 承诺内部绝不溢出，饱和算术则把溢出变成确定的夹紧结果。

## `gcd`（[numeric.ops.gcd]）{{c++17}}

```cpp
template<class M, class N>
  constexpr common_type_t<M, N> gcd(M m, N n);
```

由 [[P0295R0]] 引入。

- ¶1 *Mandates*：`M`、`N` 都是**整数类型且不是 cv `bool`**——传 `double` 是编译错误；
- ¶2 *Preconditions*：|m| 和 |n| 可以表示为 `common_type_t<M, N>` 的值。注 1：这保证了诸如 `gcd(m, m) = |m|` 可表示；
- ¶3 *Returns*：两者都为零时返回零，否则返回 |m| 与 |n| 的最大公约数——结果**总是非负**；
- ¶4 *Throws*：无。

前置条件的典型违反是 `gcd(INT_MIN, 0)`：|INT_MIN| 无法用 `int` 表示。本机 libc++ 在 `-fsanitize=undefined` 下报 `negation of -2147483648 cannot be represented in type 'int'`。

## `lcm`（[numeric.ops.lcm]）

- 同样的 *Mandates*；
- ¶2：除了 |m|、|n| 可表示外，**最小公倍数本身**也必须可表示为 `common_type_t<M, N>`——`lcm(65536, 65537)` 对 `int` 是 {{ub}}；
- ¶3：任一为零时返回零。

## `midpoint`（[numeric.ops.midpoint]）{{c++20}}

由 [[P0811R3]] 引入（同一提案还带来了 `<cmath>` 的 `lerp`）。

### 算术版本（¶1–¶3）

```cpp
template<class T> constexpr T midpoint(T a, T b) noexcept;
```

- ¶1 *Constraints*：`T` 是**除 cv `bool` 以外的算术类型**；
- ¶2 *Returns*：a 与 b 之和的一半；对整数类型且和为奇数时，**向 `a` 取整**；
- ¶3 *Remarks*：**不发生溢出**；对浮点类型，至多发生一次不精确运算。

“向 `a` 取整”而不是“向零/向下取整”，使得 `midpoint` 不对称：`midpoint(1, 4) == 2`，`midpoint(4, 1) == 3`。这个设计便于二分查找类算法：`midpoint(lo, hi)` 总是偏向 `lo`，`midpoint(hi, lo)` 总是偏向 `hi`，选择哪个取决于你希望区间如何收缩。

“不溢出”的价值在于：朴素的 `(a + b) / 2` 对 `int` 会溢出（{{ub}}），`a + (b - a) / 2` 在 `a`、`b` 异号时同样会溢出；典型实现（包括 libc++）在内部借助无符号运算规避这两种情况。

### 指针版本（¶4–¶7）

```cpp
template<class T> constexpr T* midpoint(T* a, T* b);
```

- ¶4 *Constraints*：`T` 是对象类型；¶5 *Mandates*：`T` 是完整类型；
- ¶6 *Preconditions*：`a`、`b` 分别指向**同一个数组对象**的元素 i 和 j（注 1：非数组对象视作单元素数组，尾后指针视作指向假想的第 n 个元素，见 [[basic.compound]]）；
- ¶7 *Returns*：指向元素 i + (j − i)/2 的指针，除法**向零截断**。

注意指针版的取整规则写法不同（i + (j − i)/2，向零截断），但效果同样是“偏向 `a`”。指针版没有 `noexcept`（前置条件可能被违反），不同数组的指针是 {{ub}}。

```cpp run title="midpoint_gcd.cpp" ok
#include <cassert>
#include <climits>
#include <numeric>

int main() {
    assert(std::midpoint(INT_MAX, INT_MAX - 2) == INT_MAX - 1);   // 不溢出
    assert(std::midpoint(1, 4) == 2 && std::midpoint(4, 1) == 3); // 向 a 取整
    assert(std::midpoint(-3, 0) == -2);                           // 向 a 取整，不是向零
    int arr[5] = {};
    assert(std::midpoint(arr, arr + 5) == arr + 2);
    assert(std::midpoint(arr + 5, arr) == arr + 3);               // 5 + (0-5)/2，向零截断为 5 - 2
    assert(std::midpoint(1e308, 1e308) == 1e308);                 // 浮点也不溢出

    assert(std::gcd(-12, 18) == 6 && std::lcm(4, -6) == 12);      // 结果非负
    assert(std::gcd(0, 0) == 0 && std::lcm(0, 5) == 0);
    static_assert(std::gcd(12u, 18L) == 6);                       // common_type_t<unsigned, long>
}
```

## 饱和算术（[numeric.sat]）{{c++26}}

由 [[P0543R3]] 引入，最初的名字是 `add_sat`、`sub_sat`、`mul_sat`、`div_sat`、`saturate_cast`；当前草案中已改名为：

```cpp
template<class T> constexpr T saturating_add(T x, T y) noexcept;
template<class T> constexpr T saturating_sub(T x, T y) noexcept;
template<class T> constexpr T saturating_mul(T x, T y) noexcept;
template<class T> constexpr T saturating_div(T x, T y) noexcept;
template<class R, class T> constexpr R saturating_cast(T x) noexcept;
```

（本机 libc++ 提供的就是 `saturating_*` 名称，`__cpp_lib_saturation_arithmetic` 为 `202603L`。）

### 语义：无限精度计算，再夹紧（[numeric.sat.func] ¶1）

!!! std
    In the following descriptions, an arithmetic operation is performed as a mathematical operation with infinite range and then it is determined whether the mathematical result fits into the result type.

¶3、¶5、¶7：若数学结果可表示为 `T`，返回它；否则返回 `T` 的最大值或最小值中**更接近**数学结果的那个。

几个要点：

- **没有整型提升**。`int8_t` 版本的 `saturating_add(int8_t(100), int8_t(100))` 结果是 127，而不是先提升为 `int` 得到 200；两个形参类型相同，所以 `saturating_add(x, 1)`（`x` 是 `int8_t`）会推导冲突，需要写 `saturating_add<int8_t>(x, 1)`。
- ¶2 等 *Constraints*：`T` 是**有符号或无符号整数类型**（[[basic.fundamental]]）。这个术语**不包括** `bool`、`char`、`wchar_t`、`char8_t`、`char16_t`、`char32_t`——它们是整型（integral）但不是“有符号/无符号整数类型”。所以 `saturating_add('a', 'b')` 不参与重载决议，编译失败。
- ¶8–¶11 `saturating_div`：前置条件 `y != 0`；唯一的“溢出”情形 `numeric_limits<T>::min() / -1` 返回 `max()`。¶11 *Remarks*：违反前置条件的调用**不是核心常量表达式**（[[expr.const.core]]）——于是 `constexpr int x = std::saturating_div(1, 0);` 必须被诊断。这是“在常量求值中把库 UB 变成编译错误”这一模式的又一个实例。

### `saturating_cast`（[numeric.sat.cast]）

¶1：`R` 和 `T` 都是有符号或无符号整数类型；¶2：`x` 可表示为 `R` 则返回它，否则返回 `R` 中最接近的极值。这比 `static_cast` 的模 2ⁿ 回绕更符合直觉：`saturating_cast<uint8_t>(-5) == 0`，`saturating_cast<int8_t>(1000) == 127`。比较时它正确处理有符号/无符号混合（libc++ 内部用 `cmp_less`/`cmp_greater`，见 [[utility.intcmp]]）。

```cpp run title="saturating.cpp" ok
#include <climits>
#include <cstdint>
#include <numeric>

static_assert(std::saturating_add<std::int8_t>(100, 100) == 127);
static_assert(std::saturating_sub(0u, 1u) == 0u);                  // 无符号不再回绕
static_assert(std::saturating_mul<std::int16_t>(-300, 300) == INT16_MIN);
static_assert(std::saturating_cast<std::uint8_t>(-5) == 0);
static_assert(std::saturating_cast<std::int8_t>(1000) == 127);
static_assert(std::saturating_div(INT_MIN, -1) == INT_MAX);

int main() {}
```

```cpp run title="saturating_div0.cpp" error
#include <numeric>
constexpr int x = std::saturating_div(1, 0);   // error: 违反前置条件的调用不是核心常量表达式
int main() {}
```

!!! note "与 `<stdckdint.h>` 的分工"
    C23 的 `ckd_add` 等（当前草案通过 `<stdckdint.h>` 提供，见 [[numerics.c.ckdint]]）**报告**是否溢出并给出回绕结果；饱和算术**不报告**，直接夹紧。前者适合“溢出即错误”的场景，后者适合信号处理、像素运算等“溢出就取极值”的场景。

## 思考题

<details markdown="1">
<summary>1. `std::midpoint(a, b)` 用于二分查找 `while (lo < hi) { auto mid = std::midpoint(lo, hi); ... }`，取整方向会造成死循环吗？</summary>

`midpoint(lo, hi)` 在 `lo < hi` 时向 `lo` 取整，即 `mid ∈ [lo, hi)`。若更新规则是 `lo = mid + 1` / `hi = mid`，区间每次严格缩小，不会死循环；若更新规则是 `lo = mid` / `hi = mid - 1`（找最后一个满足条件的位置），则需要偏向 `hi` 的中点，应写 `std::midpoint(hi, lo)`，否则 `hi == lo + 1` 时 `mid == lo` 导致死循环。
</details>

<details markdown="1">
<summary>2. `std::gcd(-5, 10u)` 的结果类型和值是什么？是否有 UB？</summary>

`common_type_t<int, unsigned>` 是 `unsigned`。前置条件要求 |−5| = 5 和 |10| = 10 可表示为 `unsigned`——满足。结果是 `5u`。注意标准是对**数学值** |m| 讨论可表示性，而不是把 −5 先转成 `unsigned`（那会得到 4294967291）；实现必须先取绝对值再转换。
</details>

## 小结

| 函数 | 约束/强制 | 前置条件 | 溢出处理 |
|---|---|---|---|
| `gcd` / `lcm` | 整数类型，非 `bool`（Mandates） | \|m\|、\|n\|（及 lcm 结果）可表示 | 违反即 UB |
| `midpoint`（算术） | 算术类型，非 `bool`（Constraints） | — | 保证不溢出；整数向 `a` 取整 |
| `midpoint`（指针） | 完整对象类型 | 同一数组 | — |
| `saturating_add/sub/mul` | 有符号/无符号整数类型（不含字符类型、`bool`） | — | 夹紧到最近的极值 |
| `saturating_div` | 同上 | `y != 0`（常量求值中被诊断） | `min / -1` → `max` |
| `saturating_cast` | 同上 | — | 夹紧 |
