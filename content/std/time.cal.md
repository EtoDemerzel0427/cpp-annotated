---
title: 民用历法
summary: <chrono> 的公历类型：day、month、year、weekday 四个字段，last 与 weekday[n] 这样的星期选择器，以及九个组合类型；日期的字段式与序列式表示怎样互转，构造不检查、用 ok() 判断有效性的设计，"/" 日期语法，以及按月加减为什么会得到 2 月 31 日。
status: done
covers: *
papers: P0355R7
related: time.clock, time.point, time.duration, time.zone, time.format, time.parse, time.hash
tags: 标准库, chrono, 日期, 历法, 公历
updated: 2026-10-19
---

!!! tldr
    - 日期有两种表示：`sys_days` 是距 1970-01-01 的天数，适合按天计算；`year_month_day` 分别存年月日，适合取字段和按月、按年计算。两者可以隐式互转，代价只是一段整数运算。
    - 历法类型的构造从不检查，`2023y/February/29` 也能构造出来；用 `ok()` 判断是否有效，用 `/last` 或转换成 `sys_days` 来修正。
    - `2024y/January/31 + months{1}` 是无效的 2024-02-31。月末怎样处理由调用者决定：截到月末，或者转换成 `sys_days` 顺延到 3 月 2 日。
    - "/" 语法支持年/月/日、月/日/年、日/月/年三种顺序，但第一个 `/` 两边至少要有一个历法类型；`4/4/2016` 只是整数除法，结果是 0。
    - `month` 和 `weekday` 的加减按环取模，`day` 和 `year` 不取模；`weekday` 不能比较大小。

## 两种日期表示

```cpp run ok title="two-forms.cpp"
#include <chrono>
#include <iostream>
using namespace std::chrono;

int main() {
  year_month_day ymd = 2024y/February/27;
  sys_days sd = ymd;                        // 字段式 → 序列式：隐式
  sd += days{3};                            // 按天加：整数加法
  year_month_day later = sd;                // 序列式 → 字段式：隐式
  std::cout << later << ' ' << weekday{sd} << '\n';   // 2024-03-01 Fri
  std::cout << later.year() / later.month() / last << '\n';  // 2024/Mar/last
}
```

