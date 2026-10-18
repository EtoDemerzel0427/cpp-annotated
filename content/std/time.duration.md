---
title: 类模板 duration
summary: duration = 计次数 + 编译期周期；哪些转换可以隐式发生、哪些必须 duration_cast；算术结果的类型如何由 common_type 决定；duration_cast/floor/ceil/round 的精确舍入规则；字面量、abs、流输出——以及溢出与整数截断这两个最常见的坑
status: done
covers: *
papers: N2661, P0092R1
related: time.traits, time.point, time.hms, time.format, ratio, conv.integral, expr.mul
tags: 标准库, chrono, duration, 单位安全
updated: 2026-10-18
---

`duration` 是整个 `<chrono>` 的地基。它的设计可以用一句话概括：**数值在对象里，单位在类型里**。`milliseconds{1500}` 在内存中只是一个 64 位整数 1500，和 `long long` 一样大、一样快；"毫秒"这个信息存在于模板实参 `ratio<1, 1000>` 中，只在编译期参与计算。于是：

- 不同单位之间的换算系数在编译期算好，运行时只剩一次乘法或除法（或者什么都不剩）；
- 会丢信息的换算（如毫秒 → 秒）不允许隐式发生，必须写 `duration_cast` / `floor` / `ceil` / `round`；
- 函数签名写 `void sleep(milliseconds)` 时，调用者传 `2s` 会自动换算成 2000ms，传整数 `2` 则编译失败——"单位是多少"不再靠文档约定。

## 表示与周期（[time.duration.general]）

¶1：duration 度量两个时间点之间的时间。它由一个**表示**（representation，存计次数）和一个**计次周期**（[[g:tick-period]]）组成；周期是相邻两次计次之间的秒数，用编译期有理数 `ratio`（[[ratio]]）表示。

```cpp
template<class Rep, class Period = ratio<1>>
class duration {
public:
  using rep    = Rep;
  using period = Period::type;     // 注意：约分后的 ratio
private:
  rep rep_;                        // 仅用于说明
  // ...
};
```

`period` 是 `Period::type` 而不是 `Period`：`ratio<2, 4>::type` 是 `ratio<1, 2>`。但 `duration<int, ratio<2,4>>` 与 `duration<int, ratio<1,2>>` 仍然是**两个不同的类型**，只是 `period` 相同。

¶2：`Rep` 必须是算术类型或"模拟算术类型的类"。若 `Rep` 是 cv 限定类型或 `duration` 的特化，程序非良构（{{ill-formed}}）。后一条防止 `duration<seconds>` 这种"时长的时长"——它会让 `common_type`、`operator/` 等的重载决议产生歧义。

¶3：若 `Period` 不是 `ratio` 的特化，或 `Period::num` 不是正数，程序非良构。负周期与零周期都没有意义；分母为正由 `ratio` 自己保证。

¶4：`duration` 的成员除了表示类型本身的操作抛出的异常之外，不抛异常。对内建算术类型，这意味着全部不抛。

¶5：默认的复制构造函数是 constexpr 函数，当且仅当 `rep_` 的相应初始化是 constexpr-suitable（[[dcl.constexpr]]）。换句话说，复制构造是否 constexpr 完全由 `rep` 决定：rep 是内建类型时它总是 constexpr；rep 是某个复制构造不能用于常量求值的类类型时，duration 的复制也就不是 constexpr，但特化本身照样合法。

¶6 的例子：

```cpp
duration<long, ratio<60>> d0;       // 用 long 计分钟
duration<long long, milli> d1;      // 用 long long 计毫秒
duration<double, ratio<1, 30>> d2;  // 用 double 计 1/30 秒（30 Hz 帧）
```

注意 `duration() = default`：默认构造的 duration **不**初始化 `rep_`，`seconds s;` 之后读 `s.count()` 读到的是不确定值（局部变量的情形下是 C++26 的错误值，[[basic.indet]]）。要零值请写 `seconds{}` 或 `seconds::zero()`。

## 构造：隐式转换的规则（[time.duration.cons]）

### 从数值构造（¶1–¶2）

```cpp
template<class Rep2> constexpr explicit duration(const Rep2& r);
```

