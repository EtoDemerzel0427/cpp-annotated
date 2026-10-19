---
title: chrono 格式化
summary: std::format 怎样格式化 chrono 类型：%Y、%m、%S 等转换说明符的含义；不写 L 就不本地化；%S 的小数位由类型决定；负时长的符号位置；类型缺少所需信息时抛 format_error，而这常常变成编译错误；%Z/%z 与 local_time_format、zoned_time。
status: done
papers: P1361R2
related: format.string, format.formatter, format, time.parse, time.duration, time.clock, time.zone, time.hms
tags: 标准库, chrono, format, 格式化
updated: 2026-10-19
---

!!! tldr
    - chrono 的格式说明由填充、对齐、宽度、可选的精度和 `L`，再加上 `%` 开头的转换说明符组成，如 `{:>12%F}`。
    - 不写 `L` 时一律使用 `"C"` locale，与全局 locale 无关；写了 `L` 才本地化。
    - `%S` 的小数位数由类型的精度决定：`milliseconds` 总是 3 位，`seconds` 没有小数。
    - 被格式化的类型缺少说明符需要的信息时抛 `format_error`；如果格式串是编译期检查的，这通常表现为编译错误。
    - `sys_time` 的 `%Z` 永远是 `UTC`，`local_time` 根本没有 `%Z`/`%z`；需要时区信息就用 `zoned_time` 或 `local_time_format`。

## 一个例子

```cpp run ok
#include <chrono>
#include <format>
#include <iostream>
using namespace std::chrono;

int main() {
    auto t = sys_days{2024y/March/1} + 13h + 5min + 7s + 250ms;
    std::cout << std::format("{}", t) << '\n';                            // 2024-03-01 13:05:07.250
    std::cout << std::format("{:%Y-%m-%dT%H:%M:%SZ}", floor<seconds>(t)) << '\n';
                                                                         // 2024-03-01T13:05:07Z
    std::cout << std::format("{:%a %d %b %Y, %I:%M %p}", t) << '\n';      // Fri 01 Mar 2024, 01:05 PM
    std::cout << std::format("{:%j %u %V}", t) << '\n';                   // 061 5 09
    std::cout << std::format("[{:>12%F}]", t) << '\n';                    // [  2024-03-01]
    std::cout << std::format("{:%H:%M}", 90min) << ' '                    // 01:30
              << std::format("{:%Q%q}", 90min) << '\n';                   // 90min
    std::cout << std::format("{:%z %Z}", t) << '\n';                      // +0000 UTC
}
```

C++20 通过 [[P1361R2]] 把 `<chrono>` 接入了 `std::format`。duration、各时钟的 time_point、各种历法类型、`hh_mm_ss`、`sys_info`、`local_info`、`zoned_time` 都有 `formatter` 特化（[[time.syn]]）。本章所有的 `operator<<` 也都用 `format` 定义，例如 `sys_time` 的输出是 `{:L%F %T}`，所以这一节是 chrono 文本输出的唯一规范来源。

转换说明符沿用 C `strftime` 的 `%` 记法，但有三点不同：类型安全，能处理任意精度的小数秒，默认与 locale 无关。

## 格式说明的语法（¶1）

¶1 chrono 库的每个 `formatter` 特化都满足 *Formatter* 要求（[[format.formatter]]），它们的 `parse` 按下面的语法解释格式说明：

```text
chrono-format-spec:  fill-and-align(opt) width(opt) precision(opt) L(opt) chrono-specs(opt)
chrono-specs:        conversion-spec | chrono-specs conversion-spec | chrono-specs literal-char
literal-char:        除 {、}、% 之外的任何字符
conversion-spec:     % modifier(opt) type
modifier:            E O
type:                a A b B c C d D e F g G h H I j m M n p q Q r R S t T u U V w W x X y Y z Z %
```

*fill-and-align*、*width*、*precision* 的含义与 [[format.string]] 相同，作用于整个格式化结果：`{:>20%F}` 把日期右对齐到 20 列。*precision* 只对 rep 是浮点类型的 `duration` 有效，其他类型的格式说明里出现 *precision* 就抛 `format_error`。

*literal-char* 原样复制到输出，所以 `{:%Y年%m月%d日}` 是合法的。

## 格式化 locale（¶2）

¶2 **格式化 locale**（[[g:formatting-locale]]）按以下顺序确定：

- ¶2.1 格式说明中没有 `L` 选项时，用 `"C"` locale；否则
- ¶2.2 用传给格式化函数的 locale，如果有的话；否则
- ¶2.3 用全局 locale。