[[time.cal.general#1]] 只有一句话：本节的类型描述民用的公历，以及公历与 `sys_days`、`local_days` 的关系。

日期有两种表示，各有所长：

- **序列式**：`sys_days` 是 `time_point<system_clock, days>`，即一个"距 1970-01-01 多少天"的整数。按天加减、求两个日期相差几天、求星期几，都是一次整数运算。
- **字段式**（[[g:field-based-time-point]]）：`year_month_day` 分别存年、月、日。取年月日、按月或按年加减很方便；按天加减就麻烦了，要处理月末和闰年。

所以标准没有给 `year_month_day` 提供"加几天"的运算，而是让它和 `sys_days` 隐式互转，按天的运算交给 `sys_days`。两个方向的换算都是常数时间的算术，这要归功于 `system_clock` 被规定为不计闰秒的 Unix 时间（[[time.clock]]）。

## 十五个类型

| 类别 | 类型 | 表示 | 可比较大小 |
|---|---|---|---|
| 字段 | `day` | 月中第几天，通常 1–31 | 是 |
| | `month` | 1–12 | 是 |
| | `year` | −32767–32767 | 是 |
| | `weekday` | 0–6，周日到周六 | 否 |
| 星期选择器 | `weekday_indexed` | 第 n 个星期 X，n 为 1–5 | 否 |
| | `weekday_last` | 最后一个星期 X | 否 |
| 缺年份 | `month_day`、`month_day_last` | 每年的某月某日、某月最后一天 | 是 |
| | `month_weekday`、`month_weekday_last` | 每年某月的第 n 个或最后一个星期 X | 否 |
| 缺日 | `year_month` | 某年某月 | 是 |
| 完整日期 | `year_month_day` | 年/月/日 | 是 |
| | `year_month_day_last` | 某年某月最后一天 | 是 |
| | `year_month_weekday` | 某年某月第 n 个星期 X | 否 |
| | `year_month_weekday_last` | 某年某月最后一个星期 X | 否 |

此外还有 `last_spec`（[[time.cal.last#1]]），它是一个空类型，唯一的值是常量 `last`，表示一个序列中的最后一个：按上下文，可以是月末那一天，也可以是某月的最后一个星期 X。它的默认构造函数是 `explicit` 的，所以 `{}` 不能隐式转换成 `last_spec`，`ym / {}` 不会被解释成 `ym / last`。

每个类型的 overview 最后一段都规定它是平凡可复制的标准布局类。几乎所有操作都是 `constexpr noexcept` 的。在本机 libc++ 上，`year_month_day` 只占 4 个字节。

## 构造不检查，用 ok() 判断

```cpp run ok title="cal-ok.cpp"
#include <chrono>
using namespace std::chrono;

static_assert(!day{0}.ok() && day{31}.ok() && !day{32}.ok());
static_assert(!month{13}.ok());
static_assert((February/29).ok());                 // month_day：不知道年份，按 29 天算
static_assert((2024y/February/29).ok());           // 闰年
static_assert(!(2023y/February/29).ok());          // 平年
static_assert(!(2025y/February/Monday[5]).ok());   // 2025 年 2 月只有 4 个周一
static_assert(weekday{7} == Sunday);               // 7 规范化为 0

int main() {}
```

历法类型的构造函数从不检查，也从不抛异常。`day{40}`、`month{13}`、`2023y/February/29` 都能构造出来，每个类型都提供 `ok()` 告诉你值是否有效。这样设计有三个理由：

1. 构造只是存储，可以是 `constexpr noexcept` 的，适合常量表达式和性能敏感的代码。
2. `2024y/January/31 + months{1}` 先得到 2024-02-31，调用者可以自己决定怎么处理：截到月末、顺延到 3 月 2 日，或者报错。如果构造时就抛异常或者钳制取值，这些策略都无从实现。
3. 越界的值可以作为中间结果。`sys_days{2017y/January/32}` 恰好是 2 月 1 日（见下文），这在日期计算中很有用。

代价是使用之前要检查 `ok()`。对无效值做大多数运算，结果是未指定的，但不是未定义行为；流输出会附上 "is not a valid ..." 的字样。

| 类型 | `ok()` 为真的条件 |
|---|---|
| `day` | 1 ≤ d ≤ 31 |
| `month` | 1 ≤ m ≤ 12 |
| `year` | −32767 ≤ y ≤ 32767 |
| `weekday` | wd ≤ 6 |
| `weekday_indexed` | 星期有效，且 1 ≤ index ≤ 5 |
| `month_day` | 月有效，且日在 1 到该月天数之间，2 月按 29 天算 |
| `year_month_day` | 年、月有效，且日在 1 到该年该月的最后一天之间 |
| `year_month_weekday` | 各字段有效，且该月确实有第 index 个该星期 |

`month_day` 把 2 月按 29 天算（[[time.cal.md.members#4]]），因为它没有年份，`February/29` 作为一个闰年出生的人的生日是有效的。

## 四个字段类型

### day [time.cal.day]

[[time.cal.day.overview#1]] 规定 `day` 表示月中的一天，通常取 1 到 31，但可以存放这个范围之外的非负值。

`day` 可以和 `days` 做加减（[[time.cal.day.nonmembers#3]] 到第 6 段），两个 `day` 相减得到 `days`。加减不取模：`day{31} + days{5}` 是 `day{36}`，`ok()` 为假。构造函数接受 `unsigned`，¶1 [time.cal.day.members] 说值不在 0 到 255 之间时，存下的值未指定。

[[time.cal.day.nonmembers#10]] 定义了字面量后缀：`5d` 是 `day{5}`，不是 `days{5}`。

### month [time.cal.month]

`month` 的结构和 `day` 一样，区别在加减。[[time.cal.month.nonmembers#3]] 规定 `month + months` 用欧几里得除法取模，结果总在 1 到 12 之间，即使原来的值无效：`February + months{11} == January`。

¶6 两个 `month` 相减，返回 0 到 11 个月之间的值 `m`，满足 `y + m == x`：`January - February == months{11}`。月份是一个环，没有"负一个月"。

### year [time.cal.year]

[[time.cal.year.overview#1]] 规定 `year` 能表示 `min()` 到 `max()` 之间的值，即 −32767 到 32767（[[time.cal.year.members#19]] 和 ¶20）。−32768 被排除在外，这样 `-y` 总是有效。年份加减不取模。

[[time.cal.year.members#16]] 的 `is_leap()` 按 `y % 4 == 0 && (y % 100 != 0 || y % 400 == 0)` 计算，这是前推公历（proleptic Gregorian）：1582 年以前也按公历的规则算。¶10 [time.cal.year.nonmembers] 的字面量后缀 `y` 让 `2024y` 成为 `year{2024}`。

### weekday [time.cal.wd]

[[time.cal.wd.overview#1]] 规定 `weekday` 的 0 到 6 对应周日到周六。它只能判等，不能比较大小。注 1 解释了原因：一周从哪天开始没有普遍的共识，所以 `weekday` 的算术把一周当成一个没有起点和终点的环。

`weekday` 的构造函数（[[time.cal.wd.members]]）有几个细节：

- 第 1 段：`weekday{7}` 存为 0，所以用 ISO 编码（周日为 7）也能直接构造。
- 第 2 段：从 `sys_days` 构造是隐式的，算出那一天是星期几。第 3 段举例：1970-01-01 是周四，存 4。
- 第 4 段：从 `local_days` 构造是 `explicit` 的，第 5 段规定结果和用 `sys_days{dp.time_since_epoch()}` 构造相同。

¶18 `c_encoding()` 返回 0 到 6，周日为 0，和 C 的 `tm_wday` 一致；第 19 段的 `iso_encoding()` 返回 1 到 7，周一为 1，周日为 7，和 ISO 8601 一致。¶21–¶22 `wd[n]` 得到 `weekday_indexed`，`wd[last]` 得到 `weekday_last`。

[[time.cal.wd.nonmembers#2]] 规定 `weekday + days` 按 7 取模：`Monday + days{6} == Sunday`。按第 5 段，两个 `weekday` 相减，结果在 0 到 6 天之间：`Sunday - Monday == days{6}`。

为什么从 `sys_days` 的构造是隐式的，从 `local_days` 的构造却是显式的？这个规律贯穿整个历法库：`sys_days` 和历法类型隐式互转，`local_days` 必须显式转换，以免本地时间悄悄混进 UTC 的计算。`year_month_day` 等类型的构造函数和转换函数都遵循这个规律。

## 星期选择器和缺年份的类型

`weekday_indexed`（[[time.cal.wdidx]]）是一个星期加一个 1 到 5 的序号，表示某月的第 n 个星期 X，还不知道是哪个月。¶2 的例子用 `Sunday[2]` 构造它。`weekday_last`（[time.cal.wdlast]）表示某月的最后一个星期 X，通常写成 `Sunday[last]`。

缺年份的四个类型描述每年都有的某一天，比如节日和账单日：

| 类型 | 典型写法 | 比较 |
|---|---|---|
| `month_day` | `December/25`、`25d/December` | 先比月，再比日 |
| `month_day_last` | `February/last` | 比月 |
| `month_weekday` | `November/Thursday[4]` | 只能判等 |
| `month_weekday_last` | `May/Monday[last]` | 只能判等 |

它们缺了年份，不能转换成日期。需要时再用 `/` 补上年份：`2024y/(November/Thursday[4])`。`weekday_last`、`month_day_last`、`month_weekday`、`month_weekday_last` 都没有默认构造函数，必须说清是哪个星期、哪个月；`weekday_indexed` 和 `month_day` 有。

## "/" 日期语法 [time.cal.operators]

```cpp run ok title="slash-int.cpp"
#include <chrono>
using namespace std::chrono;

static_assert(2015/4/4 == 125);                  // 全是 int：内建除法
static_assert(2015y/4/4 == year_month_day{year{2015}, month{4}, day{4}});
static_assert(April/4/2016 == 2016y/April/4d);   // 月/日/年
static_assert(4d/April/2016 == 2016y/April/4d);  // 日/月/年
static_assert(4/4/2016 == 0);                    // 美式顺序，但全是 int

int main() {}
```

¶1 一组重载的 `operator/` 提供了创建日期的常规写法。第 2 段的注说明，年、月、日可以按三种顺序书写：

```text
year/month/day      2024y/February/29
month/day/year      February/29/2024
day/month/year      29d/February/2024
```

需要"日"的位置，都可以换成 `last`、`weekday[i]` 或 `weekday[last]`。第 3 段的注补充，少写一个 `/` 就得到部分日期：`2015y/April` 是 `year_month`，`April/4` 和 `4d/April` 是 `month_day`。

¶5–¶44 的四十个重载可以归纳成一条规则：第一个 `/` 的两个操作数中至少有一个是历法类型，由它决定另一边的 `int` 表示什么。

| 第一个 `/` 的操作数 | 结果 | `int` 的含义 |
|---|---|---|
| `year / month`、`year / int` | `year_month` | 月 |
| `month / day`、`month / int` | `month_day` | 日 |
| `int / day`、`day / month`、`day / int` | `month_day` | 月 |
| `month / last`、`int / last`、`last / month`、`last / int` | `month_day_last` | 月 |
| `month / weekday_indexed`、`int / weekday_indexed` 等 | `month_weekday` | 月 |
| `year_month / day`、`year_month / int` | `year_month_day` | 日 |
| `year / month_day`、`int / month_day`、`month_day / int` 等 | `year_month_day` | 年 |
| `year_month / last`、`year / month_day_last` 等 | `year_month_day_last` | 年 |
| `year_month / weekday_indexed`、`year / month_weekday` 等 | `year_month_weekday` | 年 |
| `year_month / weekday_last`、`year / month_weekday_last` 等 | `year_month_weekday_last` | 年 |

¶4 的例子正好覆盖了几种边界情况：

```cpp
auto a = 2015/4/4;          // a == int(125)
auto b = 2015y/4/4;         // b == year_month_day{year(2015), month(4), day(4)}
auto c = 2015y/4d/April;    // error: 第一个 / 没有可行的 operator/
auto d = 2015/April/4;      // error: 第一个 / 没有可行的 operator/
```

- `a` 的两个 `/` 都只有 `int`，是内建的整数除法：2015/4 是 503，503/4 是 125。
- `b` 的 `2015y/4` 匹配 `year / int`，得到 `year_month`，4 表示月；再 `/4` 匹配 `year_month / int`，得到 `year_month_day`。
- `c` 需要 `year / day`，没有这个重载，"2015 年 4 日"不是任何一种顺序的开头。
- `d` 需要 `int / month`，也没有这个重载。原因是它有歧义：按日/月/年的顺序，开头的 `int` 应该是日；按年/月/日的顺序，应该是年。标准干脆不提供，要求写 `2015y` 或 `4d`。

!!! pitfall "编译通过，结果却是一个整数"
    `auto d = 4/4/2016;` 不会报错，`d` 是 `int` 类型的 0。只要第一个 `/` 两边有一个历法类型，例如 `2016y`、`April`、`4d`，后面的 `int` 就会被正确解释。年份总带 `y` 后缀，或者月份总用具名常量，就不会出这种错。

## year_month 和按月加减 [time.cal.ym]

[[time.cal.ym.overview#1]] 规定 `year_month` 表示某年某月，日未指定，是一个分辨率为月的字段式时间点。

`year_month` 可以加减 `months` 和 `years`，两个 `year_month` 相减得到 `months`（[[time.cal.ym.nonmembers#10]]）。按第 4 段，`ym + dm` 返回满足 `z.ok() && z - ym == dm` 的值 `z`，第 5 段要求复杂度与 `dm` 的大小无关，不能一个月一个月地循环。

### 那条奇怪的约束

所有接受 `months` 的 `+`、`-`、`+=`、`-=` 都带着同一条约束，例如 [[time.cal.ym.nonmembers#3]]：

!!! std
    If the argument supplied by the caller for the months parameter is convertible to years, its implicit conversion sequence to years is worse than its implicit conversion sequence to months.

意思是：如果实参能转换到 `years`，只有当它到 `years` 的隐式转换序列比到 `months` 的差时，接受 `months` 的重载才参与重载决议。

问题出在 `years` 能隐式转换成 `months`，因为一年正好是 12 个月。假设用户定义了 `decades = duration<int, ratio_multiply<years::period, ratio<10>>>`：它既能隐式转换成 `years`，也能隐式转换成 `months`，两条都是用户定义转换，重载决议分不出好坏（[[over.ics.rank]]），`ymd + decades{1}` 就有歧义。

有了这条约束，凡是能转换成 `years`、而转换成 `months` 又不比它更好的实参，`months` 重载都退出，`ymd + decades{1}` 就无歧义地选中 `years` 重载，按年相加。`years{1}` 本身也一样：它到 `years` 是恒等转换，到 `months` 要经过用户定义转换，`months` 重载退出。结果是能当作年数的实参一律按年处理。

!!! impl "libc++ 尚未实现这条约束"
    截至写作时，libc++ 把这些运算符写成普通的非模板函数，没有实现这条约束。`2024y/January/1 + decades{1}` 在本机报错 `use of overloaded operator '+' is ambiguous`，候选是接受 `months` 和接受 `years` 的两个 `operator+`。按标准它应当选择 `years` 版本。

## year_month_day [time.cal.ymd]

这是最常用的历法类型。[[time.cal.ymd.overview#1]] 的注 1 说明，它支持按年和按月的运算，不支持按天的运算；按天运算要先转换成 `sys_days`。

### 和 sys_days 互转 [time.cal.ymd.members]

¶3 `year_month_day` 可以从 `sys_days` 隐式构造。第 4 段保证往返无损：对任何 `ok()` 为真的 `ymd`，`ymd == year_month_day{sys_days{ymd}}`。¶5 从 `local_days` 构造是 `explicit` 的。¶2 从 `year_month_day_last` 也可以隐式构造，注 1 说这比经由 `sys_days` 中转更高效。

¶19 `year_month_day` 可以隐式转换为 `sys_days`，分三种情况：

- `ok()` 为真时，返回距纪元的天数，1970 年以前为负数；
- 否则如果年和月有效，返回 `sys_days{y/m/1d} + (d - 1d)`，也就是日字段超出月末时按天顺延；
- 否则返回值未指定。

¶21 的例子展示了第二种情况：

```cpp
static_assert(year_month_day{sys_days{2017y/January/0}}  == 2016y/December/31);
static_assert(year_month_day{sys_days{2017y/January/31}} == 2017y/January/31);
static_assert(year_month_day{sys_days{2017y/January/32}} == 2017y/February/1);
```

1 月 0 日是 1 月 1 日的前一天，1 月 32 日是 1 月 31 日的后一天。借助这条顺延规则，`sys_days` 可以把越界的日期规范化。

¶20 规定，`days{-12687428}` 到 `days{11248737}` 之间的 `sys_days`，转换成 `year_month_day` 再转换回来，值不变。这个区间正好对应 `year` 的 −32767 到 32767。¶22 转换为 `local_days` 是 `explicit` 的。

### 按月、按年加减 [time.cal.ymd.nonmembers]

```cpp run ok title="month-end.cpp"
#include <chrono>
#include <iostream>
using namespace std::chrono;

int main() {
  auto d = 2024y/January/31 + months{1};
  std::cout << d << '\n';                     // 2024-02-31 is not a valid date
  std::cout << sys_days{d} << '\n';           // 2024-03-02：按 ¶19 顺延
  if (!d.ok()) d = d.year()/d.month()/last;   // 另一种策略：截到月末
  std::cout << d << '\n';                     // 2024-02-29

  std::cout << (2024y/February/29 + years{1}).ok() << '\n';  // 0：2025-02-29 无效
}
```

¶4 规定 `ymd + months` 等于 `(ymd.year() / ymd.month() + dm) / ymd.day()`，日字段原样保留。第 5 段的注说，只有日在 1 到 28 之间时，结果才一定有效。

¶10 规定 `ymd + years` 等于 `(ymd.year() + dy) / ymd.month() / ymd.day()`。第 11 段的注说，2 月 29 日加若干年，结果可能无效。

1 月 31 日加一个月是几号，没有唯一正确的答案。截到月末（2 月 29 日）、顺延（3 月 2 日）、报错，各适合不同的业务。标准让 `+` 只做字段运算，把策略留给调用者，用 `ok()`、`/last` 和 `sys_days{}` 组合出需要的语义。

## 其他三种完整日期

### year_month_day_last [time.cal.ymdlast]

[[time.cal.ymdlast.overview#1]] 规定它表示某年某月的最后一天，即 `month_day_last` 加上年份，可以比较大小。

[[time.cal.ymdlast.members#15]] 的 `day()` 在 `ok()` 时返回该月最后一天，第 16 段的注说这个值可以按需计算。它可以隐式转换为 `sys_days`（¶17），转换为 `local_days` 是 `explicit` 的。

它和 `year_month_day` 的关键区别在按月加减。[[time.cal.ymdlast.nonmembers#4]] 规定 `ymdl + months` 等于 `(y/m + dm) / last`，结果仍然是月末。`2024y/January/last + months{1}` 是 2024 年 2 月的最后一天，即 29 日，总是有效。需要"每月最后一天"这样的序列时，用 `year_month_day_last` 累加。

### year_month_weekday [time.cal.ymwd]

[[time.cal.ymwd.overview#1]] 规定它表示某年某月的第 n 个星期 X，只能判等。

按 [[time.cal.ymwd.members#2]]，它可以从 `sys_days` 隐式构造，第 3 段保证对 `ok()` 为真的值往返无损；从 `local_days` 构造是 `explicit` 的。

¶20 转换为 `sys_days` 时，如果年、月和星期都有效，结果是该月第一个星期 X 之后 `(index - 1) * 7` 天；index 为 0 时，结果是第一个星期 X 之前 7 天；否则未指定。这里不要求 index 不超过 5：在只有 4 个周一的月份里，`Monday[5]` 会顺延到下个月。

¶22 `ok()` 要求各字段有效，并且确实表示一个有效的日期，即该月有第 index 个星期 X。

[[time.cal.ymwd.nonmembers#3]] 和第 8 段规定，按月、按年加减时保留的是"第 n 个星期 X"，而不是日号。所以 `2024y/November/Thursday[4] + years{1}` 是 2025 年 11 月的第四个星期四。

### year_month_weekday_last [time.cal.ymwdlast]

它表示某年某月的最后一个星期 X。[[time.cal.ymwdlast.members#16]] 规定，`ok()` 时它转换为该月最后一个星期 X 的 `sys_days`。按月、按年加减时，保留的是"最后一个星期 X"。

```cpp run ok title="holidays.cpp"
#include <chrono>
#include <iostream>
using namespace std::chrono;

int main() {
  for (auto y = 2024y; y <= 2025y; ++y) {
    sys_days thanksgiving = y/November/Thursday[4];   // 美国感恩节
    sys_days memorial     = y/May/Monday[last];       // 美国阵亡将士纪念日
    sys_days eom          = y/February/last;          // 2 月最后一天
    std::cout << thanksgiving << ' ' << memorial << ' ' << eom << ' '
              << weekday{eom} << '\n';
  }
  auto gap = sys_days{2024y/December/25} - sys_days{2024y/January/1};
  std::cout << gap << '\n';                           // 359d
}
```

<details class="fine" markdown="1"><summary>其余条文</summary>

各类型的流输出：`day` 输出两位数（`%d`），`month` 输出 locale 的月份缩写（`%b`），`year` 输出至少四位（`%Y`），`weekday` 输出 locale 的星期缩写（`%a`），`weekday_indexed` 输出如 `Sun[2]`，`year_month_day` 输出 `%F`（如 `2024-02-29`）。值无效时附上 "is not a valid ..." 的说明。

各类型的 `from_stream` 都按 [[time.parse]] 解析；无法解析出有效值时设置 `failbit`，不修改目标。

`weekday_indexed` 的构造函数（[[time.cal.wdidx.members#1]]）在星期无效、或者序号不在 0 到 7 之间时，存下的值未指定。

`day`、`month`、`year` 的前置和后置 `++`、`--` 以及复合赋值，都按对应的 `+`、`-` 定义（各类型的 members 子条款）。

</details>

## 常见陷阱

!!! pitfall "在 sys_days 上加 years"
    `sys_days{2024y/February/29} + years{1}` 能编译，但 `years{1}` 是平均年长，即 365.2425 天。结果的类型是精度为 216 秒的 `sys_time`，值是 2025-02-28 05:49:12。按日历加一年，应当在字段式类型上做：`2024y/February/29 + years{1}`，然后检查 `ok()`。同理，`months{1}` 是 30.436875 天。

!!! pitfall "weekday 不能比较大小"
    `Monday < Friday` 非良构。如果业务上确实以周一为一周的开始，比较 `wd.iso_encoding()`；以周日为开始，比较 `c_encoding()`。

!!! pitfall "默认构造的历法对象没有初始化"
    `day`、`month`、`year`、`weekday`、`year_month_day` 等的默认构造函数都是 `= default`，和 `int` 一样不初始化。局部变量 `year_month_day d;` 的字段值不确定，C++26 起读取它得到错误值（[[basic.indet]]）。

!!! pitfall "对无效值求 sys_days"
    对 `ok()` 为假的对象求 `sys_days`、做差等，多数情况下结果未指定，例如 [[time.cal.month.nonmembers#6]] 和 [[time.cal.ymd.members#19]] 的最后一种情况。这不是未定义行为，但结果没有意义。`month` 和 `weekday` 的 `+` 是例外，它们对无效值也给出范围内的结果。

## 思考题

!!! question "思考题 1"
    `sys_days{2024y/February/30}` 是哪一天？`sys_days{2024y/month{13}/1}` 呢？

<details markdown="1">
<summary>答案</summary>

前者的年和月有效、日无效，按 [[time.cal.ymd.members#19]] 返回 `sys_days{2024y/February/1} + days{29}`，即 2024-03-01。后者的月无效，¶19 说返回值未指定。
</details>

!!! question "思考题 2"
    为什么 `month + months` 取模，而 `day + days`、`year + years` 不取模？

<details markdown="1">
<summary>答案</summary>

月份和星期构成环：12 月之后是 1 月，周六之后是周日。对孤立的 `month` 字段加一个月，取模是唯一合理的语义，年份的进位交给 `year_month` 处理。日没有固定的周期，一个月有 28 到 31 天，`day` 不知道自己属于哪个月，无法正确取模，所以只做简单的加减，留给 `ok()` 判断。年是没有边界的线性量，也不需要取模。
</details>

!!! question "思考题 3"
    `year_month_weekday{sys_days{2025y/February/Monday[5]}}` 等于 `2025y/February/Monday[5]` 吗？

<details markdown="1">
<summary>答案</summary>

不等于。2025 年 2 月只有 4 个周一，`2025y/February/Monday[5]` 的 `ok()` 为假。按 [[time.cal.ymwd.members#20]]，它转换成 `sys_days` 时是第一个周一（2 月 3 日）之后 28 天，即 2025-03-03。从这个 `sys_days` 构造的 `year_month_weekday` 是 `2025y/March/Monday[1]`。¶3 的往返保证只对 `ok()` 为真的值成立。
</details>
