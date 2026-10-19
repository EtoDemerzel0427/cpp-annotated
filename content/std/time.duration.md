---
title: 类模板 duration
summary: duration 用一个计次数加一个编译期周期表示时长；哪些换算可以隐式发生，算术结果的类型怎样确定，duration_cast、floor、ceil、round 怎样舍入，以及溢出和整数截断这两类常见错误。
status: done
covers: *
papers: N2661, P0092R1, P0355R7
related: time.traits, time.point, time.hms, time.format, ratio, conv.integral, expr.mul
tags: 标准库, chrono, duration, 单位安全
updated: 2026-10-19
---

!!! tldr
    - `duration` 把数值存在对象里，把单位存在类型里：`milliseconds{1500}` 在运行时就是一个整数 1500，"毫秒"只存在于模板实参中。
    - 不会丢失信息的换算（秒到毫秒、任何类型到浮点）可以隐式发生；会截断的换算（毫秒到秒、浮点到整数）必须写 `duration_cast`、`floor`、`ceil` 或 `round`。
    - 不同单位的加减和比较先转换到公共类型，也就是两个周期的最大公约数；duration 除以 duration 得到一个没有单位的数。
    - `duration_cast` 向零截断，`floor` 和 `ceil` 分别向负、正无穷取整，`round` 在正中间时取偶数。
    - 隐式转换只保证不截断，不保证不溢出。`nanoseconds` 只能表示大约 ±292 年。

## 单位写在类型里

<div class="compare" markdown="1">

```cpp run ok
#include <chrono>
using namespace std::chrono;
void wait_for(milliseconds) {}
int main() {
  wait_for(2s);      // 换算成 2000ms
  wait_for(1500ms);
}
```

```cpp run error
#include <chrono>
using namespace std::chrono;
void wait_for(milliseconds) {}
int main() {
  wait_for(2);       // error: 没有单位
  wait_for(1.5s);    // error: 可能截断
}
```

</div>

`wait_for` 的形参是 `milliseconds`。传 `2s` 时，秒被自动换算成毫秒，乘以 1000 而已。传裸整数 `2` 编译失败，因为没人知道它是秒还是毫秒。传 `1.5s` 也失败：它的计数是浮点数，换成整数毫秒在一般情况下会截断。

单位换算的系数在编译期就算好了，运行时最多剩一次乘法或除法。`milliseconds` 和一个 `long long` 一样大，一样快。

## 表示：计次数加周期 [time.duration.general]

¶1 一个 duration 度量两个时间点之间的时间。它由两部分组成：**表示**（representation），保存计次数；**计次周期**（[[g:tick-period]]），即相邻两次计次之间是多少秒，用编译期有理数 `ratio`（[[ratio]]）表示。

```cpp
template<class Rep, class Period = ratio<1>>
class duration {
public:
  using rep    = Rep;
  using period = Period::type;   // 约分后的 ratio
private:
  rep rep_;                      // 仅用于说明
};
```

标准的例子（¶6）：

```cpp
duration<long, ratio<60>> d0;       // 用 long 计分钟
duration<long long, milli> d1;      // 用 long long 计毫秒
duration<double, ratio<1, 30>> d2;  // 用 double 计 1/30 秒（30 Hz 的帧）
```

`period` 是约分后的 `Period::type`。所以 `duration<int, ratio<2, 4>>` 的 `period` 是 `ratio<1, 2>`，但它和 `duration<int, ratio<1, 2>>` 仍然是两个不同的类型。

¶2 `Rep` 应当是算术类型，或者模拟算术类型的类。用 cv 限定的类型或者另一个 `duration` 作 `Rep`，程序非良构。后一条排除了 `duration<seconds>` 这种时长的时长，它会让 `common_type` 和 `operator/` 的重载决议产生歧义。

¶3 `Period` 必须是 `ratio` 的特化，并且 `Period::num` 必须为正，否则非良构。零周期和负周期都没有意义。

默认构造函数是 `= default`，不初始化 `rep_`。局部变量 `seconds s;` 的计数是不确定的，C++26 起读取它得到错误值（[[basic.indet]]）。需要零值时写 `seconds{}` 或 `seconds::zero()`。

## 什么时候可以隐式转换 [time.duration.cons]

### 从数值构造（¶1–¶2）

```cpp
template<class Rep2> constexpr explicit duration(const Rep2& r);
```

¶1 这个构造函数要求 `Rep2` 能隐式转换为 `rep`，并且满足下面两条之一：`rep` 是浮点类型（¶1.1），或者 `Rep2` 不是浮点类型（¶1.2）。换句话说，只禁止用浮点数构造整数计数的 duration，因为那会丢掉小数部分。