所以 `format("{:%c}", t)` 永远输出 C locale 的 `Fri Mar  1 13:05:07 2024`，与 `std::locale::global` 设成了什么无关；写成 `{:L%c}` 才本地化。这与 `std::format` 处理数字的方式一致：默认与 locale 无关，`L` 显式开启。

本章的 `operator<<` 都写成 `format(os.getloc(), "{:L...}", ...)`：流输出要尊重流的 locale，所以显式带上 `L`。

!!! history "C++20 之后的修正"
    C++20 最初的措辞里，chrono 格式化默认就使用 locale，与 `std::format` 默认不受 locale 影响的原则冲突。后来通过提案改成现在的规则，并作为缺陷修复适用于 C++20。

## 转换说明符（¶3，表 133）

¶3 每个转换说明符按表 133 替换；表中注明使用 ISO 8601 格式的，按该标准输出。有些说明符依赖格式化 locale。如果字符串字面量编码是 Unicode 编码形式，而 locale 属于实现定义的某组 locale，依赖 locale 的替换结果会转换为字面量编码。被格式化的对象不包含说明符所需的信息时，抛 `format_error`。

按用途分组，以 2024-03-01 13:05:07.250 在 C locale 下为例：

| 类别 | 说明符 | 含义 |
|---|---|---|
| 年 | `%Y` | 年，不足 4 位补 0：`2024`；`year{12}` 为 `0012` |
| | `%y` `%C` | 年的末两位 `24`；世纪（向下取整地除以 100）`20` |
| | `%G` `%g` | ISO 8601 周历年（4 位 / 末两位） |
| 月 | `%m` | `03` |
| | `%b` `%h` `%B` | locale 的缩写或完整月名：`Mar`、`March` |
| 日 | `%d` `%e` | `01`、` 1`（补空格） |
| | `%j` | 一年中的第几天 `061`；对 duration 是天数，不补位 |
| 星期 | `%a` `%A` | `Fri`、`Friday` |
| | `%u` `%w` | ISO 编码（周一为 1，周日为 7）`5`；C 编码（周日为 0）`5` |
| | `%U` `%W` `%V` | 以周日或周一为一周开始的周数；ISO 8601 周数 |
| 时间 | `%H` `%I` `%M` | 24 小时制 `13`、12 小时制 `01`、分 `05` |
| | `%S` | 秒，含小数部分：`07.250`（见下文） |
| | `%p` | `AM` / `PM` |
| 组合 | `%F` `%T` `%R` `%D` | `%Y-%m-%d`、`%H:%M:%S`、`%H:%M`、`%m/%d/%y` |
| | `%c` `%x` `%X` `%r` | locale 的日期时间、日期、时间、12 小时制时间 |
| 时区 | `%z` | UTC 偏移 `+0000`；`%Ez`、`%Oz` 带冒号 `+00:00` |
| | `%Z` | 时区缩写 `UTC` |
| duration | `%Q` | `count()` 的值 |
| | `%q` | 单位后缀，与 [[time.duration]] 的流输出相同：`ms`、`min`、`[1/3]s` |
| 其他 | `%n` `%t` `%%` | 换行、制表符、`%` |

修饰符 `E`、`O` 请求 locale 的替代表示，例如日本年号、非阿拉伯数字。它们只能与表中列出的说明符组合，如 `%Ec`、`%EY`、`%Od`、`%OH`。

表 133 的例 3 说明 `%y` 不管年份的符号：`format("{:%C %y}", -1976y)` 输出 `-20 76`。

### `%S` 与小数秒

| 类型 | `format("{:%S}", ...)` |
|---|---|
| `7s` | `07` |
| `7000ms` | `07.000` |
| `duration<int, ratio<1, 3>>{22}` | `07.333333` |

表 133 对 `%S` 的规定：秒数小于 10 时补一个 0；如果输入的精度不能用整秒精确表示，就输出定点小数，小数位数与输入的精度一致，与 [[time.hms]] 的 `fractional_width` 相同；18 位小数内无法精确表示时，输出到微秒。三分之一秒属于最后一种情况，所以输出 6 位小数。小数点字符由 locale 决定。

所以 `%S` 的位数由类型决定，不由值决定。想要整秒，先 `floor<seconds>(t)` 再格式化。

## 负时长（¶4）

