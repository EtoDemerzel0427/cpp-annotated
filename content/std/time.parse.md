---
title: chrono 解析
summary: parse 操纵符如何经由 ADL 调用 from_stream；解析标志（%Y %m %d %H %M %S %z %Z …）与格式化说明符的差异——宽度 N、大小写不敏感、%y 的世纪窗口、空白匹配规则；信息不足时 failbit；sys_time 会减去 %z 偏移而 local_time 不会；悬空格式串的风险
status: done
related: time.format, time.clock, time.cal, time.duration, basic.lookup.argdep, istream.unformatted
tags: 标准库, chrono, 解析, iostream
updated: 2026-10-18
---

`parse` 是 [[time.format]] 的逆操作：按 `%` 格式串从输入流中读出一个 chrono 值。它基于 iostream 而不是 `std::format` 那样的独立设施——C++20 时标准库还没有 `std::scan`，流是唯一现成的输入抽象。

```cpp
std::istringstream in{"2024-03-01 13:05:07"};
sys_seconds tp;
in >> parse("%F %T", tp);
if (in) { /* 成功 */ }
```

!!! impl "libc++ 尚未实现"
    截至写作时，libc++ 没有实现 `parse` 与各个 `from_stream` 重载（`<chrono>` 中找不到这些名字），本页例子无法在本机编译。例子按标准编写，可在 Compiler Explorer 上用较新的 GCC 或 MSVC 运行。

## parse 与 from_stream 的分工（¶1–¶14）

¶1：每个 `parse` 重载都以**非限定**方式调用 `from_stream`，以启用实参依赖查找（[[basic.lookup.argdep]]）。以下令 `is` 为 `basic_istream<charT, traits>` 对象，`I` 为 `basic_istream<charT, traits>&`。

这是一个典型的**定制点**设计：

- `from_stream(is, fmt, value, abbrev*, offset*)` 是真正干活的函数，本章为每个 chrono 类型都提供了一个（[time.duration.io] ¶3、[time.clock.system.nonmembers] ¶6、[time.cal.day.nonmembers] ¶8 等）；
- `parse(fmt, value, ...)` 只是包装，返回一个**操纵符**，让 `is >> parse(...)` 的写法成立；
- 用户为自己的类型在其所在命名空间里提供 `from_stream`，`parse` 通过 ADL 找到它，于是 `is >> parse("%F", my_date)` 对用户类型同样可用。

四组重载按是否额外接收时区缩写 `abbrev`、UTC 偏移 `offset` 区分，每组都有 `const charT*` 与 `basic_string` 两种格式串形式：

| 重载 | 调用 | 段落 |
|---|---|---|
| `parse(fmt, tp)` | `from_stream(is, F, tp)` | ¶3–¶5 |
| `parse(fmt, tp, abbrev)` | `from_stream(is, F, tp, addressof(abbrev))` | ¶6–¶8 |
| `parse(fmt, tp, offset)` | `from_stream(is, F, tp, static_cast<basic_string<...>*>(nullptr), &offset)` | ¶9–¶11 |
| `parse(fmt, tp, abbrev, offset)` | `from_stream(is, F, tp, addressof(abbrev), &offset)` | ¶12–¶14 |

其中 `F` 对 `const charT*` 形式是 `fmt`，对 `basic_string` 形式是 `fmt.c_str()`。

- *Constraints*（¶4、¶7、¶10、¶13）：对应的 `from_stream` 调用作为不求值操作数是良构的。所以对一个没有 `from_stream` 的类型调用 `parse`，`parse` 本身就不可行，错误出现在调用处而不是深层实例化中。
- *Returns*（¶5、¶8、¶11、¶14）：一个**未指明类型**的操纵符，使 `is >> parse(...)` 的类型为 `I`、值为 `is`，并调用相应的 `from_stream`。

`abbrev` 用 `addressof` 取地址而不是 `&`：`basic_string<charT, traits, Alloc>` 的模板实参可以是用户定义的类型，于是 ADL 可能找到用户为它重载的一元 `operator&`。对可能涉及用户类型的对象一律用 `addressof`，是标准库的一贯做法。

### 悬空的格式串（¶2）

¶2 *Recommended practice*：实现应当让意外保存或使用"可能持有悬空格式串引用的操纵符"变得困难，例如让 `parse` 返回的操纵符不可移动，并阻止向这种操纵符的左值做流提取。

问题在于操纵符只保存格式串的**指针**：

