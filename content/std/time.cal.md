---
title: 民用历法
summary: 15 个公历类型如何分工——day/month/year/weekday 四个字段类型、weekday_indexed/last 两个"星期选择器"、9 个组合类型；字段式（year_month_day）与序列式（sys_days）的互转；"先构造、后 ok()"的有效性模型；"/" 日期语法的三种顺序与 int 陷阱；按月加减为什么会得到 2 月 31 日
status: done
covers: *
papers: P0355R7
related: time.clock, time.point, time.duration, time.zone, time.format, time.parse, time.hash
tags: 标准库, chrono, 日期, 历法, 公历
updated: 2026-10-18
---

[time.cal] ¶1（[time.cal.general]）只有一句：本节的类型描述民用（公历）历法，以及它与 `sys_days`、`local_days` 的关系。

整个历法层建立在一个设计决策上：**日期有两种表示，各擅所长，互相转换很便宜**。

- **序列式**（serial）：`sys_days` = `time_point<system_clock, days>`，一个整数"距 1970-01-01 多少天"。按天加减、求两个日期相差几天、求星期几，都是一次整数运算。
- **字段式**（[[g:field-based-time-point]]）：`year_month_day`，分别存年、月、日。取年月日、按月或按年加减很方便，按天加减则很麻烦（要处理月末、闰年）。

所以标准**没有**给 `year_month_day` 提供"加几天"的运算，而是让它与 `sys_days` 隐式互转，按天的运算交给 `sys_days`。两个方向的转换都是 O(1) 的纯算术（Howard Hinnant 的 `days_from_civil` / `civil_from_days` 算法），这正得益于 `system_clock` 被规定为 Unix 时间（[[time.clock]]）。

## 15 个类型的分工

| 类别 | 类型 | 表示 | 有序？ |
|---|---|---|---|
| 字段 | `day` | 月中第几天，通常 1–31 | 是 |
| | `month` | 1–12 | 是 |
| | `year` | −32767–32767 | 是 |
| | `weekday` | 0–6（周日–周六） | **否** |
| 星期选择器 | `weekday_indexed` | "第 n 个星期 X"（n 为 1–5） | 否 |
| | `weekday_last` | "最后一个星期 X" | 否 |
| 缺年份 | `month_day`、`month_day_last`、`month_weekday`、`month_weekday_last` | 每年都有的日子，如 2 月 29 日、11 月第 4 个周四 | 前两个有序 |
| 缺日 | `year_month` | 某年某月 | 是 |
| 完整日期 | `year_month_day` | 年/月/日 | 是 |
| | `year_month_day_last` | 某年某月最后一天 | 是 |
| | `year_month_weekday` | 某年某月第 n 个星期 X | 否 |
| | `year_month_weekday_last` | 某年某月最后一个星期 X | 否 |

另有 `last_spec`（[time.cal.last]）：一个空类型，唯一的值是常量 `last`，表示"序列中的最后一个"——依上下文是月末那一天，或某月的最后一个星期 X。它的默认构造函数是 `explicit` 的，所以 `{}` 不能隐式转换成 `last_spec`：`ym / {}` 不会被悄悄解释成 `ym / last`。

所有类型都是**平凡可复制**、**标准布局**的类（各 overview 最后一段），几乎所有操作都是 `constexpr noexcept`。在 libc++ 上 `year_month_day` 只占 4 字节。

## 有效性模型："先构造，后 ok()"

历法类型的构造函数**从不检查**，也从不抛异常。`day{40}`、`month{13}`、`2023y/February/29` 都能构造出来，每个类型提供 `ok()` 告诉你值是否有效。

为什么这样设计？