```cpp
duration<int, milli> d(3);       // OK
duration<int, milli> d2(3.5);    // error: Rep2 是浮点，rep 不是
```

构造函数是 `explicit` 的，所以 `seconds s = 5;` 非良构。裸数字没有单位，不能悄悄变成时长。

### 从另一个 duration 构造（¶3–¶4）

```cpp
template<class Rep2, class Period2>
constexpr duration(const duration<Rep2, Period2>& d);   // 不是 explicit
```

¶3 这个转换构造函数要求 `Rep2` 能隐式转换为 `rep`，两个周期相除不会在编译期溢出，并且满足下面两条之一：

- ¶3.1 目标的 `rep` 是浮点类型；
- ¶3.2 源周期是目标周期的整数倍（`ratio_divide<Period2, period>::den` 为 1），并且源的 `Rep2` 不是浮点类型。

¶3.2 的意思是换算只需要乘法。注 1 说明，这条要求是为了防止整数 duration 之间的隐式截断。¶4 规定转换的值是 `duration_cast<duration>(d).count()`。

| 方向 | 例子 | 隐式转换 |
|---|---|---|
| 整数，粗到细 | `seconds` → `milliseconds` | 允许，乘以 1000 |
| 整数，细到粗 | `milliseconds` → `seconds` | 不允许，要做除法 |
| 整数，周期不成倍数 | `ratio<1,3>` → `ratio<1,2>` | 不允许 |
| 任意到浮点 | `milliseconds` → `duration<double>` | 允许 |
| 浮点到整数 | `duration<double>` → `seconds` | 不允许，即使周期相同 |

```cpp run ok title="duration-conv.cpp"
#include <chrono>
#include <type_traits>
using namespace std::chrono;

static_assert( std::is_convertible_v<seconds, milliseconds>);
static_assert(!std::is_convertible_v<milliseconds, seconds>);
static_assert( std::is_convertible_v<milliseconds, duration<double>>);
static_assert(!std::is_convertible_v<duration<double>, seconds>);
static_assert( std::is_convertible_v<days, hours>);
static_assert(!std::is_convertible_v<hours, days>);
static_assert(!std::is_constructible_v<seconds, double>);   // ¶1

int main() {
  milliseconds ms = 2s;                      // 2000ms
  auto s = duration_cast<seconds>(1999ms);   // 显式截断：1s
  return (ms.count() == 2000 && s.count() == 1) ? 0 : 1;
}
```

这些条件都写成 *Constraints*。条件不满足时，构造函数不参与重载决议，而不是在实例化时报错。所以 `is_convertible_v` 能检测出不可转换；有 `f(seconds)` 和 `f(milliseconds)` 两个重载时，`f(1500ms)` 只会选后者。

## 取值、成员运算和特殊值