```cpp
auto m = parse(std::string("%F"), ymd);   // 临时 string 在这一行结束时销毁
in >> m;                                  // 操纵符里的指针已悬空：UB
```

注意仅仅"不可移动"挡不住第一行：C++17 起 `auto m = parse(...)` 依靠保证的复制消除（[[class.copy.elision]]）照样能编译。所以推荐做法里还有后半句——禁止对这种操纵符的**左值**做流提取，这样第二行 `in >> m` 编译失败，只剩 `in >> parse(...)` 这种在同一个完整表达式中创建并使用的写法。标准把这写成推荐而非要求，可移植代码应当自觉遵守这一用法。

## from_stream 的通用规则（¶15–¶17）

¶15：

- 所有 `from_stream` 都表现为**无格式输入函数**（[[istream.unformatted]]）：构造 `sentry` 时不跳过前导空白；但它们对之后 `gcount()` 的返回值的影响是未指明的。
- 格式串包含普通字符和以 `%` 开头的标志；部分标志可以用 `E` 或 `O` 修饰；部分标志可以带一个正十进制宽度 *N*，规定最多读取多少个字符（如 `%4Y`）。
- 表 134 中没有列出的字符（**空白除外**）必须与输入逐字匹配。
- 格式串中的**一个空白字符匹配输入中零个或多个空白字符**。

¶16：被解析的类型无法表示某个标志所指的信息时，调用 `is.setstate(ios_base::failbit)`。例：duration 不能表示星期几。但与格式化一样，"一天中的时间"类标志（`%H`、`%I`、`%p` 等）对 duration 解释为自午夜起经过的时间。

¶17：没能解析完格式串规定的全部内容，**或者**解析出的信息不足以确定一个完整的 duration、time_point 或历法数据结构时，调用 `setstate(failbit)`。

¶17 的后半句很关键：

```cpp
year_month_day ymd;
std::istringstream{"2024-03"} >> parse("%Y-%m", ymd);   // failbit：没有日
year_month ym;
std::istringstream{"2024-03"} >> parse("%Y-%m", ym);    // OK
```

另外，各 `from_stream` 都规定：**解析失败时不修改目标对象**。所以失败后 `ymd` 保持原值，读取前应当给它一个确定的初值，或者只在流状态良好时使用它。

## 解析标志（表 134）

大部分标志的含义与 [[time.format]] 的表 133 对称，下面只列解析特有的规则。

| 标志 | 解析规则 | 默认宽度 *N* |
|---|---|---|
| `%a` `%A` | locale 的星期名，全称或缩写皆可，**大小写不敏感** | — |
| `%b` `%B` `%h` | locale 的月名，全称或缩写皆可，大小写不敏感 | — |
| `%Y` | 年 | 4 |
| `%y` | 年的末两位；若没有用 `%C` 等给出世纪，69–99 视为 1969–1999，00–68 视为 2000–2068 | 2 |
| `%C` | 世纪 | 2 |
| `%m` `%d` `%e` `%H` `%I` `%M` | 前导零可有可无 | 2 |
| `%j` | 一年中第几天；**对 duration 是天数** | 3 |
| `%S` | 秒；目标精度能转换为秒时默认宽 2，否则宽度由目标的十进制精度决定，按定点 `long double` 读取，小数点由 locale 决定 | 2 或更宽 |
| `%u` `%w` | 星期数字（ISO / C 编码） | 1 |
| `%U` `%W` `%V` `%G` `%g` | 周数、ISO 周历年 | 2、2、2、4、2 |
| `%F` | `%Y-%m-%d`；带宽度 *N* 时只作用于 `%Y` | — |
| `%z` | `[+|-]hh[mm]`：`-0430`、`04` | — |
| `%Ez` `%Oz` | `[+|-]h[h][:mm]`：`-04:30`、`4` | — |
| `%Z` | 时区缩写或名字：**一个单词**，只能含基本字符集中的字母数字和 `_` `/` `-` `+` | — |
| `%n` | 恰好一个空白字符 | — |
| `%t` | 零个或一个空白字符 | — |
| `%%` | 一个 `%` | — |

几个细节：