¶1 *Constraints*：`is_convertible_v<const Rep2&, rep>` 为真，并且

- ¶1.1：`treat_as_floating_point_v<rep>` 为真，**或**
- ¶1.2：`treat_as_floating_point_v<Rep2>` 为假。

也就是说：浮点值不能用来构造整数 rep 的 duration（会截断小数），其他组合都行。

```cpp
duration<int, milli> d(3);          // OK
duration<int, milli> d2(3.5);       // error：Rep2 是浮点而 rep 不是
```

¶2：效果是用 `r` 初始化 `rep_`。

构造函数是 `explicit` 的——`seconds s = 5;` 非良构。这是单位安全的第一道门：裸数字没有单位，不允许悄悄变成时长。

### 从另一个 duration 构造（¶3–¶4）

```cpp
template<class Rep2, class Period2>
constexpr duration(const duration<Rep2, Period2>& d);   // 非 explicit
```

¶3 *Constraints*：`is_convertible_v<const Rep2&, rep>` 为真，`ratio_divide<Period2::type, period>` 是有效的 ratio 特化（不溢出），并且下面二者之一成立：

- ¶3.1：`treat_as_floating_point_v<rep>` 为真；或
- ¶3.2：`ratio_divide<Period2, period>::den` 为 1，且 `treat_as_floating_point_v<Rep2>` 为假。

¶3.2 的含义：源周期是目标周期的**整数倍**，换算只需要乘法。注 1 点明目的：防止整数 duration 之间隐式截断。

¶4：效果是用 `duration_cast<duration>(d).count()` 初始化 `rep_`。

把规则列成表：

| 源 → 目标 | 例子 | 隐式转换 |
|---|---|---|
| 整数，粗 → 细 | `seconds` → `milliseconds` | 允许（乘 1000） |
| 整数，细 → 粗 | `milliseconds` → `seconds` | **拒绝**（要除法） |
| 整数，不成倍数 | `duration<int, ratio<1,3>>` → `duration<int, ratio<1,2>>` | **拒绝** |
| 任意 → 浮点 | `milliseconds` → `duration<double>` | 允许 |
| 浮点 → 整数 | `duration<double>` → `seconds` | **拒绝**（即使周期相同） |

```cpp title="duration-conv.cpp" ok
#include <chrono>
#include <type_traits>
using namespace std::chrono;

static_assert( std::is_convertible_v<seconds, milliseconds>);
static_assert(!std::is_convertible_v<milliseconds, seconds>);
static_assert( std::is_convertible_v<milliseconds, duration<double>>);
static_assert(!std::is_convertible_v<duration<double>, seconds>);
static_assert( std::is_convertible_v<days, hours>);
static_assert(!std::is_convertible_v<hours, days>);
static_assert(!std::is_constructible_v<seconds, double>);   // ¶1：浮点数值不能构造整数 duration

int main() {
    milliseconds ms = 2s;                        // OK：2000ms
    auto s = duration_cast<seconds>(1999ms);     // 显式截断：1s
    return (ms.count() == 2000 && s.count() == 1) ? 0 : 1;
}
```

!!! note "约束而非强制"
    这些都是 *Constraints*：不满足时构造函数**不参与重载决议**，所以 `is_convertible_v` 能检测到"不可转换"。这让 `duration` 可以安全地出现在重载集合里——`f(seconds)` 与 `f(milliseconds)` 两个重载，传 `1500ms` 只会选后者。

另一个后果是 ¶3 中"`ratio_divide` 是有效的 ratio"这一条：如果两个周期相除会在编译期溢出 `intmax_t`，转换构造函数直接消失，而不是在实例化时硬错误。

## 观察器与成员算术（[time.duration.observer]、[time.duration.arithmetic]）

[time.duration.observer] ¶1：`count()` 返回 `rep_`。**它返回计次数，不是秒数**——`milliseconds{1500}.count()` 是 1500。

[time.duration.arithmetic]：