[[time.duration.observer#1]] 规定 `count()` 返回 `rep_`，也就是计次数，不是秒数：`milliseconds{1500}.count()` 是 1500。

[time.duration.arithmetic] 的成员运算符都直接作用于 `rep_`，有三点值得注意：

- 一元 `+` 和 `-` 返回 `common_type_t<duration>`，也就是周期约分后的类型（¶1–¶2）。只有用没约分的 `ratio` 写出的类型才看得出区别。
- `+=` 和 `-=` 的形参是同类型的 `const duration&`（¶9–¶12）。`ms += 1s` 能编译，是因为 `1s` 先隐式转换成了 `milliseconds`；`s += 1ms` 不能编译。
- `*=`、`/=` 和 `%=` 的形参是 `const rep&`，乘除的是没有单位的数（¶13–¶18）。另有一个 `%=` 接受 duration（¶19）。

[time.duration.special] 的 `zero()`、`min()`、`max()` 由 `duration_values<rep>` 给出（[[time.traits]]）。整数计数的 `min()` 是最小的负数，不是零。

## 混合单位的算术 [time.duration.nonmember]

```cpp run ok title="duration-arith.cpp"
#include <chrono>
#include <type_traits>
using namespace std::chrono;

static_assert(std::is_same_v<decltype(1s + 1ms), milliseconds>);
static_assert(std::is_same_v<decltype(1s * 1.5), duration<double>>);
static_assert(std::is_same_v<decltype(1s / 2ms), long long>);   // libc++
static_assert(std::is_same_v<decltype(1h % 7min), minutes>);

static_assert(1s + 1ms == 1001ms);
static_assert(1s / 2ms == 500);
static_assert(1h % 7min == 4min);
static_assert(seconds{1} / 2 == 0s);   // 整数除法：截断
static_assert(-7s / 2 == -3s);         // 向零截断

int main() {}
```

¶1 下面用 `CD` 表示函数的返回类型。

| 运算 | 返回类型 | 段落 |
|---|---|---|
| `d1 + d2`、`d1 - d2` | `common_type_t<D1, D2>` | ¶2–¶3 |
| `d * s`、`s * d` | `duration<common_type_t<Rep1, Rep2>, Period>` | ¶4–¶7 |
| `d / s`、`d % s` | 同上 | ¶8–¶9、¶12–¶13 |
| `d1 / d2` | `common_type_t<Rep1, Rep2>`，一个纯数 | ¶10–¶11 |
| `d1 % d2` | `common_type_t<D1, D2>` | ¶14 |

两个 duration 的公共类型取两个周期的最大公约数（[[time.traits]]），所以 `1s + 1ms` 的类型是 `milliseconds`，值是 1001ms。转换到公共类型只需要乘法，整数计数下不会丢失信息，但可能溢出。

duration 乘以一个数时，计数类型可能变宽：`1s * 1.5` 的类型是 `duration<double>`。

¶8 `d / s` 和 `d % s` 多了一条约束：`Rep2` 不是 duration 的特化。没有这条，`1s / 2ms` 会同时匹配"duration 除以数"和"duration 除以 duration"两个模板。

¶10 两个 duration 相除时，先都转换到公共类型，再把计数相除。`1s / 2ms` 问的是 1 秒里能放下几个 2 毫秒，结果是 500，没有单位。在 libc++ 上它的类型是 `long long`，这取决于 `seconds::rep` 和 `milliseconds::rep` 的选择，标准只规定了它们的最小位数。

`d1 % d2` 的结果是公共类型的 duration，常用来取一天之内的部分：`tp.time_since_epoch() % days{1}`。

所有整数运算都沿用内建运算的规则：除法向零截断（[[expr.mul]]），有符号溢出是未定义行为。

## 比较 [time.duration.comparisons]

¶2 `==` 和 `<` 先把两边转换到公共类型，再比较计数（¶3）。所以 `1s == 1000ms` 为真，`1999ms < 2s` 为真，比较的是物理时长。`>`、`<=`、`>=` 由 `<` 推出（¶4–¶6）。

¶7 `<=>` 要求公共类型的 `rep` 满足 `three_way_comparable`。对 `duration<double>`，结果是 `partial_ordering`，因为 NaN 和任何值都不可比较。

!!! lawyer "跨单位比较也可能溢出"
    `nanoseconds::max() == hours{3'000'000}` 要先把 `hours` 转换成 `nanoseconds`，这次乘法溢出了。结果是未定义行为，不是返回 `false`。

## 截断与取整 [time.duration.cast]

```cpp run ok title="rounding.cpp"
#include <chrono>
using namespace std::chrono;

static_assert(duration_cast<seconds>(-1500ms) == -1s);  // 向零
static_assert(floor<seconds>(-1500ms)         == -2s);  // 向负无穷
static_assert(ceil<seconds>(-1500ms)          == -1s);  // 向正无穷
static_assert(round<seconds>(1500ms)          ==  2s);  // 1.5 → 2
static_assert(round<seconds>(2500ms)          ==  2s);  // 2.5 → 2，取偶数
static_assert(round<seconds>(-2500ms)         == -2s);

int main() {}
```

### duration_cast（¶1–¶3）

¶2 令 `CF` 为换算系数 `ratio_divide<Period, ToDuration::period>`，`CR` 为中间计算类型 `common_type<ToDuration::rep, Rep, intmax_t>::type`。按 `CF` 分四种情形：

| 情形 | 计算 |
|---|---|
| ¶2.1 `CF` 是 1/1 | `static_cast<ToRep>(d.count())` |
| ¶2.2 只有分母是 1 | `static_cast<ToRep>(static_cast<CR>(d.count()) * CF::num)` |
| ¶2.3 只有分子是 1 | `static_cast<ToRep>(static_cast<CR>(d.count()) / CF::den)` |
| ¶2.4 其他 | `static_cast<ToRep>(static_cast<CR>(d.count()) * CF::num / CF::den)` |

¶3 的注总结了设计：所有转换都用 `static_cast`；编译期已知系数为 1 时省掉乘除；中间结果在至少 `intmax_t` 宽的 `CR` 中计算，最后一步才转换到目标类型。

由此可以得出几条结论：

- 整数情形下 `duration_cast` 向零截断，因为 ¶2.3 用的是内建的 `/`。`duration_cast<seconds>(-1500ms)` 是 `-1s`，不是 `-2s`。
- ¶2.4 先乘后除以保留精度，但乘法可能在 `CR` 中溢出。
- 浮点转整数的最后一步 `static_cast`，如果值超出了目标类型的范围，是未定义行为（[[conv.fpint]]）。

### floor、ceil、round（¶4–¶9）{{c++17}}

¶5 `floor<To>(d)` 返回 `To` 中满足 `t <= d` 的最大值，即向负无穷取整。¶7 `ceil<To>(d)` 返回满足 `t >= d` 的最小值，即向正无穷取整。

¶9 `round<To>(d)` 返回最接近 `d` 的值；有两个同样接近的值时，返回满足 `t % 2 == 0` 的那个。这种舍入法常叫银行家舍入，在大量取整后求和时不会累积出系统性的偏差。¶8 要求 `To::rep` 不是浮点类型。

处理时刻时最常用的是 `floor`。`floor<days>(system_clock::now())` 得到今天的零点（UTC）；如果换成 `duration_cast<days>`，1970 年以前的时刻会因为负数向零截断而得到明天的零点（见 [[time.point]]）。

### abs [time.duration.alg] {{c++17}}

¶1 `abs` 只接受有符号的 `Rep`。¶2 `d >= d.zero()` 时返回 `d`，否则返回 `-d`。和内建的 `abs(INT_MIN)` 一样，对 `min()` 求 `abs` 会溢出。

## 字面量 [time.duration.literals] {{c++14}}

```cpp
using namespace std::chrono_literals;
auto constexpr aday       = 24h;
auto constexpr lesson     = 45min;
auto constexpr halfanhour = 0.5h;
```

¶1 后缀 `h`、`min`、`s`、`ms`、`us`、`ns` 用在整数字面量上，分别得到 `hours`、`minutes`、`seconds`、`milliseconds`、`microseconds`、`nanoseconds`。¶2 用在浮点字面量上时，计数类型是一个未指定的浮点类型，所以 `0.5h` 表示半小时。

¶3 整数字面量的值无法用结果类型表示时，程序非良构。

¶8 的注说明，`s` 和 `basic_string` 的 `""s` 不冲突：一个作用于数字，一个作用于字符串字面量。微秒的后缀是 `us` 而不是 `µs`，因为字面量后缀必须是标识符，ASCII 字符输入起来最方便。

!!! impl "libc++ 不诊断字面量溢出"
    按 ¶3，`18'000'000'000'000'000'000h` 应当报错：它能放进 `unsigned long long`，放不进 `hours::rep`。本机 libc++ 直接用这个值构造 `hours`，编译通过，计数变成了 `-446744073709551616`。这是 libc++ 的不符合之处。

## 输出 [time.duration.io] {{c++20}}

```cpp run ok title="duration-io.cpp"
#include <chrono>
#include <iostream>
using namespace std::chrono;

int main() {
  std::cout << 42ms << ' ' << 3us << ' ' << 90min << ' ' << days{2} << '\n';
  std::cout << duration<int, std::ratio<1, 3>>{5} << ' ' << weeks{1} << '\n';
  std::cout << duration<double, std::milli>{1.5} << '\n';
}
```

本机 libc++ 输出 `42ms 3µs 90min 2d`、`5[1/3]s 1[604800]s` 和 `1.5ms`。

¶1 `os << d` 的效果是：在一个复制了 `os` 的格式标志、locale 和精度的字符串流中输出 `d.count()` 和单位后缀，再把整个字符串写入 `os`。先拼成一个字符串，是为了让 `setw` 作用于数值和后缀的整体。

后缀由约分后的周期决定（¶1.1–¶1.22）：

| 周期 | 后缀 |
|---|---|
| `atto`、`femto`、`pico`、`nano` | `as`、`fs`、`ps`、`ns` |
| `micro` | `µs` 或 `us`，由实现定义 |
| `milli`、`centi`、`deci`、`ratio<1>` | `ms`、`cs`、`ds`、`s` |
| `deca` 到 `exa` | `das`、`hs`、`ks`、`Ms`、`Gs`、`Ts`、`Ps`、`Es` |
| `ratio<60>`、`ratio<3600>`、`ratio<86400>` | `min`、`h`、`d` |
| 其他，分母为 1 | `[num]s` |
| 其他 | `[num/den]s` |

`weeks`、`months`、`years` 没有专门的后缀，分别显示为 `[604800]s`、`[2629746]s`、`[31556952]s`。

<details class="fine" markdown="1"><summary>其余条文</summary>

[[time.duration.general#4]]：duration 的成员除了计数类型自身的操作抛出的异常之外，不抛异常。计数是内建算术类型时，所有成员都不抛。

[[time.duration.general#5]]：默认的复制构造函数是不是 constexpr 函数，完全取决于复制 `rep_` 的那次初始化是否 constexpr-suitable（[[dcl.constexpr]]）。

[[time.duration.io#3]] 和第 4 段：`from_stream` 按 [[time.parse]] 的格式解析一个 duration；失败时设置 `failbit`，不修改目标。本机 libc++ 尚未实现。

</details>

## 历史

!!! history
    - C++11 通过 [[N2661]] 引入 `<chrono>`，`duration` 的隐式转换规则从那时起基本没变。
    - C++14 加入了 `h`、`min`、`s` 等字面量后缀。
    - C++17 的 [[P0092R1]] 加入了 `floor`、`ceil`、`round` 和 `abs`。在那之前只有向零截断的 `duration_cast`。
    - C++20 的 [[P0355R7]] 加入了日历和时区，同时给 duration 加上了流输出、`from_stream` 以及 `days`、`weeks`、`months`、`years` 这几个别名。

## 常见陷阱

!!! pitfall "隐式转换也会溢出"
    `nanoseconds` 的计数至少 64 位，2⁶³ 纳秒约等于 292 年。libstdc++ 的 `system_clock` 以纳秒计时，所以只能表示到 2262 年。

    ```cpp
    auto ns = duration_cast<nanoseconds>(years{300});   // UB：有符号溢出
    nanoseconds x = years{300};                         // 同样是 UB
    ```

    第二行更隐蔽。隐式转换的条件（¶3.2）只看周期是否成倍数，不看数值范围。用 UBSan 运行会报告 `signed integer overflow`；在常量表达式里，同样的溢出会让求值失败，编译器给出诊断。

!!! pitfall "用 int 作计数类型"
    2³¹ 毫秒约等于 24.8 天。一个运行一个月的服务如果用 `duration<int, milli>` 累计运行时间就会溢出。标准别名对位数有最低要求（[[time.syn]]），`milliseconds` 至少 45 位，优先使用它们。

!!! pitfall "整数 duration 的除法会截断"
    `seconds{1} / 2` 是 `0s`，`seconds{3} / seconds{2}` 是 `1`。需要小数时先转换成浮点 duration：`duration<double>{3s} / 2s` 是 `1.5`。

!!! pitfall "无符号计数类型"
    `duration<unsigned>{1} - duration<unsigned>{2}` 得到 4294967295 秒，`abs` 也不能用于无符号计数。时间差有正有负，计数类型应当有符号。`system_clock::rep` 就明确要求是有符号的（[[time.clock]]）。

!!! pitfall "count() 把单位丢掉了"
    `usleep(d.count())` 只有在 `d` 恰好是 `microseconds` 时才对。在接口边界上先转换到目标单位再取计数，写成 `usleep(duration_cast<microseconds>(d).count())`；更好的做法是让函数直接接受 duration。

## 思考题

!!! question "思考题 1"
    `seconds s = 1500ms;` 非良构。改成直接初始化 `seconds s{1500ms};` 呢？

<details markdown="1">
<summary>答案</summary>

同样非良构。转换构造函数不是 `explicit` 的，挡住它的是 ¶3 的约束：`milli` 除以 `ratio<1>` 的分母不是 1，计数类型又是整数，所以这个构造函数不参与重载决议，直接初始化也找不到可行的构造函数。要写成 `duration_cast<seconds>(1500ms)` 或 `floor<seconds>(1500ms)`。
</details>

!!! question "思考题 2"
    `1s / 2ms` 和 `1s / 2` 都是 duration 除以某个东西，为什么不会产生歧义？

<details markdown="1">
<summary>答案</summary>

¶8 给 duration 除以数的版本加了约束：`Rep2` 不是 duration 的特化。对 `1s / 2ms`，`Rep2` 推导为 `milliseconds`，约束不满足，只剩 duration 除以 duration 的版本。对 `1s / 2`，duration 除以 duration 的版本推导失败，只剩 duration 除以数的版本。
</details>

!!! question "思考题 3"
    `round<seconds>(2500ms)` 为什么是 `2s` 而不是 `3s`？

<details markdown="1">
<summary>答案</summary>

¶9：2s 和 3s 离 2.5s 一样近，这时返回满足 `t % 2 == 0` 的那个，也就是 2s。
</details>
