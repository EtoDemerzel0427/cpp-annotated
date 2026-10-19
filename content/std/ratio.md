---
title: 编译期有理数算术
summary: std::ratio<N, D> 用类型表示一个精确的有理数，在编译期做加减乘除和比较；结果放不下 intmax_t 时程序非良构。它是 <chrono> 时间单位的基础。
status: done
covers: *
related: meta, time.duration, type.traits, meta.help, basic.fundamental
tags: 标准库, ratio, 编译期计算, chrono
updated: 2026-10-19
---

!!! tldr
    - `ratio<N, D>` 是一个类型，它的 `num`、`den` 是约分后的分子分母，分母总是正数。
    - `ratio<2, 4>` 和 `ratio<1, 2>` 是不同的类型，`num`、`den` 却相同；判断相等要用 `ratio_equal_v` 或比较 `::type`。
    - `ratio_add` 等算术别名的结果总是约分后的 `ratio`；结果放不下 `intmax_t` 时程序非良构，只有中间量溢出时实现应当设法算对，算不对也必须报错。
    - `zepto`、`yocto` 等八个 SI 前缀只有在 `intmax_t` 能表示时才声明，64 位 `intmax_t` 上它们都不存在。

## 用类型表示单位

```cpp run title="chrono-period.cpp" ok
#include <chrono>
#include <ratio>
#include <type_traits>

using namespace std::chrono;
static_assert(std::is_same_v<milliseconds::period, std::milli>);   // milli 是 ratio<1, 1000>
static_assert(std::is_same_v<std::milli, std::ratio<1, 1000>>);

int main() {
  milliseconds ms = seconds(3);   // 换算系数 1000/1 在编译期算出
  return ms.count() == 3000 ? 0 : 1;
}
```

时长类型 `duration<Rep, Period>` 的 `Period` 就是一个 `ratio`，表示一个计时单位是多少秒。把单位写进类型，单位之间的换算系数就能在编译期精确算出来，运行时只剩一次乘除。`<ratio>` 是 C++11 为 `<chrono>` 准备的，当时 `constexpr` 还很弱，所以它的设计是用类型做算术：数值放在模板实参里，加减乘除是别名模板，比较是类模板。整个头文件都是 freestanding 的，在没有操作系统的环境中也要提供。

## `ratio` 与约分 [ratio.ratio]

```cpp
template<intmax_t N, intmax_t D = 1> class ratio {
public:
  static constexpr intmax_t num;
  static constexpr intmax_t den;
  using type = ratio<num, den>;
};
```

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

¶2 `num` 和 `den` 是约分并统一符号之后的值。设 `gcd` 为 `|N|` 和 `|D|` 的最大公约数，则 `num` 等于 `sgn(N) * sgn(D) * abs(N) / gcd`，`den` 等于 `abs(D) / gcd`。所以 `den` 总是正的，符号全部放在 `num` 上。

约分只体现在 `num`、`den` 的值上，类型本身不变：`ratio<2, 4>` 仍然是 `ratio<2, 4>`。成员 `type` 才是约分后的规范形式 `ratio<1, 2>`。

¶1 如果 `D` 为零，或者 `N`、`D` 的绝对值不能用 `intmax_t` 表示，程序非良构。第二条排除的是最小的负数：在补码表示下 `INTMAX_MIN` 的绝对值放不下。有了这条限制，约分和统一符号时就可以放心地对绝对值做运算（注 1）。

```cpp run title="ratio-zero.cpp" error
#include <ratio>
using X = std::ratio<1, 0>;    // 只是别名，还没有实例化，不报错
constexpr auto n = X::num;     // error: 实例化 ratio<1, 0>，分母为零
int main() {}
```

别名声明不会实例化类模板，所以第二行本身没有问题。第三行用到了 `X::num`，`ratio<1, 0>` 被实例化，libc++ 的 `static_assert` 报告 "ratio divide by 0"。

## 算术 [ratio.arithmetic]

| 别名 | `X` | `Y` |
|---|---|---|
| `ratio_add<R1, R2>` | `R1::num * R2::den + R2::num * R1::den` | `R1::den * R2::den` |
| `ratio_subtract<R1, R2>` | `R1::num * R2::den - R2::num * R1::den` | `R1::den * R2::den` |
| `ratio_multiply<R1, R2>` | `R1::num * R2::num` | `R1::den * R2::den` |
| `ratio_divide<R1, R2>` | `R1::num * R2::den` | `R1::den * R2::num` |

¶1 四个别名模板先按上表算出 `X` 和 `Y`，结果是 `ratio<U, V>`，其中 `U`、`V` 是 `ratio<X, Y>::num` 和 `ratio<X, Y>::den`。所以结果总是规范形式，即使输入不是：