- ¶1–¶2：一元 `+`、`-` 返回 `common_type_t<duration>`，而不是 `duration`。单参数的 `common_type<D>` 等于 `common_type<D, D>`，结果是 `duration<rep, period>`，用的是**约分后**的周期。所以 `+duration<int, ratio<2,4>>{1}` 的类型是 `duration<int, ratio<1,2>>`。实践中这一点几乎只影响用非约分 ratio 写出的类型。
- ¶3–¶8：前后缀 `++`/`--` 直接作用于 `rep_`。
- ¶9–¶12：`+=`、`-=` 的参数是**同类型**的 `const duration&`。`ms += 1s` 能编译是因为 `1s` 先隐式转换成了 `milliseconds`；`s += 1ms` 不能编译，因为 `1ms` 转不成 `seconds`。
- ¶13–¶18：`*=`、`/=`、`%=` 的参数是 `const rep&`——乘除的是无单位的数。
- ¶19–¶20：`%= const duration&` 取余数。

## 特殊值（[time.duration.special]）

¶1–¶3：`zero()`、`min()`、`max()` 分别返回 `duration(duration_values<rep>::zero())` 等，见 [[time.traits]]。`min()` 对整数 rep 是最小负数，不是零。

## 非成员算术（[time.duration.nonmember]）

¶1 约定：`CD` 表示函数的返回类型。

| 运算 | 返回类型 | 段落 |
|---|---|---|
| `d1 + d2`、`d1 - d2` | `common_type_t<D1, D2>` | ¶2–¶3 |
| `d * s`、`s * d` | `duration<common_type_t<Rep1, Rep2>, Period>` | ¶4–¶7 |
| `d / s` | `duration<common_type_t<Rep1, Rep2>, Period>` | ¶8–¶9 |
| `d1 / d2` | `common_type_t<Rep1, Rep2>`（**无单位的数**） | ¶10–¶11 |
| `d % s` | `duration<common_type_t<Rep1, Rep2>, Period>` | ¶12–¶13 |
| `d1 % d2` | `common_type_t<D1, D2>` | ¶14 |

要点：

- **加减先转到公共类型**（¶2–¶3）。`1s + 1ms` 是 `milliseconds{1001}`，`1h - 1min` 是 `minutes{59}`。转到公共类型只需乘法，整数下不丢信息（但可能溢出）。
- **乘以数值时 rep 可能变宽**（¶4–¶7）。`1s * 1.5` 的类型是 `duration<double>`。约束要求 `Rep2` 能转换为 `common_type_t<Rep1, Rep2>`。
- **`d / s` 与 `d % s` 的约束多了一条："`Rep2` 不是 duration 的特化"**（¶8、¶12）。没有这条，`1s / 2ms` 会同时匹配"duration 除以数值"和"duration 除以 duration"两个模板，造成歧义。
- **duration 除以 duration 得到纯数**（¶10–¶11）。`1s / 2ms` 是 `long long` 类型的 500：先把两边都转换到公共类型 `milliseconds`，再用 count 相除。这是"这段时间里能放下几个那段时间"的问题，结果自然无量纲。
- `d1 % d2` 的结果是公共类型的 duration，常用于"取一天中的时刻"：`tp.time_since_epoch() % days{1}`。

所有整数运算都遵循内建运算的规则：除法**向零截断**（[[expr.mul]]），有符号溢出是 UB。

```cpp title="duration-arith.cpp" ok
#include <chrono>
#include <type_traits>
using namespace std::chrono;

static_assert(std::is_same_v<decltype(1s + 1ms), milliseconds>);
static_assert(std::is_same_v<decltype(1s * 1.5), duration<double>>);
static_assert(std::is_same_v<decltype(1s / 2ms), long long>);   // libc++：seconds::rep 是 long long
static_assert(std::is_same_v<decltype(1h % 7min), minutes>);

static_assert(1s + 1ms == 1001ms);
static_assert(1s / 2ms == 500);
static_assert(1h % 7min == 4min);
static_assert(seconds{1} / 2 == 0s);       // 整数除法：截断到 0
static_assert(-7s / 2 == -3s);             // 向零截断

int main() {}
```

（`1s / 2ms` 的类型是 `common_type_t<seconds::rep, milliseconds::rep>`；`long long` 是 libc++ 上的结果，标准只规定"至少若干位的有符号整数"。）

