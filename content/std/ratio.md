---
title: 编译期有理数算术
summary: std::ratio<N, D> 用两个 intmax_t 常量精确表示有理数并自动约分；ratio_add 等算术别名、ratio_less 等比较 trait 的溢出规则（结果不可表示即非良构，中间量溢出时实现应尽量算对）；SI 前缀 typedef 与"不可表示则不声明"；它是 <chrono> 单位系统的地基
status: draft
covers: *
related: meta, time.duration, type.traits, meta.help, basic.fundamental
tags: 标准库, ratio, 编译期计算, chrono
updated: 2026-10-18
---

`<ratio>` 是 C++11 为 `<chrono>` 准备的基础设施：时长 `duration<Rep, Period>` 的 `Period` 就是一个 `ratio`，`milliseconds` 是 `duration<long long, milli>`，`milli` 是 `ratio<1, 1000>`。把"单位"编码进**类型**，单位换算的系数就能在编译期精确算出，运行期只剩一次乘除。

`ratio` 诞生于 `constexpr` 还很弱的 C++11 时代，因此它是一个"**用类型做算术**"的设计：数值放在模板实参里，加减乘除是别名模板，比较是 trait。今天用 `constexpr` 函数也能做同样的事，但 `ratio` 作为 `<chrono>` 的接口一部分会一直存在。

## 总则（[ratio.general]）

¶1：`ratio` 能**精确**表示任何分子、分母都可以用 `intmax_t` 编译期常量表示的有限有理数。

¶2：本子条款中，名为 `R1`、`R2` 的模板形参表示类型要求：若对应的模板实参**不是** `ratio` 模板的特化，程序**非良构**。所以 `ratio_add<int, ratio<1>>` 必须被诊断。注意它要求的是"`ratio` 的特化"——一个"长得像" `ratio` 的用户类型（有 `num`、`den` 成员）也不行。

## 头文件概要（[ratio.syn]）

`<ratio>` 全部是 freestanding 的（`// all freestanding`）。内容分四块：类模板 `ratio`；四个算术别名 `ratio_add`、`ratio_subtract`、`ratio_multiply`、`ratio_divide`；六个比较 trait `ratio_equal`、`ratio_not_equal`、`ratio_less`、`ratio_less_equal`、`ratio_greater`、`ratio_greater_equal` 及其 `_v` 变量模板；以及 24 个 SI 前缀别名（从 `quecto` = 10⁻³⁰ 到 `quetta` = 10³⁰）。

## 类模板 `ratio`（[ratio.ratio]）

```cpp
template<intmax_t N, intmax_t D = 1> class ratio {
public:
  static constexpr intmax_t num;
  static constexpr intmax_t den;
  using type = ratio<num, den>;
};
```

¶1：若 `D` 为零，或 `N`、`D` 中任一个的**绝对值**不能用 `intmax_t` 表示，程序非良构。注 1 解释了第二条：它排除了最小的负数（`INTMAX_MIN` 的绝对值在补码下不可表示），从而保证任何负输入都有一个可表示的正绝对值——约分和符号归一化都需要对绝对值做运算。

¶2：`num`、`den` 是**约分并规范化符号**后的值，`gcd` 为 `|N|` 与 `|D|` 的最大公约数：

- `num` = `sgn(N) * sgn(D) * abs(N) / gcd`
- `den` = `abs(D) / gcd`

所以 `den` 永远为正，符号全部归到 `num`。

!!! pitfall "`ratio<2, 4>` 与 `ratio<1, 2>` 是不同的类型"
    约分体现在 `num`/`den` 的**值**上，而不是类型本身：`ratio<2, 4>` 仍是 `ratio<2, 4>`，只是它的 `num == 1`、`den == 2`。成员 `type` 才是规范形式 `ratio<1, 2>`。因此判断两个 ratio 相等要用 `ratio_equal_v`，或比较 `::type`，而不是对原类型用 `is_same_v`。算术别名的结果则总是规范形式（见下）。