1. **性能**：构造是 `noexcept` 的纯存储，可以在常量表达式和热路径中使用。
2. **组合性**：`2024y/January/31 + months{1}` 先得到 2024-02-31，调用者可以自己决定怎么处理——截到月末、顺延到 3 月 2 日、还是报错。如果构造时就抛异常或钳制，这些策略都无从实现。
3. **允许"溢出"作为中间值**：`sys_days{2017y/January/32}` 恰好是 2 月 1 日（见下文），这在日期运算中很有用。

代价是：**使用之前必须检查 `ok()`**。无效值在多数运算中的结果是未指明的（{{unspec}}），不是 UB；流输出会附带 "is not a valid ..." 字样。

| 类型 | `ok()` 为真的条件 |
|---|---|
| `day` | 1 ≤ d ≤ 31 |
| `month` | 1 ≤ m ≤ 12 |
| `year` | −32767 ≤ y ≤ 32767 |
| `weekday` | wd ≤ 6 |
| `weekday_indexed` | `weekday().ok()` 且 1 ≤ index ≤ 5 |
| `month_day` | 月有效，且日在 [1, 该月天数]，**2 月按 29 天算** |
| `year_month_day` | 年、月有效，且日在 [1, 该年该月最后一天] |
| `year_month_weekday` | 各字段有效，且该月确实有第 index 个该星期 |

`month_day` 把 2 月按 29 天算（[time.cal.md.members] ¶4），因为没有年份，`February/29` 在闰年是有效的生日。

```cpp title="cal-ok.cpp" ok
#include <chrono>
using namespace std::chrono;

static_assert(!day{0}.ok() && day{31}.ok() && !day{32}.ok());
static_assert(!month{13}.ok());
static_assert((February/29).ok());                 // month_day：不知道年份，按 29 天
static_assert((2024y/February/29).ok());           // 闰年
static_assert(!(2023y/February/29).ok());          // 平年
static_assert(!(2025y/February/Monday[5]).ok());   // 2025 年 2 月只有 4 个周一
static_assert(weekday{7} == Sunday);               // 7 被规范化为 0

int main() {}
```

## 四个字段类型

### day（[time.cal.day]）

- overview ¶1：表示月中的一天，通常 1–31，但可以存放范围外的非负值。可以用任意 `unsigned` 构造，值会被截断到内部存储（典型地是 `unsigned char`）。满足 *Cpp17EqualityComparable* 和 *Cpp17LessThanComparable*，与 `days` 做算术。
- members ¶1：`explicit day(unsigned d)`；`d` 不在 [0, 255] 时存放的值未指明。
- ¶2–¶13：`++`、`--`、`+= days`、`-= days`；**不取模**——`day{31} + days{5}` 是 `day{36}`，`!ok()`。
- ¶14–¶15：`explicit operator unsigned()`；`ok()`。
- nonmembers ¶1–¶6：`==`、`<=>`（`strong_ordering`）；`day ± days`；`day − day` 得到 `days`。
- ¶7：输出两位数（`%d`），无效时附 " is not a valid day"。
- ¶8–¶9：`from_stream`。¶10：字面量 `operator""d`，`5d` 是 `day{5}`——注意不是 `days{5}`。

### month（[time.cal.month]）

结构与 `day` 相同，关键区别在算术：

- nonmembers ¶3：`month + months` 用**欧几里得取模**：`month{modulo(m + (n − 1), 12) + 1}`，结果总在 [1, 12]，即使原值无效。例：`February + months{11} == January`。
- ¶6：`month − month` 返回 [0, 11] 范围内的 `months`，使得 `y + m == x`。例：`January − February == months{11}`——月份是环，没有"负 1 个月"。
- ¶7：输出用 locale 的缩写月名 `%b`（受 `L` 与 locale 影响），无效时输出 "13 is not a valid month"。

### year（[time.cal.year]）