## 比较（[time.duration.comparisons]）

¶1：`CT` 表示两个实参类型的 `common_type_t`。

- ¶2–¶3：`==` 与 `<` 先把两边转到 `CT` 再比较 count。所以 `1s == 1000ms` 为真，`1999ms < 2s` 为真——比较的是物理时长，不是数字。
- ¶4–¶6：`>`、`<=`、`>=` 由 `<` 推出。
- ¶7：`<=>` 要求 `CT::rep` 满足 `three_way_comparable`，返回 `CT(lhs).count() <=> CT(rhs).count()`；对 `duration<double>` 得到 `partial_ordering`（NaN 不可比较）。

!!! lawyer "跨类型比较也可能溢出"
    `nanoseconds::max() == hours{3'000'000}` 要把 `hours` 转换成 `nanoseconds`，乘法溢出——这是 {{ub}}，而不是"返回 false"。

## 转换函数（[time.duration.cast]）

### duration_cast（¶1–¶3）

¶1 *Constraints*：`ToDuration` 是 duration 的特化。

¶2：令 `CF` 为 `ratio_divide<Period, ToDuration::period>`（换算系数），`CR` 为 `common_type<ToDuration::rep, Rep, intmax_t>::type`（中间计算类型）。按 `CF` 分四种情形：

| 情形 | 计算 |
|---|---|
| ¶2.1 `CF` 为 1/1 | `static_cast<ToRep>(d.count())` |
| ¶2.2 `CF::den == 1` | `static_cast<ToRep>(static_cast<CR>(d.count()) * CF::num)` |
| ¶2.3 `CF::num == 1` | `static_cast<ToRep>(static_cast<CR>(d.count()) / CF::den)` |
| ¶2.4 其他 | `static_cast<ToRep>(static_cast<CR>(d.count()) * CF::num / CF::den)` |

¶3（注 1）总结了三点设计：全部用 `static_cast`，不靠隐式转换；编译期已知某个系数为 1 时省掉对应的乘除；中间结果用"最宽"的表示 `CR` 计算，最后一步才转换到目标 rep。

由此可以推出几条精确的结论：

- 整数情形下 `duration_cast` 是**向零截断**的（¶2.3 用的是内建 `/`）：`duration_cast<seconds>(-1500ms)` 是 `-1s`，不是 `-2s`。
- ¶2.4 先乘后除，以保留精度，但乘法可能在 `CR`（至少 `intmax_t`）里溢出。
- 浮点 → 整数的最后一步 `static_cast` 若值超出目标类型范围，是 {{ub}}（[[conv.fpint]]）。

### floor、ceil、round（¶4–¶9）{{c++17}}

C++17 由 [[P0092R1]] 加入：

- ¶4–¶5 `floor<To>(d)`：`To` 中满足 `t <= d` 的**最大**值——向负无穷取整。
- ¶6–¶7 `ceil<To>(d)`：满足 `t >= d` 的**最小**值——向正无穷取整。
- ¶8–¶9 `round<To>(d)`：最接近 `d` 的值；正好在中间时取 `t % 2 == 0` 的那个（**四舍六入五成双**，banker's rounding）。约束要求 `To::rep` 不是浮点——对浮点目标"取整"没有意义。

```cpp title="rounding.cpp" ok
#include <chrono>
using namespace std::chrono;

static_assert(duration_cast<seconds>(-1500ms) == -1s);   // 向零
static_assert(floor<seconds>(-1500ms)         == -2s);   // 向负无穷
static_assert(ceil<seconds>(-1500ms)          == -1s);   // 向正无穷
static_assert(round<seconds>(1500ms)          ==  2s);   // 1.5 → 2（2 是偶数）
static_assert(round<seconds>(2500ms)          ==  2s);   // 2.5 → 2（不是 3！）
static_assert(round<seconds>(-2500ms)         == -2s);

int main() {}
```

`floor` 是处理时刻时最常用的一个：`floor<days>(system_clock::now())` 得到"今天零点"（UTC），而 `duration_cast<days>` 对 1970 年之前的时刻会得到"明天零点"——因为负数向零截断。

