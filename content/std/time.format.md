---
title: chrono 格式化
summary: std::format 对 chrono 类型的格式说明 chrono-format-spec——%Y %m %d %H %M %S 等转换说明符的精确含义；格式化 locale 只有加 L 才生效；负时长的符号位置；缺少信息时的 format_error（以及它为什么常常变成编译错误）；各时钟的 %Z/%z；local_time_format 与 zoned_time
status: done
papers: P1361R2
related: format.string, format.formatter, format, time.parse, time.duration, time.clock, time.zone, time.hms
tags: 标准库, chrono, format, 格式化
updated: 2026-10-18
---

C++20 通过 [[P1361R2]] 把 `<chrono>` 接入了 `std::format`：每个 chrono 值类型——duration、各时钟的 time_point、15 个历法类型、`hh_mm_ss`、`sys_info`、`local_info`、`zoned_time`——都有 `formatter` 特化（概要 [time.syn] 中列出）。本章所有的 `operator<<` 也都**用 `format` 定义**（如 `sys_time` 的输出是 `{:L%F %T}`），所以本节是 chrono 文本输出的唯一规范来源。

格式说明沿用 C `strftime` 的 `%` 记法，但与 `strftime` 有三处根本不同：类型安全（格式化什么类型由编译器知道）、能处理任意精度的小数秒、默认与 locale 无关。

## 格式说明的语法（¶1）

¶1：chrono 库中的每个 `formatter` 特化都满足 *Formatter* 要求（[[format.formatter]]）。它们的 `parse` 成员把格式说明按如下语法解释：

```text
chrono-format-spec:  fill-and-align(opt) width(opt) precision(opt) L(opt) chrono-specs(opt)
chrono-specs:        conversion-spec | chrono-specs conversion-spec | chrono-specs literal-char
literal-char:        除 {、}、% 之外的任何字符
conversion-spec:     % modifier(opt) type
modifier:            E O
type:                a A b B c C d D e F g G h H I j m M n p q Q r R S t T u U V w W x X y Y z Z %
```

- *fill-and-align*、*width*、*precision* 的含义同 [[format.string]]：对**整个**格式化结果做填充与对齐。`{:>20%F}` 把日期右对齐到 20 列。
- *precision* 只对 rep 为浮点的 `duration` 有效；对其他类型，格式说明中出现 *precision* 就抛 `format_error`。
- 所有 *literal-char* 原样复制到输出：`{:%Y年%m月%d日}` 是合法的。

## 格式化 locale（¶2）

¶2：**格式化 locale**（[[g:formatting-locale]]）定义为：

- ¶2.1：格式说明中**没有** `L` 选项时，用 `"C"` locale；否则
- ¶2.2：用传给格式化函数的 locale（如果有）；否则
- ¶2.3：用全局 locale。

所以 `format("{:%c}", t)` 永远输出 C locale 的 `Fri Mar  1 13:05:07 2024`，与 `std::locale::global` 设成什么无关；只有写成 `{:L%c}` 才本地化。这与 `std::format` 处理数字的方式一致：默认与 locale 无关，`L` 显式开启。

!!! history "C++20 → C++23 的修正"
    C++20 最初的措辞里，chrono 格式化默认就使用全局 locale，与 `std::format` "默认不受 locale 影响"的原则冲突。C++23 中通过提案改为现在的规则，并作为缺陷修复适用于 C++20。这也是为什么本章各处的 `operator<<` 都写成 `format(os.getloc(), "{:L...}", ...)`：流输出要尊重流的 locale，所以显式带上 `L`。

## 转换说明符（¶3，表 133）

¶3：每个 *conversion-spec* 按表 133 替换；凡标注了 ISO 8601-1:2019 的，使用该标准的格式。有些说明符依赖格式化 locale。若字符串字面量编码是 Unicode 编码形式，且 locale 属于实现定义的一组 locale，依赖 locale 的替换结果会被转换为字面量编码。若被格式化的对象**不包含**说明符所需的信息，抛 `format_error`。