- overview ¶1：范围 [`min()`, `max()`]，即 [−32767, 32767]（members ¶19–¶20）。用 `int` 构造，超出 [−32767, 32767] 时值未指明（¶1）。−32768 被排除在外，是为了让 `-year` 总是有效。
- members ¶14–¶15：一元 `+`、`-`。
- ¶16：`is_leap()`：`y % 4 == 0 && (y % 100 != 0 || y % 400 == 0)`——**前推公历**（proleptic Gregorian），1582 年以前也按公历规则算。
- nonmembers ¶3–¶6：`year ± years`、`year − year`。不取模。
- ¶7：输出 `%Y`（至少 4 位）。¶10：字面量 `operator""y`，`2024y`。

### weekday（[time.cal.wd]）

- overview ¶1：0–6 对应周日到周六。只满足 *Cpp17EqualityComparable*。注 1：**不**满足 *Cpp17LessThanComparable*，因为"一周从哪天开始"没有普遍共识；`weekday` 的算术把一周当成没有起点和终点的环。
- members ¶1：`explicit weekday(unsigned wd)`：`wd == 7` 时存 0。这让 ISO 编码（周日 = 7）也能直接构造。
- ¶2–¶3：`weekday(const sys_days&)` **隐式**——从日期算星期几。例：1970-01-01 是周四，存 4。
- ¶4–¶5：`explicit weekday(const local_days&)`——值与从 `sys_days{dp.time_since_epoch()}` 构造相同。
- ¶18–¶19：`c_encoding()` 返回 0–6（周日 = 0，对应 C 的 `tm_wday`）；`iso_encoding()` 返回 1–7（周一 = 1，周日 = 7，对应 ISO 8601）。
- ¶21–¶22：`wd[n]` 得到 `weekday_indexed`；`wd[last]` 得到 `weekday_last`。
- nonmembers ¶2：`weekday + days` 模 7。例：`Monday + days{6} == Sunday`。¶5：`weekday − weekday` 在 [0, 6]：`Sunday − Monday == days{6}`。
- ¶6：输出 locale 的缩写星期名 `%a`。

为什么从 `sys_days` 的构造是隐式的，而从 `local_days` 的是显式的？这是贯穿整个历法层的规律：**`sys_days` 是历法类型的"母语"，隐式互转；`local_days` 需要显式转换**，以免本地时间悄悄混进 UTC 计算。`year_month_day`、`year_month_weekday` 的构造函数与转换函数都遵循这个规律。

## 星期选择器（[time.cal.wdidx]、[time.cal.wdlast]）

- `weekday_indexed`（overview ¶1–¶3）：一个 `weekday` 加一个 1–5 的序号，表示"某月的第 n 个星期 X"，还不知道是哪个月。通常用 `Sunday[2]` 构造（¶2 的例子）。members ¶1：`!wd.ok()` 或 index 不在 [0, 7] 时存放的值未指明；¶4：`ok()` 要求 index 在 [1, 5]。nonmembers ¶2：输出 `Sun[2]`。
- `weekday_last`（overview ¶1–¶3）：表示某月的最后一个星期 X。`explicit` 构造，通常写 `Sunday[last]`。没有默认构造函数——"最后一个星期几"必须指定是星期几。

## 缺年份的四个类型

| 类型 | 典型写法 | 说明 | 段落 |
|---|---|---|---|
| `month_day` | `December/25`、`25d/December` | 有序（先比月再比日）；`ok()` 把 2 月当 29 天 | [time.cal.md] |
| `month_day_last` | `February/last` | 某月最后一天；有序；只有 `explicit` 构造 | [time.cal.mdlast] ¶1–¶9 |
| `month_weekday` | `November/Thursday[4]` | 某月第 n 个星期 X；只可判等 | [time.cal.mwd] |
| `month_weekday_last` | `May/Monday[last]` | 某月最后一个星期 X；只可判等 | [time.cal.mwdlast] |

它们自己不能转换成日期——缺了年份。用途是描述"每年的某一天"（节日、账单日），需要时再用 `/` 补上年份：`2024y/(November/Thursday[4])`。注意 `month_day_last`、`month_weekday`、`month_weekday_last`、`weekday_last` **没有默认构造函数**，而 `month_day` 有。