- `%y` 的 69/68 分界与 POSIX `strptime` 相同。表 134 中 `%y` 一行的例 2：`istringstream{"-20 76"} >> parse("%3C %y", y)` 得到 `-1976y`——`%3C` 允许读入带符号的三个字符 `-20`，世纪给定后 `%y` 不再套用窗口。
- 格式串里的空格匹配"零个或多个"空白，`%n` 匹配"恰好一个"，`%t` 匹配"零或一个"，组合起来可以描述各种空白模式：表注 1 举例说 `"%n "` 匹配一个或多个空白，`"%n%t%t"` 匹配一到三个空白。
- `%Z` 解析出的字符串只通过 `abbrev` 输出参数交给调用者，**不参与**时间换算——缩写不唯一（[[time.zone]]），标准不尝试从它推算偏移。

## 偏移的处理：sys_time 与 local_time 的区别

各时钟的 `from_stream` 在 `%z` 成功解析时有两种行为：

- `sys_time`、`utc_time`、`tai_time`、`gps_time`、`file_time`（[time.clock.system.nonmembers] ¶6 等）：把偏移写入 `*offset`（若非空），**并且从解析出的时间戳中减去偏移**，结果是真正的 UTC 时刻。
- `local_time`（[time.clock.local] ¶5）：只把偏移写入 `*offset`，**不**修改时间戳——本地时间本来就不对齐 UTC。

```cpp title="parse-offset.cpp" ok
#include <chrono>
#include <iostream>
#include <sstream>
using namespace std::chrono;

int main() {
    sys_seconds st;
    local_seconds lt;
    minutes off{};
    std::istringstream{"2024-03-01 08:00:00 +0800"} >> parse("%F %T %z", st);
    std::istringstream{"2024-03-01 08:00:00 +0800"} >> parse("%F %T %z", lt, off);
    std::cout << st << '\n';          // 2024-03-01 00:00:00：已换算为 UTC
    std::cout << lt << ' ' << off << '\n';   // 2024-03-01 08:00:00 480min：原样保留
}
```

## 自定义类型的解析

因为 `parse` 通过 ADL 查找 `from_stream`，为自己的类型提供解析只需在类型所在的命名空间中写一个签名兼容的 `from_stream`：

```cpp title="parse-custom.cpp" ok
#include <chrono>
#include <iostream>
#include <sstream>
#include <string>

namespace app {
    struct date { std::chrono::year_month_day ymd; };

    template<class CharT, class Traits, class Alloc = std::allocator<CharT>>
    std::basic_istream<CharT, Traits>&
    from_stream(std::basic_istream<CharT, Traits>& is, const CharT* fmt, date& d,
                std::basic_string<CharT, Traits, Alloc>* abbrev = nullptr,
                std::chrono::minutes* offset = nullptr) {
        std::chrono::year_month_day tmp;
        std::chrono::from_stream(is, fmt, tmp, abbrev, offset);   // 复用标准实现
        if (is) d.ymd = tmp;
        return is;
    }
}

int main() {
    app::date d;
    std::istringstream{"2024-02-29"} >> std::chrono::parse("%F", d);   // ADL 找到 app::from_stream
    std::cout << d.ymd << '\n';
}
```

## 陷阱

!!! pitfall "忘记检查流状态"
    `parse` 失败只设置 `failbit`，不抛异常（除非流设置了 `exceptions()`），目标对象保持原值。`in >> parse(...);` 之后必须检查 `in`。

!!! pitfall "用 sys_time 解析不带偏移的本地时间"
    `"2024-03-01 08:00:00"` 来自用户界面时几乎总是本地时间。把它解析进 `sys_seconds` 不会报错，但得到的是 UTC 08:00。应当解析进 `local_seconds`，再经由 `time_zone` 或 `zoned_time` 换算（[[time.zone]]）。

!!! pitfall "格式串里的空格比想象中宽松"
    `parse("%F %T", tp)` 也能接受 `"2024-03-01      13:05:07"` 甚至 `"2024-03-0113:05:07"`——一个空格匹配零个或多个空白。需要严格校验时用 `%n`。

## 小结

- `is >> parse(fmt, x)` 经由 ADL 调用 `from_stream`；用户类型提供自己的 `from_stream` 即可接入。
- 失败设置 `failbit`、不修改目标；信息不足（如解析 `year_month_day` 缺日）同样失败。
- 解析与格式化标志大体对称，额外有宽度 *N*、大小写不敏感、`%y` 世纪窗口、空白匹配规则。
- `sys_time` 系列会减去 `%z` 偏移得到 UTC，`local_time` 不会。
- 操纵符可能引用临时格式串：在同一个完整表达式里创建并使用它。
- libc++ 尚未实现。