```cpp run ok
#include <chrono>
#include <format>
#include <iostream>
using namespace std::chrono;

int main() {
  std::cout << std::format("{:%T}", -10'000s) << '\n';        // -02:46:40
  std::cout << std::format("{:%H:%M:%S}", -10'000s) << '\n';  // -02:46:40
  std::cout << std::format("minutes {:%M, hours %H, seconds %S}", -10'000s) << '\n';
                                                   // minutes -46, hours 02, seconds 40
}
```

¶4 格式化值为负的 `duration`，或 `is_negative()` 为真的 `hh_mm_ss`，结果等于格式化它的绝对值，再在第一个转换说明符的替换结果之前放一个 `-`。第三行说明，负号跟着第一个转换说明符走，而不是放在整个结果的开头。

## 缺少信息时（¶5–¶6）

¶6 被格式化的类型不包含某个说明符需要的信息时，抛 `format_error`。例 2 举的是 duration：它没有足够的信息格式化成星期几。

但如果说明符指的是一天中的时间（`%H`、`%I`、`%p` 等），duration 解释为从午夜起经过的时间。所以 `format("{:%H:%M}", 90min)` 输出 `01:30`。

¶5 除非显式请求，chrono 类型的格式化结果不含时区缩写和偏移。信息可用时，`%Z` 和 `%z` 分别输出它们；注 1 说明，信息不可用时出现 `%Z` 或 `%z` 就抛 `format_error`。

各类型含有的信息大致如下：

| 类型 | 日期字段 | 时间字段 | 时区 |
|---|---|---|---|
| `duration`、`hh_mm_ss` | 无（`%j` 例外：天数） | 有，从午夜起计算 | 无 |
| `sys_time`、`utc_time`、`file_time` 等 | 有 | 有 | `%Z` 为 `UTC`（tai 为 `TAI`，gps 为 `GPS`），`%z` 为 `+0000` |
| `local_time` | 有 | 有 | 无：`%Z`、`%z` 抛异常 |
| 历法类型 | 各自的字段 | 无 | 无 |
| `zoned_time` | 有 | 有（本地时间） | 有 |

### `format_error` 常常变成编译错误

```cpp
#include <chrono>
#include <format>
using namespace std::chrono;

int main() {
    auto a = std::format("{:%A}", 3s);                  // libc++：编译错误，duration 没有星期
    auto b = std::format("{:%Z}", local_seconds{});     // libc++：编译错误，local_time 没有时区
}
```

`std::format` 的格式串在编译期检查：`basic_format_string` 的构造函数是 `consteval` 的，它在常量求值中调用 formatter 的 `parse`（[[format]]）。类型根本没有某项信息，这在 `parse` 阶段就能确定。`parse` 抛出 `format_error`，常量求值失败，结果就是编译错误。

本机 libc++ 对这两行都报告 `call to consteval function ... is not a constant expression`，附注里能看到 `"The supplied date time doesn't contain a weekday"` 这样的消息。标准只说抛 `format_error`，没有规定在 `parse` 还是 `format` 阶段检查。用 `std::vformat` 绕过编译期检查时，才会在运行期收到异常。

有些错误只能在运行期发现，因为它取决于值。表 133 规定，值不是有效的星期时，`%a` 抛 `format_error`：

```cpp run ok
#include <chrono>
#include <format>
#include <iostream>
using namespace std::chrono;

int main() {
    try {
        weekday wd{9};
        std::cout << std::vformat("{:%a}", std::make_format_args(wd)) << '\n';
    } catch (const std::format_error& e) {
        std::cout << "format_error: " << e.what() << '\n';
    }
    std::cout << std::format("{}", weekday{9}) << '\n';   // 9 is not a valid weekday
}
```

## 省略 chrono-specs（¶7）

¶7 除非另有规定，省略 *chrono-specs* 时，结果如同把对象输出到一个 imbue 了格式化 locale 的 `basic_ostringstream`，再把 `os.str()` 按填充、宽度等说明复制到输出。例 4：`format("{:=>8}", 42ms)` 得到 `"====42ms"`。

这把 `{}` 与 `operator<<` 统一了起来。`{}` 格式化 `sys_time` 得到 `%F %T` 的形式；格式化无效的 `year_month_day{2024y/February/30}` 得到 `2024-02-30 is not a valid date`，而显式写 `{:%F}` 只输出 `2024-02-30`，不附加说明。

## 各时钟的 formatter（¶10–¶15）