```cpp run title="ratio-basic.cpp" ok
#include <ratio>
#include <type_traits>
using namespace std;

static_assert(ratio<2, 4>::num == 1 && ratio<2, 4>::den == 2);
static_assert(ratio<1, -3>::num == -1 && ratio<1, -3>::den == 3);   // 符号归到分子
static_assert(ratio<-6, -4>::num == 3 && ratio<-6, -4>::den == 2);
static_assert(!is_same_v<ratio<2, 4>, ratio<1, 2>>);                // 类型不同
static_assert( is_same_v<ratio<2, 4>::type, ratio<1, 2>>);         // 规范形式相同
static_assert( ratio_equal_v<ratio<2, 4>, ratio<1, 2>>);

int main() {}
```

!!! note "非良构什么时候被诊断"
    `using X = std::ratio<1, 0>;` 本身不会报错——别名声明不实例化类模板。一旦用到 `X::num` 或 `X::type`，libc++ 的 `static_assert` 就会报 "ratio divide by 0"。`ratio<INTMAX_MIN, 1>` 同理会在实例化时被拒绝。

## 算术（[ratio.arithmetic]）

¶1：四个别名模板各自表示对 `R1`、`R2` 的算术结果。先按表 65（在不溢出的前提下）算出 `X`、`Y`，结果是 `ratio<U, V>`，其中 `U`、`V` 是 `ratio<X, Y>::num` 与 `ratio<X, Y>::den`——即**规范形式**：

| 别名 | `X` | `Y` |
|---|---|---|
| `ratio_add<R1, R2>` | `R1::num * R2::den + R2::num * R1::den` | `R1::den * R2::den` |
| `ratio_subtract<R1, R2>` | `R1::num * R2::den - R2::num * R1::den` | `R1::den * R2::den` |
| `ratio_multiply<R1, R2>` | `R1::num * R2::num` | `R1::den * R2::den` |
| `ratio_divide<R1, R2>` | `R1::num * R2::den` | `R1::den * R2::num` |

¶2 是溢出规则，有两层：

!!! std
    If it is not possible to represent `U` or `V` with `intmax_t`, the program is ill-formed. Otherwise, an implementation should yield correct values of `U` and `V`. If it is not possible to represent `X` or `Y` with `intmax_t`, the program is ill-formed unless the implementation yields correct values of `U` and `V`.

    若 `U` 或 `V` 不能用 `intmax_t` 表示，程序非良构。否则，实现**应当**给出正确的 `U`、`V`。若中间量 `X` 或 `Y` 不能用 `intmax_t` 表示，除非实现给出了正确的 `U`、`V`，否则程序非良构。

也就是说：**最终结果**放不下，一定是错误；**只有中间量**放不下而结果放得下，好的实现应该通过先约分（交叉约去公因子）等技巧算对，算不对也必须报错，而不是静默溢出。¶3 例子的后半部分正是这种情况，标准在注释里承认"在某些实现下可能非良构"。

```cpp run title="ratio-arith.cpp" ok
#include <chrono>
#include <cstdint>
#include <ratio>
#include <type_traits>
using namespace std;

static_assert(is_same_v<ratio_add<ratio<1, 3>, ratio<1, 6>>, ratio<1, 2>>);   // 结果已约分
static_assert(is_same_v<ratio_multiply<milli, kilo>, ratio<1>>);

constexpr intmax_t M = INTMAX_MAX;
// 中间量 1 * M 与 M * 2 中的 M * 2 溢出，但结果 1/2 可表示：libc++ 先交叉约分，算对了
static_assert(is_same_v<ratio_multiply<ratio<1, M>, ratio<M, 2>>, ratio<1, 2>>);

static_assert(is_same_v<chrono::milliseconds::period, milli>);

int main() {}
```

而结果本身放不下时必须诊断：