## year_month（[time.cal.ym]）

- overview ¶1：某年某月，日未指定。是分辨率为月的基于字段的时间点。有序。
- members ¶4–¶13 / nonmembers ¶3–¶13：`± months`、`± years`；`year_month − year_month` 得到 `months`（¶10）。¶4–¶5：`ym + dm` 返回使 `z.ok() && z − ym == dm` 的值，复杂度 O(1)（不是循环加 12 次）。

### 那条奇怪的 *Constraints*

`year_month`、`year_month_day` 等所有接受 `months` 的 `+`、`-`、`+=`、`-=` 都带着同一条约束（例如 [time.cal.ym.members] ¶4）：

!!! std
    If the argument supplied by the caller for the months parameter is convertible to years, its implicit conversion sequence to years is worse than its implicit conversion sequence to months.

    如果调用者给 months 形参的实参能转换到 years，那么只有当它到 years 的隐式转换序列**劣于**到 months 的转换序列时，这个 months 重载才参与决议。

问题出在 `years` 可以隐式转换成 `months`（1 年 = 12 个月，整数倍）。考虑用户定义的 `decades = duration<int, ratio_multiply<years::period, ratio<10>>>`：它既能隐式转换成 `years`，也能隐式转换成 `months`，两者都是用户定义转换，重载决议无法区分（[[over.ics.rank]]），`ymd + decades{1}` 就会歧义。这条约束的效果是：凡是能转成 `years` 而转 `months` 又不比它更好的实参，`months` 重载就退出，于是 `ymd + decades{1}` 无歧义地选中 `years` 重载，按年相加。对 `years{1}` 本身也一样：它到 `years` 是恒等转换，到 `months` 是用户定义转换，`months` 重载退出——这条约束保证了“能当作年的实参，一律按年处理”。

!!! impl "libc++ 尚未实现这条约束"
    截至写作时，libc++ 把这些运算符写成普通的非模板函数，没有实现上述约束。`2024y/January/1 + decades{1}` 在 libc++ 上报错：`use of overloaded operator '+' is ambiguous`，候选是 `operator+(const year_month_day&, const months&)` 与 `operator+(const year_month_day&, const years&)`。按标准它应当选择 `years` 版本。

## year_month_day（[time.cal.ymd]）

这是最常用的历法类型。

### 构造与转换（members ¶1–¶5、¶19–¶22）

- ¶1：由 `year`、`month`、`day` 构造。
- ¶2：从 `year_month_day_last` **隐式**构造。注 1：这比经由 `sys_days` 中转更高效。
- ¶3–¶4：从 `sys_days` **隐式**构造。*Remarks*：对任何 `ok()` 的 `ymd`，`ymd == year_month_day{sys_days{ymd}}`——往返无损。
- ¶5：从 `local_days` **显式**构造。
- ¶19：**隐式**转换为 `sys_days`。`ok()` 时返回距纪元的天数（1970 年前为负）；否则若年、月有效，返回 `sys_days{y/m/1d} + (d − 1d)`——**即日字段"溢出"时按天顺延**；再否则值未指明。
- ¶20：*Remarks*：`sys_days` 在 [`days{-12687428}`, `days{11248737}`] 范围内时，转成 `year_month_day` 再转回来值不变。这个区间正好对应 `year` 的 [−32767, 32767]。
- ¶21 的例子：

```cpp
static_assert(year_month_day{sys_days{2017y/January/0}}  == 2016y/December/31);
static_assert(year_month_day{sys_days{2017y/January/31}} == 2017y/January/31);
static_assert(year_month_day{sys_days{2017y/January/32}} == 2017y/February/1);
```

`January/0` 是"1 月 1 日的前一天"，`January/32` 是"1 月 31 日的后一天"——¶19 的顺延规则让 `sys_days` 成为一个"规范化器"。