| 特化 | `%Z` | `%z` | 其他 | 段落 |
|---|---|---|---|---|
| `sys_time` | `UTC` | `+0000` | | ¶10 |
| `utc_time` | `UTC` | `+0000` | 闰秒插入期间，秒字段的整数部分为 `60` | ¶11 |
| `tai_time` | `TAI` | `+0000` | 按 `sys_time{tp.time_since_epoch()}` 减去 1958 到 1970 年的天数显示 | ¶12 |
| `gps_time` | `GPS` | `+0000` | 按 `sys_time{tp.time_since_epoch()}` 加上 1970-01-01 到 1980-01-06 的天数显示 | ¶13 |
| `file_time` | `UTC` | `+0000` | 按 `clock_cast<system_clock>(t)` 或 `clock_cast<utc_clock>(t)` 显示 | ¶14 |
| `local_time` | 抛 `format_error` | 抛 `format_error` | | ¶15 |

¶12、¶13 的换算只是平移纪元，不考虑闰秒。TAI 和 GPS 本来就不插入闰秒，它们的读数就是从各自的纪元起、每天 86400 秒。

## `local_time_format` 与 `zoned_time`（¶16–¶19）

`local_time` 没有时区信息。如果你知道它的缩写和偏移（例如从文件里读出来），想一起输出，就用 `local_time_format`：

```cpp
template<class Duration>
  local-time-format-t<Duration>
    local_time_format(local_time<Duration> time, const string* abbrev = nullptr,
                      const seconds* offset_sec = nullptr);
```

¶16 它返回一个仅用于说明的聚合 `{time, abbrev, offset_sec}`。¶17–¶18 这个类型的 formatter 在省略 *chrono-specs* 时等价于 `%F %T %Z`；`%Z` 输出 `*abbrev`，`%z` 输出 `*offset_sec`，对应的指针为空时抛 `format_error`。

形参是指针，返回的对象也只保存指针，所以所指的对象要活得比格式化调用久：

```cpp
std::string abbr = "CST";
std::cout << std::format("{}", local_time_format(lt, &abbr));   // OK
auto f = local_time_format(lt, &std::string("CST"));            // error: 不能对纯右值取地址
```

¶19 `zoned_time` 的 formatter 派生自 `local-time-format-t` 的 formatter。它的 `format` 先取 `sys_info info = tp.get_info()`，再以 `{tp.get_local_time(), &info.abbrev, &info.offset}` 调用基类。所以 `zoned_time` 的 `%Z`、`%z` 总是可用，`{}` 输出形如 `2024-03-15 09:00:00 EDT`。`info` 是局部变量，指针只在这次调用内使用，不会悬空。

本机 libc++ 还没有提供 `local_time_format` 和 `zoned_time`，本节的代码没有经过编译验证。

<details class="fine" markdown="1"><summary>其余条文</summary>

¶8–¶9 {{c++26}}：`std::print` 在格式化器保证不调用用户代码时，可以不持有流锁直接输出，由 `enable_nonlocking_formatter_optimization` 控制（[[print.fun]]）。对 `duration`，库只提供一个特化，值与 `Rep` 的相同；对 `zoned_time`，只为 `TimeZonePtr` 是 `const time_zone*` 的情形提供特化，值为 `true`。用户自定义的 `Rep` 或 `TimeZonePtr` 可能执行任意代码，所以不能默认开启。

</details>

## 常见误解

!!! pitfall "`%S` 只输出整数秒"
    `format("{:%T}", system_clock::now())` 在本机 libc++ 上输出 6 位小数，因为 `system_clock::duration` 是微秒；libstdc++ 上是纳秒，输出 9 位。要固定格式，先 `floor<seconds>` 或 `floor<milliseconds>`。

!!! pitfall "`%Z` 能给出本地时区"
    `format("{:%Z}", system_clock::now())` 永远是 `UTC`，因为 `sys_time` 本来就是 UTC。要显示本地时区，格式化 `zoned_time{current_zone(), now}`。

!!! pitfall "设置了全局 locale 就会本地化"
    设置了全局 locale 之后，`format("{:%B}", t)` 仍然输出英文月名。本地化必须写 `{:L%B}`，并传入或设置相应的 locale。

## 小结

- 格式说明：填充、对齐、宽度，仅浮点 duration 可用的精度，可选的 `L`，再加转换说明符。
- 默认用 `"C"` locale，写 `L` 才本地化。
- `%S` 的小数位数由类型的精度决定。
- 负 duration 的 `-` 放在第一个转换说明符之前。
- 缺少信息时抛 `format_error`；能在 `parse` 阶段发现的，经由编译期格式串检查变成编译错误。
- `local_time` 没有 `%Z`/`%z`，需要时用 `local_time_format` 或 `zoned_time`。