```cpp run title="ratio-arith.cpp" ok
#include <ratio>
#include <type_traits>
using namespace std;

static_assert(is_same_v<ratio_add<ratio<1, 3>, ratio<1, 6>>, ratio<1, 2>>);
static_assert(is_same_v<ratio_add<ratio<2, 4>, ratio<0>>, ratio<1, 2>>);   // 输入未约分
static_assert(is_same_v<ratio_multiply<milli, kilo>, ratio<1>>);

int main() {}
```

[ratio.general] ¶2 规定，形参名为 `R1`、`R2` 的地方，模板实参必须是 `ratio` 的特化，否则程序非良构。一个自己写的、带有 `num` 和 `den` 成员的类也不行。

### 溢出

```cpp run title="ratio-overflow.cpp" error
#include <cstdint>
#include <ratio>

constexpr std::intmax_t M = INTMAX_MAX;
// 1/M + 1/(M-1) 的分母 M*(M-1) 放不下 intmax_t
constexpr auto v = std::ratio_add<std::ratio<1, M>, std::ratio<1, M - 1>>::num;   // error

int main() {}
```

!!! std
    If it is not possible to represent `U` or `V` with `intmax_t`, the program is ill-formed. Otherwise, an implementation should yield correct values of `U` and `V`.

¶2 溢出规则分两层。最终结果 `U`、`V` 放不下，程序一定非良构，编译器必须报错。结果放得下、只是中间量 `X` 或 `Y` 放不下时，实现应当算出正确的结果，例如先交叉约去公因子再相乘；如果实现没有算对，程序也必须是非良构的，不能静默地得到错误的值。

```cpp run title="ratio-intermediate.cpp" ok
#include <cstdint>
#include <ratio>
#include <type_traits>
using namespace std;

constexpr intmax_t M = INTMAX_MAX;
// 按定义 Y = M * 2 会溢出，但结果 1/2 放得下；libc++ 先约分，算对了
static_assert(is_same_v<ratio_multiply<ratio<1, M>, ratio<M, 2>>, ratio<1, 2>>);

int main() {}
```

¶3 标准的例子也包含这种情况，并在注释里说明它在某些实现上可能是非良构的。上面溢出的例子，libc++ 在内部的检查辅助模板中报告 "overflow in __ll_add"。

## 比较 [ratio.comparison]

六个比较模板都派生自 `bool_constant`，另有对应的 `_v` 变量模板：

- `ratio_equal`：`R1::num == R2::num && R1::den == R2::den`。两边都已是规范形式，逐项比较就是数值相等；
- `ratio_less`：¶1 若 `R1::num × R2::den < R2::num × R1::den` 则为真；
- `ratio_not_equal`、`ratio_less_equal`、`ratio_greater`、`ratio_greater_equal` 都用前两者定义。

¶1 对 `ratio_less`，实现可以换用别的算法来避免溢出；如果仍然溢出，程序非良构。libc++ 按连分数逐步比较，所以 `ratio_less_v<ratio<M - 1, M>, ratio<M, M - 1>>`（`M = INTMAX_MAX`）能正确得到 `true`，尽管按定义直接相乘早就溢出了。

## SI 前缀 [ratio.si]

`<ratio>` 为全部 24 个十进制 SI 前缀提供了别名，从 `quecto`（10⁻³⁰）到 `quetta`（10³⁰），包括 2022 年加入 SI 的 `ronto`、`quecto`、`ronna`、`quetta`。

¶1 其中 `quecto`、`ronto`、`yocto`、`zepto`、`zetta`、`yotta`、`ronna`、`quetta` 八个比较特殊：只有当定义中用到的两个常量都能用 `intmax_t` 表示时才声明，否则不声明。64 位 `intmax_t` 的最大值约为 9.2 × 10¹⁸，10²¹ 及以上都放不下，所以这八个别名在常见平台上都不存在：

```cpp run title="ratio-si.cpp" error
#include <ratio>

std::exa*    e;     // OK：10^18 放得下
std::zepto*  z;     // error: no type named 'zepto' in namespace 'std'
std::quecto* q;     // error

int main() {}
```

可移植的代码不能假设这些名字一定存在。

## 思考题

!!! question "思考题"
    `std::ratio_add<std::ratio<1, 2>, std::ratio<1, 2>>` 是什么类型？是 `std::ratio<4, 4>` 吗？

<details markdown="1">
<summary>答案</summary>

`X = 1*2 + 1*2 = 4`，`Y = 2*2 = 4`，结果是 `ratio<ratio<4, 4>::num, ratio<4, 4>::den>`，即 `ratio<1, 1>`，也就是 `ratio<1>`。它不是 `ratio<4, 4>`：算术别名的结果总是规范形式（[ratio.arithmetic] 第 1 段），而 `ratio<4, 4>` 是另一个类型，只是它的 `::type` 也是 `ratio<1>`。
</details>