- ¶22：**显式**转换为 `local_days`。¶23：`ok()`，见上表。

### 算术（nonmembers ¶3–¶13）

- ¶4：`ymd + months` = `(ymd.year()/ymd.month() + dm) / ymd.day()`——**日字段原样保留**。¶5 注 1：只有当日在 [1, 28] 时，结果才保证 `ok()`。
- ¶10：`ymd + years` = `(ymd.year() + dy) / ymd.month() / ymd.day()`。¶11 注 2：2 月且日不在 [1, 28] 时（即 2 月 29 日），结果可能 `!ok()`。

所以：

```cpp title="month-end.cpp" ok
#include <chrono>
#include <iostream>
using namespace std::chrono;

int main() {
    auto d = 2024y/January/31 + months{1};
    std::cout << d << '\n';                       // 2024-02-31 is not a valid date
    std::cout << sys_days{d} << '\n';             // 2024-03-02：按 ¶19 顺延
    if (!d.ok()) d = d.year()/d.month()/last;     // 策略之一：截到月末
    std::cout << d << '\n';                       // 2024-02-29

    std::cout << (2024y/February/29 + years{1}).ok() << '\n';   // 0：2025-02-29 无效
}
```

"1 月 31 日加一个月是几号"没有唯一正确答案：截到月末（2 月 29 日）、顺延（3 月 2 日）、报错，各有各的业务场景。标准让 `+` 只做"字段运算"，把策略留给调用者，用 `ok()` 和 `/last`、`sys_days{}` 这几个工具组合出想要的语义。

- ¶14：输出 `%F`（`2024-02-29`），无效时附 " is not a valid date"。

## 其余三个完整日期类型

### year_month_day_last（[time.cal.ymdlast]）

- overview ¶1：某年某月的最后一天。`month_day_last` 加上年份。有序。
- members ¶15–¶16：`day()` 在 `ok()` 时返回该月最后一天，否则未指明；注：可以按需计算。
- ¶17：隐式转换为 `sys_days{year()/month()/day()}`；¶18：显式转换为 `local_days`。
- nonmembers ¶4：`ymdl + months` = `(y/m + dm) / last`——**仍然是月末**。这是它与 `year_month_day` 的关键区别：`2024y/January/last + months{1}` 是 2024 年 2 月最后一天（29 日），总是有效。

需要"每月最后一天"的序列时，用 `year_month_day_last` 做累加，而不是 `year_month_day`。

### year_month_weekday（[time.cal.ymwd]）

- overview ¶1：某年某月第 n 个星期 X。只可判等。
- members ¶2–¶3：从 `sys_days` 隐式构造，往返无损。¶4：从 `local_days` 显式构造。
- ¶20：转换为 `sys_days`：年、月、星期有效时，返回该月第一个星期 X 之后 `(index − 1) * 7` 天；**index 为 0 时返回第一个星期 X 之前 7 天**；否则未指明。注意这里不要求 index ≤ 5——`Monday[5]` 在只有 4 个周一的月份会顺延到下个月。
- ¶22：`ok()`：各字段有效，且确实表示一个有效日期（该月有第 index 个星期 X）。
- nonmembers ¶3、¶8：按月、按年加减时**保留"第 n 个星期 X"**，而不是保留日号——`2024y/November/Thursday[4] + years{1}` 是 2025 年感恩节。

### year_month_weekday_last（[time.cal.ymwdlast]）

- 某年某月最后一个星期 X。¶16：`ok()` 时转换为该月最后一个星期 X 对应的 `sys_days`。按月、按年加减时保留"最后一个星期 X"。