按用途把表 133 分组：

| 类别 | 说明符 | 含义（C locale 下的例子，以 2024-03-01 13:05:07.250 为例） |
|---|---|---|
| 年 | `%Y` | 年，不足 4 位补 0：`2024`；`year{12}` 为 `0012` |
| | `%y` `%C` | 年的末两位 `24`、世纪（floored 除以 100）`20` |
| | `%G` `%g` | ISO 8601 周历年（4 位 / 末两位） |
| 月 | `%m` | `03` |
| | `%b` `%h` `%B` | locale 的缩写/全称月名：`Mar`、`March` |
| 日 | `%d` `%e` | `01`、` 1`（补空格） |
| | `%j` | 一年中第几天 `061`；**对 duration 是天数，不补位** |
| 星期 | `%a` `%A` | `Fri`、`Friday` |
| | `%u` `%w` | ISO（周一 = 1 … 周日 = 7）`5`；C（周日 = 0）`5` |
| | `%U` `%W` `%V` | 以周日 / 周一为一周之始的周数；ISO 8601 周数 |
| 时间 | `%H` `%I` `%M` | 24 小时制 `13`、12 小时制 `01`、分 `05` |
| | `%S` | 秒，**含小数秒**：`07.250`（见下文） |
| | `%p` | `AM` / `PM` |
| 组合 | `%F` `%T` `%R` `%D` | `%Y-%m-%d`、`%H:%M:%S`、`%H:%M`、`%m/%d/%y` |
| | `%c` `%x` `%X` `%r` | locale 的日期时间、日期、时间、12 小时制时间 |
| 时区 | `%z` | UTC 偏移 `+0000`；`%Ez`、`%Oz` 带冒号 `+00:00` |
| | `%Z` | 时区缩写 `UTC` |
| duration | `%Q` | `count()` 的值 |
| | `%q` | 单位后缀（同 [[time.duration]] 的流输出：`ms`、`min`、`[1/3]s`） |
| 其他 | `%n` `%t` `%%` | 换行、制表符、`%` |

修饰符 `E`、`O` 用于请求 locale 的"替代表示"（如日本年号、非阿拉伯数字），只能与表中列出的说明符组合，如 `%Ec`、`%EY`、`%Od`、`%OH`。

### %S 与小数秒

表 133 对 `%S` 的规定：秒数小于 10 时补 0；如果输入的精度不能用秒精确表示，就输出定点小数，小数位数与输入精度一致（与 [[time.hms]] 的 `fractional_width` 相同），无法在 18 位内精确表示时输出到微秒。

所以 `%S` 的位数**由类型决定**，不由值决定：`milliseconds` 总输出 3 位小数（`07.250`，`07.000`），`seconds` 不输出小数。想要整秒，先 `floor<seconds>(t)` 再格式化——这比在格式说明里截断更明确。

## 负时长（¶4）

¶4：格式化负的 `duration`，或 `is_negative()` 为真的 `hh_mm_ss`，结果等同于格式化其绝对值，并在**第一个转换说明符**的替换结果之前放一个 `-`。

```cpp
format("{:%T}", -10'000s);          // "-02:46:40"
format("{:%H:%M:%S}", -10'000s);    // "-02:46:40"
format("minutes {:%M, hours %H, seconds %S}", -10'000s);
                                    // "minutes -46, hours 02, seconds 40"
```

第三个例子说明：负号跟着第一个转换说明符走，而不是放在整个结果的开头。

## 缺失的信息（¶5–¶6）

- ¶5：除非显式请求，chrono 类型的格式化结果**不含**时区缩写与偏移。信息可用时，`%Z` 和 `%z` 格式化它们。注 1：信息不可用而格式说明中出现 `%Z` 或 `%z` 时，抛 `format_error`。
- ¶6：被格式化的类型不含格式标志所需的信息时，抛 `format_error`。例 2：duration 没有足够信息格式化为星期几。**但是**，如果标志引用的是"一天中的时间"（`%H`、`%I`、`%p` 等），duration 被解释为**自午夜起经过的时间**。

