---
title: chrono 解析
summary: is >> parse(fmt, x) 按 % 格式串从流中读出 chrono 值，经由 ADL 调用 from_stream；解析标志与格式化说明符的区别（最大宽度、大小写不敏感、%y 的世纪窗口、空白匹配）；失败时置 failbit 且不修改目标；sys_time 会减去 %z 偏移而 local_time 不会。
status: done
related: time.format, time.clock, time.cal, time.duration, basic.lookup.argdep, istream.unformatted
tags: 标准库, chrono, 解析, iostream
updated: 2026-10-19
---

!!! tldr
    - `in >> parse("%F %T", tp)` 按格式串从流中读出一个 chrono 值。`parse` 只是包装，真正解析的是通过实参依赖查找找到的 `from_stream`，所以用户类型也能接入。
    - 解析失败或信息不足（例如读 `year_month_day` 却没有日）时置 `failbit`，目标对象保持原值，不抛异常。
    - 格式串里的一个空格匹配零个或多个空白；`%n` 匹配恰好一个，`%t` 匹配零个或一个。
    - 解析进 `sys_time` 时，`%z` 读到的偏移会从结果中减去，得到 UTC；解析进 `local_time` 时只报告偏移，不修改时间。
    - `parse` 返回的操纵符只保存格式串的指针，要在同一个完整表达式里创建和使用它。

## 基本用法

```cpp
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
    std::cout << st << '\n';                  // 2024-03-01 00:00:00：已换算为 UTC
    std::cout << lt << ' ' << off << '\n';    // 2024-03-01 08:00:00 480min：原样保留
}
```

`parse` 是 [[time.format]] 的逆操作。它建立在 iostream 上，而不是像 `std::format` 那样的独立设施，因为 C++20 时标准库没有对应的 `std::scan`，流是唯一现成的输入抽象。

!!! impl "libc++ 尚未实现"
    本机 libc++ 没有实现 `parse` 和各个 `from_stream` 重载，本页的代码都没有经过编译验证，因此不标判定。它们按标准编写，可以在 Compiler Explorer 上用较新的 GCC 或 MSVC 运行。

## `parse` 与 `from_stream`（¶1–¶14）

¶1 每个 `parse` 重载都以非限定的方式调用 `from_stream`，以便启用实参依赖查找（ADL，[[basic.lookup.argdep]]）。