```cpp run title="ratio-overflow.cpp" error
#include <cstdint>
#include <ratio>

// 1/M + 1/(M-1) 的分母 M*(M-1) 不能用 intmax_t 表示 → 非良构
constexpr auto v = std::ratio_add<std::ratio<1, INTMAX_MAX>, std::ratio<1, INTMAX_MAX - 1>>::num;

int main() {}
```

libc++ 在此报 "overflow in __ll_add"——它内部用带溢出检查的 `__ll_add`、`__ll_mul` 等辅助模板做每一步运算。

## 比较（[ratio.comparison]）

六个比较模板都派生自 `bool_constant`：

- `ratio_equal`：`R1::num == R2::num && R1::den == R2::den`——因为两边都已是规范形式，逐分量比较就是数值相等；
- `ratio_not_equal`、`ratio_less_equal`、`ratio_greater`、`ratio_greater_equal` 都用 `ratio_equal`/`ratio_less` 表达；
- `ratio_less`（¶1）：若 `R1::num × R2::den < R2::num × R1::den` 则为真。**实现可以使用其他算法以避免溢出**；若确实发生溢出，程序非良构。

libc++ 的 `ratio_less` 用连分数式的比较避免了大部分溢出，例如 `ratio_less_v<ratio<M-1, M>, ratio<M, M-1>>`（`M = INTMAX_MAX`）可以正确算出 `true`，而按定义直接相乘早已溢出。

## SI 前缀（[ratio.si]）

概要给出 24 个别名，覆盖 SI 的全部十进制前缀，包括 2022 年新增的 `ronto`/`quecto`（10⁻²⁷/10⁻³⁰）与 `ronna`/`quetta`（10²⁷/10³⁰）。

¶1：对 `quecto`、`ronto`、`yocto`、`zepto`、`zetta`、`yotta`、`ronna`、`quetta` 这八个，**若其定义中用到的两个常量都能用 `intmax_t` 表示，就声明该 typedef；否则不声明**。在 64 位 `intmax_t` 上（最大约 9.2 × 10¹⁸），10²¹ 及以上都放不下，所以这八个都不存在：

```cpp run title="ratio-si.cpp" error
#include <ratio>

std::exa*   ok;     // 10^18 可以表示
std::zepto* z;      // error: no type named 'zepto' in namespace 'std'
std::quecto* q;     // error

int main() {}
```

这是标准中少见的"**条件声明**"：程序不能假设某个名字一定存在。可移植代码若要用 `yocto`，应先检测（例如写一个依赖 `intmax_t` 宽度的 `#if`）。

## 思考题

!!! question "思考题"
    `std::ratio_add<std::ratio<1, 2>, std::ratio<1, 2>>` 是什么类型？`std::ratio_add<std::ratio<2, 4>, std::ratio<0>>` 呢？

<details markdown="1">
<summary>展开查看答案与解析</summary>

第一个：`X = 1*2 + 1*2 = 4`、`Y = 2*2 = 4`，结果是 `ratio<4, 4>::num`/`den`，即 `ratio<1, 1>`（也就是 `ratio<1>`）。第二个：`R1` 的 `num`/`den` 已经是 1/2，`R2` 是 0/1；`X = 1*1 + 0*2 = 1`、`Y = 2*1 = 2`，结果 `ratio<1, 2>`——即使输入是非规范的 `ratio<2, 4>`，算术结果也总是规范形式（[ratio.arithmetic] ¶1）。
</details>

## 小结

| 组件 | 要点 |
|---|---|
| `ratio<N, D>` | `D == 0` 或绝对值不可表示 → 非良构；`num`/`den` 约分且 `den > 0`；类型本身不约分，`::type` 才是规范形式 |
| 算术别名 | 结果总是规范形式；结果放不下 → 非良构；仅中间量放不下 → 实现应算对，否则非良构 |
| 比较 | `ratio_less` 可用防溢出算法；溢出则非良构 |
| SI 前缀 | 24 个；放不下的 8 个不声明 |
| 实参检查 | `R1`/`R2` 不是 `ratio` 特化 → 非良构 |