## 字面量（[time.duration.literals]）{{c++14}}

¶1：后缀 `h`、`min`、`s`、`ms`、`us`、`ns` 作用于整数字面量时，分别得到 `hours`、`minutes`、`seconds`、`milliseconds`、`microseconds`、`nanoseconds`。

¶2：作用于浮点字面量时，得到 rep 为**未指明浮点类型**的 duration。`0.5h` 是"半小时"，类型是 `duration<某浮点, ratio<3600>>`。

¶3：整数字面量换算后无法用结果类型表示（溢出）时，程序非良构（{{ill-formed}}）。

¶4–¶11 列出各个字面量运算符；¶8 的注说明 `s` 与 `basic_string` 的 `""s` 不冲突。

```cpp
using namespace std::chrono_literals;
auto constexpr aday       = 24h;
auto constexpr lesson     = 45min;
auto constexpr halfanhour = 0.5h;
```

!!! impl "libc++ 不诊断字面量溢出"
    ¶3 要求溢出时报错。截至写作时，libc++ 的 `operator""h(unsigned long long)` 只是直接构造 `hours(h)`，`18'000'000'000'000'000'000h`（能放进 `unsigned long long` 但放不进 `long`）会被静默转换成一个负数并通过编译。这是 libc++ 的不符合之处。

`us` 而不是 `µs`：字面量后缀必须是标识符，ASCII 输入最方便。但流输出时微秒的后缀可以是 `µs`，见下文。

## abs（[time.duration.alg]）{{c++17}}

¶1 *Constraints*：`numeric_limits<Rep>::is_signed` 为真。¶2：`d >= d.zero()` 时返回 `d`，否则返回 `-d`。对 `min()` 求 `abs` 会溢出——与内建 `abs(INT_MIN)` 同理。

## 流输出与 from_stream（[time.duration.io]）{{c++20}}

¶1：`os << d` 等价于：在一个复制了 `os` 的 flags、locale、precision 的 `basic_ostringstream` 中输出 `d.count()` 和单位后缀，再把整个字符串写入 `os`。先拼成一个字符串再输出，是为了让 `setw` 对"数值 + 后缀"整体生效。

后缀由 `Period::type` 决定：

| 周期 | 后缀 | 周期 | 后缀 |
|---|---|---|---|
| `atto` … `nano` | `as` `fs` `ps` `ns` | `ratio<1>` | `s` |
| `micro` | `µs` 或 `us`（{{impl}}） | `deca` … `exa` | `das` `hs` `ks` `Ms` `Gs` `Ts` `Ps` `Es` |
| `milli`、`centi`、`deci` | `ms` `cs` `ds` | `ratio<60>`、`ratio<3600>`、`ratio<86400>` | `min` `h` `d` |
| 其他，`den == 1` | `[num]s` | 其他 | `[num/den]s` |

（¶1.1–¶1.22。）libc++ 对 `micro` 选择输出 `µs`。没有命名的周期会以方括号显示：`duration<int, ratio<1,3>>{5}` 输出 `5[1/3]s`。`weeks`、`months`、`years` 没有专门的后缀，分别显示为 `[604800]s`、`[2629746]s`、`[31556952]s`。

¶3–¶4：`from_stream` 按 [[time.parse]] 的格式解析一个 duration；失败时设置 `failbit` 且不修改 `d`。libc++ 尚未实现。

```cpp title="duration-io.cpp" ok
#include <chrono>
#include <iostream>
using namespace std::chrono;

int main() {
    std::cout << 42ms << ' ' << 3us << ' ' << 90min << ' ' << days{2} << '\n';
    std::cout << duration<int, std::ratio<1, 3>>{5} << ' ' << weeks{1} << '\n';
    std::cout << duration<double, std::milli>{1.5} << '\n';
}
```

在 libc++ 上输出 `42ms 3µs 90min 2d`、`5[1/3]s 1[604800]s` 和 `1.5ms`。

## 陷阱