这是一个定制点设计。`from_stream(is, fmt, value, abbrev, offset)` 负责真正的解析，本章为每个 chrono 类型都提供了一个，例如 [[time.duration.io#3]]、[[time.clock.system.nonmembers#6]]、[[time.cal.day.nonmembers#8]]。`parse(fmt, value, ...)` 只是包装，返回一个操纵符，让 `is >> parse(...)` 的写法成立。用户在自己类型所在的命名空间里提供 `from_stream`，`parse` 就能通过 ADL 找到它。

四组重载的区别在于是否额外接收时区缩写 `abbrev` 和 UTC 偏移 `offset`。每组都有 `const charT*` 和 `basic_string` 两种格式串形式，下表中 `F` 对前者是 `fmt`，对后者是 `fmt.c_str()`：

| 重载 | 调用 | 段落 |
|---|---|---|
| `parse(fmt, tp)` | `from_stream(is, F, tp)` | ¶3–¶5 |
| `parse(fmt, tp, abbrev)` | `from_stream(is, F, tp, addressof(abbrev))` | ¶6–¶8 |
| `parse(fmt, tp, offset)` | `from_stream(is, F, tp, static_cast<basic_string<...>*>(nullptr), &offset)` | ¶9–¶11 |
| `parse(fmt, tp, abbrev, offset)` | `from_stream(is, F, tp, addressof(abbrev), &offset)` | ¶12–¶14 |

*Constraints*（¶4、¶7、¶10、¶13）要求对应的 `from_stream` 调用作为不求值操作数是良构的。所以对一个没有 `from_stream` 的类型调用 `parse`，`parse` 本身就不可行，错误出现在调用处，而不是深层的实例化里。

*Returns*（¶5、¶8、¶11、¶14）是一个未指定类型的操纵符：表达式 `is >> parse(...)` 的类型是 `basic_istream<charT, traits>&`，值是 `is`，并且调用相应的 `from_stream`。

取 `abbrev` 的地址用的是 `addressof` 而不是 `&`。`basic_string<charT, traits, Alloc>` 的模板实参可以是用户定义的类型，ADL 可能找到用户为它重载的一元 `operator&`。对可能涉及用户类型的对象一律用 `addressof`，是标准库的一贯做法。

### 悬空的格式串（¶2）

```cpp
auto m = parse(std::string("%F"), ymd);   // 临时 string 在这一行结束时销毁
in >> m;                                  // 操纵符里的指针已经悬空：UB
```

操纵符只保存格式串的指针。¶2 *Recommended practice* 建议实现让意外保存或使用这种操纵符变得困难，例如让操纵符不可移动，并禁止向这种操纵符的左值做流提取。

单靠不可移动挡不住第一行：C++17 起，`auto m = parse(...)` 依靠保证的复制消除（[[class.copy.elision]]）照样能编译。所以建议的后半句是禁止对左值提取，这样第二行编译失败，只剩下 `in >> parse(...)` 这种在同一个完整表达式里创建并使用的写法。这只是建议，可移植的代码应当自觉只用这种写法。

## 解析的通用规则（¶15–¶17）

¶15 所有 `from_stream` 都表现为**无格式输入函数**（[[istream.unformatted]]）：构造 sentry 时不跳过前导空白。它们对之后 `gcount()` 的返回值有什么影响，是未指定的。

格式串由普通字符和以 `%` 开头的标志组成。有些标志可以用 `E` 或 `O` 修饰，有些可以带一个正整数宽度 *N*，表示最多读取多少个字符，如 `%4Y`。格式串中表 134 没有列出的字符，除空白之外，都必须与输入逐字匹配。格式串里的一个空白字符匹配输入中零个或多个空白字符。

¶16 被解析的类型无法表示某个标志所指的信息时，调用 `is.setstate(ios_base::failbit)`。例 1：duration 不能表示星期几。与格式化一样，一天中的时间类的标志（`%H`、`%I`、`%p` 等）对 duration 解释为从午夜起经过的时间。

¶17 没能解析完格式串规定的全部内容，或者解析出的信息不足以确定一个完整的 duration、time_point 或历法类型，调用 `setstate(failbit)`：

```cpp
year_month_day ymd;
std::istringstream{"2024-03"} >> parse("%Y-%m", ymd);   // failbit：没有日
year_month ym;
std::istringstream{"2024-03"} >> parse("%Y-%m", ym);    // OK
```

各个 `from_stream` 还规定，解析失败时不修改目标对象（例如 [[time.clock.system.nonmembers#6]]）。所以失败后 `ymd` 保持原值，使用前要检查流的状态。

## 解析标志（表 134）

大部分标志与 [[time.format]] 表 133 的格式化说明符对称，下面只列出解析特有的规则。带宽度的标志都允许、但不要求前导零。

| 标志 | 解析规则 | 默认宽度 *N* |
|---|---|---|
| `%a` `%A` | locale 的星期名，完整名或缩写均可，大小写不敏感 | |
| `%b` `%B` `%h` | locale 的月名，完整名或缩写均可，大小写不敏感 | |
| `%Y` | 年 | 4 |
| `%y` | 年的末两位；没有用 `%C` 等给出世纪时，69–99 视为 1969–1999，00–68 视为 2000–2068 | 2 |
| `%C` | 世纪 | 2 |
| `%m` `%d` `%e` `%H` `%I` `%M` | 月、日、时、分 | 2 |
| `%j` | 一年中的第几天；对 duration 是天数 | 3 |
| `%S` | 秒；目标精度能换算成整秒时默认宽 2，否则宽度由目标的十进制精度决定，按定点 `long double` 读取，小数点由 locale 决定 | 2 或更宽 |
| `%u` `%w` | 星期的数字（ISO 编码 / C 编码） | 1 |
| `%U` `%W` `%V` `%G` `%g` | 周数、ISO 周历年 | 2、2、2、4、2 |
| `%F` | `%Y-%m-%d`；带宽度 *N* 时只作用于 `%Y` | |
| `%z` | `[+|-]hh[mm]`：`-0430`、`04` | |
| `%Ez` `%Oz` | `[+|-]h[h][:mm]`：`-04:30`、`4` | |
| `%Z` | 时区缩写或名字：一个单词，只能含基本字符集中的字母、数字和 `_` `/` `-` `+` | |
| `%n` | 恰好一个空白字符 | |
| `%t` | 零个或一个空白字符 | |
| `%%` | 一个 `%` | |

`%y` 的 69/68 分界与 POSIX `strptime` 相同。表中 `%y` 一行的例 2：`istringstream{"-20 76"} >> parse("%3C %y", y)` 得到 `-1976y`。`%3C` 最多读 3 个字符，读入了带符号的 `-20`；世纪已经给出，`%y` 不再套用窗口。

空格、`%n`、`%t` 组合起来可以描述各种空白模式。`%n` 一行的注 1 举例：`"%n "` 匹配一个或多个空白，`"%n%t%t"` 匹配一到三个空白。

`%Z` 读到的字符串只通过 `abbrev` 输出参数交给调用者，不参与时间换算。时区缩写不唯一（[[time.zone]]），标准不尝试从它推算偏移。

## 偏移：`sys_time` 与 `local_time` 的区别

开头的例子用同一段输入解析了两次，结果不同。`%z` 成功解析时，各时钟的 `from_stream` 有两种行为：

- `sys_time`、`utc_time`、`tai_time`、`gps_time`、`file_time`：把偏移写入 `*offset`（如果非空），并从解析出的时间中减去偏移，结果是真正的 UTC 时刻（[[time.clock.system.nonmembers#6]] 等）。
- `local_time`：只把偏移写入 `*offset`，不修改时间，因为本地时间本来就不对齐 UTC（[[time.clock.local#5]]）。

## 为自定义类型提供解析

`parse` 通过 ADL 查找 `from_stream`，所以只要在类型所在的命名空间里写一个签名兼容的 `from_stream`：

```cpp
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
        if (is) d.ymd = tmp;                                     // 失败时不修改 d
        return is;
    }
}

int main() {
    app::date d;
    std::istringstream{"2024-02-29"} >> std::chrono::parse("%F", d);   // ADL 找到 app::from_stream
    std::cout << d.ymd << '\n';
}
```

## 常见误解

!!! pitfall "解析失败会抛异常"
    `parse` 失败只设置 `failbit`，除非流设置了 `exceptions()`，不会抛异常，目标对象保持原值。`in >> parse(...);` 之后必须检查 `in`。

!!! pitfall "没有偏移的时间可以直接解析进 `sys_time`"
    来自用户界面的 `"2024-03-01 08:00:00"` 几乎总是本地时间。把它解析进 `sys_seconds` 不会报错，但得到的是 UTC 08:00。应当解析进 `local_seconds`，再经由 `time_zone` 或 `zoned_time` 换算（[[time.zone]]）。

!!! pitfall "格式串里的空格只匹配一个空格"
    一个空格匹配零个或多个空白，所以 `parse("%F %T", tp)` 也接受 `"2024-03-01      13:05:07"`，甚至 `"2024-03-0113:05:07"`。需要严格匹配一个空白时用 `%n`。

## 小结

- `is >> parse(fmt, x)` 经由 ADL 调用 `from_stream`；用户类型提供自己的 `from_stream` 即可接入。
- 失败时设置 `failbit`、不修改目标；信息不足（如解析 `year_month_day` 缺日）同样算失败。
- 解析标志与格式化说明符大体对称，另有最大宽度 *N*、名称大小写不敏感、`%y` 的世纪窗口和空白匹配规则。
- `sys_time` 一族会减去 `%z` 偏移得到 UTC，`local_time` 不会。
- 操纵符可能引用临时的格式串，要在同一个完整表达式里创建并使用它。