后一条让 `format("{:%H:%M}", 90min)` 输出 `01:30`。

哪些类型含有哪些信息，大致是：

| 类型 | 日期字段 | 时间字段 | 时区 |
|---|---|---|---|
| `duration`、`hh_mm_ss` | 无（`%j` 例外：天数） | 有（按自午夜起解释） | 无 |
| `sys_time`、`utc_time`、`file_time` 等 | 有 | 有 | `%Z` = `UTC`（tai 为 `TAI`，gps 为 `GPS`），`%z` = `+0000` |
| `local_time` | 有 | 有 | **无**：`%Z`/`%z` 抛异常 |
| 历法类型 | 各自的字段 | 无 | 无 |
| `zoned_time` | 有 | 有（本地时间） | 有 |

### format_error 常常是编译错误

`std::format` 的格式串在编译期检查：`basic_format_string` 的构造函数是 `consteval` 的，它会在常量求值中调用 formatter 的 `parse`（[[format]]）。chrono formatter 能在 `parse` 阶段就知道"duration 没有星期信息"、"local_time 没有时区"——这类检查发生在 `parse` 里时，抛出的 `format_error` 让常量求值失败，**结果是编译错误**而不是运行期异常。

```cpp title="fmt-missing-info.cpp"
#include <chrono>
#include <format>
using namespace std::chrono;

int main() {
    auto a = std::format("{:%A}", 3s);                  // libc++：编译错误（duration 不含星期）
    auto b = std::format("{:%Z}", local_seconds{});     // libc++：编译错误（local_time 不含时区）
}
```

标准只说"抛 `format_error`"，没有规定检查发生在 `parse` 还是 `format` 阶段；但对于"这个**类型**根本没有这项信息"的情形，实现在 `parse` 中就能确定。libc++ 在这两行都报告"call to consteval function ... is not a constant expression"，附注中可以看到 `__throw_format_error("The supplied date time doesn't contain a weekday")`。只有用 `std::vformat` 绕过编译期检查时，才会在运行期收到 `format_error`。

有些错误只能在运行期发现，因为它取决于**值**：格式化 `weekday{9}` 的 `%a`，表 133 规定值不是有效星期时抛 `format_error`。

```cpp title="fmt-runtime-error.cpp" ok
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
    std::cout << std::format("{}", weekday{9}) << '\n';   // 无 chrono-specs：走流输出，"9 is not a valid weekday"
}
```

## 省略 chrono-specs（¶7）

¶7：除非另有规定，省略 *chrono-specs* 时，结果如同把对象输出到一个 imbue 了格式化 locale 的 `basic_ostringstream`，再把 `os.str()` 按填充、宽度等说明复制到输出。例 4：`format("{:=>8}", 42ms)` 得到 `"====42ms"`。

这条把 `{}` 与 `operator<<` 统一了起来：`{}` 格式化 `sys_time` 得到 `%F %T`，格式化无效的 `year_month_day` 得到 "… is not a valid date"，而显式写 `{:%F}` 则直接输出 `2024-02-30`，不附加任何说明。

## 非锁定格式化优化（¶8–¶9）{{c++26}}

`std::print` 在格式化器保证不调用用户代码时，可以不持有流锁直接输出（`enable_nonlocking_formatter_optimization`，见 [[print.fun]]）。¶8：对 `duration` 只提供一个特化，取值与 `Rep` 的相同；¶9：对 `zoned_time` 只为 `TimeZonePtr` 为 `const time_zone*` 的情形提供特化，值为 `true`。用户自定义的 `Rep` 或 `TimeZonePtr` 可能执行任意代码，所以不能默认开启。

## 各时钟的 formatter（¶10–¶14）