```cpp title="holidays.cpp" ok
#include <chrono>
#include <iostream>
using namespace std::chrono;

int main() {
    for (auto y = 2024y; y <= 2025y; ++y) {
        sys_days thanksgiving = y/November/Thursday[4];       // 美国感恩节
        sys_days memorial     = y/May/Monday[last];           // 美国阵亡将士纪念日
        sys_days eom          = y/February/last;              // 2 月最后一天
        std::cout << thanksgiving << ' ' << memorial << ' ' << eom << ' '
                  << weekday{eom} << '\n';
    }
    auto gap = sys_days{2024y/December/25} - sys_days{2024y/January/1};
    std::cout << gap << '\n';                                  // 359d
}
```

## "/" 日期语法（[time.cal.operators]）

¶1：一组重载的 `operator/` 为创建日期提供常规写法。¶2（注 1）：年、月、日接受三种顺序：

```text
year/month/day      2024y/February/29
month/day/year      February/29/2024
day/month/year      29d/February/2024
```

需要"日"的地方，都可以换成 `last`、`weekday[i]`、`weekday[last]`。¶3（注 2）：少写一个 `/` 就得到部分日期：`2015y/April` 是 `year_month`，`April/4` 与 `4d/April` 是 `month_day`。

¶5–¶44 的 40 个重载可以归纳为一条规则：**第一个 `/` 的两个操作数中至少一个必须是历法类型，它决定了另一边的 `int` 被解释成什么**。

| 左 / 右 | 结果 | `int` 的含义 |
|---|---|---|
| `year / month`、`year / int` | `year_month` | 月 |
| `month / day`、`month / int`、`int / day` | `month_day` | 日（`month/int`）或月（`int/day`） |
| `day / month`、`day / int` | `month_day` | 月 |
| `month / last`、`int / last`、`last / month`、`last / int` | `month_day_last` | 月 |
| `month / weekday_indexed` 等 | `month_weekday` | 月 |
| `year_month / day`、`year_month / int` | `year_month_day` | 日 |
| `year / month_day`、`int / month_day`、`month_day / year`、`month_day / int` | `year_month_day` | 年 |
| `year_month / last`、`year / month_day_last` 等 | `year_month_day_last` | 年 |
| `year_month / weekday_indexed`、`year / month_weekday` 等 | `year_month_weekday` | 年 |
| `year_month / weekday_last`、`year / month_weekday_last` 等 | `year_month_weekday_last` | 年 |

¶4 的例子是这一节最好的 language-lawyer 素材：

```cpp
auto a = 2015/4/4;          // a == int(125)
auto b = 2015y/4/4;         // b == year_month_day{year(2015), month(4), day(4)}
auto c = 2015y/4d/April;    // error: no viable operator/ for first /
auto d = 2015/April/4;      // error: no viable operator/ for first /
```

- `a`：两个 `/` 的操作数都是 `int`，内建整数除法，`2015/4 = 503`，`503/4 = 125`。
- `b`：`2015y/4` 匹配 `year / int` → `year_month`（4 是月），再 `/4` 匹配 `year_month / int` → `year_month_day`。
- `c`：`year / day` 没有重载——"2015 年 4 日"不是任何三种顺序的开头。
- `d`：`int / month` 没有重载。为什么不让它表示"2015 年 4 月"？因为 `int / month` 有歧义：在 `day/month/year` 顺序里，开头的 `int` 应该是日；在 `year/month/day` 顺序里应该是年。标准干脆不提供，强制你写 `2015y` 或 `4d`。

```cpp title="slash-int.cpp" ok
#include <chrono>
using namespace std::chrono;

static_assert(2015/4/4 == 125);                                   // 全是 int：内建除法
static_assert(2015y/4/4 == year_month_day{year{2015}, month{4}, day{4}});
static_assert(April/4/2016 == 2016y/April/4d);                    // month/int → month_day，再 /int 是年
static_assert(4d/April/2016 == 2016y/April/4d);                   // day/month/year
static_assert(4/4/2016 == 0);                                     // 美式顺序但全是 int：0

int main() {}
```