!!! pitfall "nanoseconds 只能表示 ±292 年"
    `nanoseconds` 的 rep 至少 64 位，2⁶³ ns ≈ 292 年。`system_clock::time_point` 若以纳秒计（libstdc++ 如此），则最大只到 2262 年。把"很长的时长"转换成纳秒是最常见的溢出来源：

    ```cpp
    auto ns = duration_cast<nanoseconds>(years{300});   // UB：有符号溢出
    nanoseconds x = years{300};                         // 同样 UB：隐式转换只保证不截断，不保证不溢出
    ```

    第二行尤其隐蔽：隐式转换规则（¶3.2）只看周期是否成倍数，完全不管数值范围。用 UBSan 运行会报告 `signed integer overflow`。在常量表达式中，同样的溢出会让求值失败，编译器给出诊断。

!!! pitfall "`duration<int, milli>` 只能表示 24.8 天"
    自定义 duration 时用 `int` 作 rep 很诱人，但 2³¹ ms ≈ 24.8 天。一个运行一个月的服务，用 `duration<int, milli>` 累计运行时间就会溢出。标准别名的位宽保证（见 [[time]]）就是为了避免这种问题——优先用 `milliseconds`。

!!! pitfall "整数 duration 的除法会截断"
    `seconds{1} / 2` 是 `0s`；`seconds{3} / seconds{2}` 是 `1`。需要小数就先转换成浮点 duration：`duration<double>{3s} / 2s` 是 `1.5`。

!!! pitfall "无符号 rep"
    `duration<unsigned>{1} - duration<unsigned>{2}` 得到 4294967295 秒。`abs` 对无符号 rep 不可用（¶1 约束）。时间差天然有正负，rep 应当有符号——`system_clock::rep` 被明确要求是有符号的（[[time.clock]]）。

!!! pitfall "`count()` 把单位丢掉了"
    `usleep(d.count())` 只有在 `d` 恰好是 `microseconds` 时才对。在接口边界上应先转换到目标单位再取 count：`usleep(duration_cast<microseconds>(d).count())`，或者更好地，让函数直接接受 duration。

## 思考题

1. `seconds s = 1500ms;` 非良构，但 `seconds s{1500ms};` 呢？

<details markdown="1">
<summary>答案</summary>

同样非良构。转换构造函数没有被 `explicit` 修饰，阻止它的不是"复制初始化不能用 explicit 构造函数"，而是 ¶3 的 *Constraints*：`milli / ratio<1>` 的分母不是 1，且 rep 是整数，所以该构造函数根本不参与重载决议。直接初始化也找不到可行函数。必须写 `duration_cast<seconds>(1500ms)` 或 `floor<seconds>(1500ms)`。
</details>

2. `1s / 2ms` 与 `1s / 2` 都是"duration 除以某物"，为什么不会歧义？

<details markdown="1">
<summary>答案</summary>

¶8 给 `operator/(const duration<Rep1,Period>&, const Rep2&)` 加了约束"`Rep2` 不是 duration 的特化"。对 `1s / 2ms`，`Rep2` 被推导为 `milliseconds`，约束失败，只剩 duration / duration 版本；对 `1s / 2`，`Rep2` 是 `int`，duration / duration 版本推导失败，只剩 duration / 数值版本。
</details>

3. `round<seconds>(2500ms)` 为什么是 `2s` 而不是 `3s`？

<details markdown="1">
<summary>答案</summary>

¶9：有两个最近值时，返回 `t % 2 == 0` 的那个。2s 与 3s 到 2.5s 的距离相等，2 是偶数。这种"银行家舍入"在大量取整的累加中不会产生系统性偏差。
</details>

## 小结

| 主题 | 规则 |
|---|---|
| 表示 | `count()` = 计次数；`period` = 约分后的 ratio；默认构造不初始化 |
| 隐式转换 | 目标是浮点，或（整数且源周期是目标周期的整数倍）；浮点 → 整数永远要显式 |
| 显式转换 | `duration_cast` 向零截断；`floor`/`ceil` 向负/正无穷；`round` 四舍六入五成双 |
| 算术 | 加减、比较先转到公共类型（周期取 gcd）；duration / duration 得纯数 |
| 溢出 | 隐式转换不防溢出；`nanoseconds` 只有 ±292 年 |