| 特化 | `%Z` | `%z` | 其他 | 段落 |
|---|---|---|---|---|
| `sys_time` | `UTC` | `+0000` | | ¶10 |
| `utc_time` | `UTC` | `+0000` | 闰秒期间秒字段的整数部分为 `60` | ¶11 |
| `tai_time` | `TAI` | `+0000` | 日期时间按 `sys_time{tp.time_since_epoch()} − (1970 − 1958 的天数)` 显示 | ¶12 |
| `gps_time` | `GPS` | `+0000` | 按 `sys_time{tp.time_since_epoch()} + (1980-01-06 − 1970-01-01)` 显示 | ¶13 |
| `file_time` | `UTC` | `+0000` | 按 `clock_cast<system_clock>(t)` 或 `clock_cast<utc_clock>(t)` 显示 | ¶14 |
| `local_time` | **抛** `format_error` | **抛** | | ¶15 |

¶12、¶13 的换算只是平移纪元，不考虑闰秒——TAI 与 GPS 本来就不插入闰秒，它们的钟面时间就是"从各自纪元开始、每天 86400 秒"的读数。

## local_time_format 与 zoned_time（¶15–¶19）

`local_time` 没有时区信息，但有时你**知道**它的缩写和偏移（例如从文件里读出来的），想一起输出。¶16：

```cpp
template<class Duration>
  local-time-format-t<Duration>
    local_time_format(local_time<Duration> time, const string* abbrev = nullptr,
                      const seconds* offset_sec = nullptr);
```

返回一个仅用于说明的聚合 `{time, abbrev, offset_sec}`。¶17–¶18：它的 formatter 在省略 *chrono-specs* 时等价于 `%F %T %Z`；`%Z` 用 `*abbrev`、`%z` 用 `*offset_sec`，对应指针为空时抛 `format_error`。

注意形参是**指针**，返回的对象只保存指针：

```cpp
auto f = local_time_format(lt, &std::string("CST"));   // 非良构：不能对纯右值取地址
std::string abbr = "CST";
std::cout << std::format("{}", local_time_format(lt, &abbr));   // OK：abbr 活得比格式化调用久
```

¶19：`zoned_time` 的 formatter **派生自** `local-time-format-t` 的 formatter，`format` 成员先取 `sys_info info = tp.get_info()`，再以 `{tp.get_local_time(), &info.abbrev, &info.offset}` 调用基类。所以 `zoned_time` 的 `%Z`、`%z` 总是可用，`{}` 输出 `2024-03-15 09:00:00 EDT`。`info` 是局部变量，指针只在这次调用内使用，没有悬空问题。

## 例子

```cpp title="chrono-format.cpp" ok
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

## 陷阱

!!! pitfall "以为 %S 只输出整数秒"
    `format("{:%T}", system_clock::now())` 在 libc++ 上输出 6 位小数（微秒），在 libstdc++ 上输出 9 位（纳秒）。要固定格式，先 `floor<seconds>` 或 `floor<milliseconds>`。

!!! pitfall "以为 %Z 能给出本地时区"
    `format("{:%Z}", system_clock::now())` 永远是 `UTC`：`sys_time` 本来就是 UTC。要显示本地时区，格式化 `zoned_time{current_zone(), now}`。

!!! pitfall "以为不加 L 也会本地化"
    设置了全局 locale 后 `format("{:%B}", t)` 仍然输出英文月名。本地化必须写 `{:L%B}`，并传入或设置相应 locale。

## 小结

- chrono 格式说明：填充/宽度/（仅浮点 duration 的）精度 + 可选 `L` + `%` 转换说明符。
- 默认 "C" locale，`L` 才本地化。
- `%S` 的小数位数由类型精度决定。
- 负 duration 的 `-` 放在第一个转换说明符之前。
- 缺信息抛 `format_error`；能在 `parse` 阶段发现的，经由 `std::format` 的编译期检查变成编译错误。
- `local_time` 没有 `%Z`/`%z`；需要时用 `local_time_format` 或 `zoned_time`。