!!! pitfall "最危险的情形：编译通过，结果是个整数"
    `auto d = 4/4/2016;` 不会报错，`d` 是 `int` 0。只要第一个 `/` 两边有一个是历法类型（`2016y`、`April`、`4d`），后面的 `int` 都会被正确解释。养成习惯：**年份总写 `y` 后缀，或月份总用具名常量**。

## 陷阱

!!! pitfall "在 sys_days 上加 years"
    `sys_days{2024y/February/29} + years{1}` 能编译，但 `years{1}` 是**平均年长** 365.2425 天，结果类型是精度为 216 秒的 `sys_time`，值为 `2025-02-28 05:49:12`。按日历加一年应在字段式类型上做：`2024y/February/29 + years{1}`（然后检查 `ok()`）。同理 `months{1}` 是 30.436875 天。

!!! pitfall "weekday 不能比较大小"
    `Monday < Friday` 非良构。如果业务上确实以周一为一周之始，用 `wd.iso_encoding()` 比较；以周日为始，用 `c_encoding()`。

!!! pitfall "默认构造的历法对象未初始化"
    `day`、`month`、`year`、`weekday`、`year_month_day` 等的默认构造函数都是 `= default`，与 `int` 一样，局部变量 `year_month_day d;` 的字段值不确定（C++26 起为错误值，[[basic.indet]]）。

!!! pitfall "无效值的结果"
    对 `!ok()` 的对象求 `sys_days`、做差等，多数情况下结果未指明（例如 [time.cal.month.nonmembers] ¶6、[time.cal.ymd.members] ¶19 的最后一种情形）。这不是 UB，但结果没有意义；`month` 和 `weekday` 的 `+` 是例外，它们对无效值也给出范围内的结果。

## 思考题

1. `sys_days{2024y/February/30}` 是什么？`sys_days{2024y/month{13}/1}` 呢？

<details markdown="1">
<summary>答案</summary>

前者：年、月有效而日无效，按 [time.cal.ymd.members] ¶19 返回 `sys_days{2024y/February/1} + days{29}`，即 2024-03-01。后者：月无效，¶19 说返回值未指明。
</details>

2. 为什么 `month + months` 取模而 `day + days`、`year + years` 不取模？

<details markdown="1">
<summary>答案</summary>

月和星期构成环：12 月之后是 1 月，周六之后是周日，"加一个月"在 `month` 这个孤立字段上只有取模一种合理语义（年份的进位由 `year_month` 处理）。日没有固定周期——一个月 28 到 31 天，`day` 不知道自己属于哪个月，无法正确取模，所以只做简单加减，交给 `ok()` 判断；年是无界的线性量，也不需要取模。
</details>

3. `year_month_weekday{sys_days{2025y/February/Monday[5]}}` 等于 `2025y/February/Monday[5]` 吗？

<details markdown="1">
<summary>答案</summary>

不等于。`2025y/February/Monday[5]` 的 `ok()` 为假（2025 年 2 月只有 4 个周一），按 ¶20 它转换成 `sys_days` 时是"第一个周一之后 28 天"，即 2025-03-03。再从这个 `sys_days` 构造 `year_month_weekday` 得到 `2025y/March/Monday[1]`。¶3 的往返保证只对 `ok()` 的值成立。
</details>

## 小结

- 按天算用 `sys_days`，按月/年算或取字段用 `year_month_day`；两者隐式互转、O(1)。
- `local_days` 与历法类型之间只能显式转换。
- 构造从不检查：用 `ok()` 判断，用 `/last` 或 `sys_days{}` 选择修正策略。
- `month`、`weekday` 是环（取模），`day`、`year` 不是；`weekday` 不可排序。
- `/` 语法：第一个 `/` 必须有一个历法类型；`int/int/int` 只是整数除法。
- `year_month_day_last`、`year_month_weekday(_last)` 在按月/年加减时保持"月末""第 n 个星期 X"的语义。
