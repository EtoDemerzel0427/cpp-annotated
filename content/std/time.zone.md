---
title: 时区
summary: IANA 时区数据库在 C++ 中的模型——tzdb / tzdb_list 与运行期更新、time_zone 如何在 sys_time 与 local_time 之间换算、夏令时切换造成的"不存在"与"有歧义"的本地时间及 choose、zoned_time 的不变式与推导指引、sys_info/local_info、闰秒表与时区别名
status: done
covers: *
papers: P0355R7
related: time.clock, time.cal, time.format, time.parse, time.hash
tags: 标准库, chrono, 时区, 夏令时, 闰秒
updated: 2026-10-18
---

[time.zone.general] ¶1：本节描述访问 IANA 时区数据库的接口，它与 `sys_time` 和 `local_time` 协作，为历法类型和用户自定义历法提供时区支持。

时区规则不是数学，而是政治：哪些地区用夏令时、哪天切换、标准偏移是多少，各国政府随时会改，IANA 数据库每年发布若干个版本。所以时区信息**不能**像 `sys_days` ↔ `year_month_day` 那样写成编译期算法，只能在运行期查一个数据库。本节的设计围绕三个问题展开：

1. 数据库从哪里来、运行中能否更新、更新后旧指针是否还有效？（[time.zone.db]）
2. 本地时间与 UTC 如何互换？夏令时切换时一个本地时间可能**不存在**或**出现两次**，怎么办？（[time.zone.timezone]、[time.zone.exception]、[time.zone.info]）
3. 怎样把"一个时刻 + 一个时区"打包成一个值来传递和格式化？（[time.zone.zonedtime]）

!!! impl "libc++ 的状况"
    本页所有例子**无法在本机 libc++ 上编译**：本机 Homebrew 构建的 `__config_site` 将 `_LIBCPP_HAS_TIME_ZONE_DATABASE` 定义为 0，`tzdb`、`time_zone`、`zoned_time`、`leap_second` 等名字都不存在；即使在启用了时区数据库的 libc++ 构建中，这部分也属于实验特性（受 `_LIBCPP_HAS_EXPERIMENTAL_TZDB` 控制，需要 `-fexperimental-library`）。例子按标准编写，输出取自标准的示例或按 IANA 数据推出；可在 Compiler Explorer 上用较新的 GCC 或 MSVC 运行。

## 时区数据库（[time.zone.db]）

### tzdb（[time.zone.db.tzdb]）

```cpp
struct tzdb {
  string                 version;        // 如 "2024a"
  vector<time_zone>      zones;
  vector<time_zone_link> links;
  vector<leap_second>    leap_seconds;
  const time_zone* locate_zone(string_view tz_name) const;
  const time_zone* current_zone() const;
};
```

- ¶1：每个 vector 都已排序，便于快速查找（`time_zone` 与 `time_zone_link` 按名字，`leap_second` 按日期）。
- ¶2：`locate_zone(name)`：先在 `zones` 中找名字等于 `name` 的时区；找不到再在 `links` 中找同名的别名，返回其 `target()` 指向的时区。
- ¶3：都找不到时抛 `runtime_error`。注 2：正常返回时，返回值总指向一个有效的 `time_zone`——**永远不返回空指针**。
- ¶4：`current_zone()` 返回计算机设置的本地时区。

### tzdb_list（[time.zone.db.list]）

- ¶1：`tzdb_list` 是单例，唯一对象通过 `get_tzdb_list()` 访问；它包含一个 `tzdb` 的列表。注 1：只有需要长时间运行、并在运行中更新时区数据库的程序才需要直接访问它；其他程序通过 `get_tzdb()`、`locate_zone()`、`current_zone()` 隐式使用列表的 `front()`。
- 不可复制；构造方式未指明。
- ¶2：`const_iterator` 是常量迭代器，满足 *Cpp17ForwardIterator*，值类型为 `tzdb`。
- ¶3–¶4：`front()` 返回第一个 `tzdb`；*Synchronization*：与 `reload_tzdb()` 之间是线程安全的。注 2：`reload_tzdb()` 把新的 `tzdb` 推到最前面。
- ¶5–¶9：`erase_after(p)`：前置条件是 `p` 之后的迭代器可解引用；删除它指向的 `tzdb`。*Postconditions*：除了被删的那个，**不使任何指针、引用、迭代器失效**。注 3：不可能删除 `begin()` 指向的那个。不抛异常。
- ¶10–¶13：`begin`、`end`、`cbegin`、`cend`。

这是一个**单向链表**的接口（`front`、`erase_after`、前向迭代器），选择链表的原因正是 ¶7 的保证：新版本推到前面、旧版本留在后面，所有已经拿到的 `const time_zone*` 继续有效。程序可以放心地缓存 `locate_zone` 返回的指针，只要自己不 `erase_after` 掉它所在的 `tzdb`。

### 访问函数（[time.zone.db.access]）

| 函数 | 效果 | 段落 |
|---|---|---|
| `get_tzdb_list()` | 首次访问时初始化数据库（得到只含一个 `tzdb` 的列表）；多线程同时调用是安全的；无法得到有效数据库时抛 `runtime_error` | ¶1–¶4 |
| `get_tzdb()` | `get_tzdb_list().front()` | ¶5 |
| `locate_zone(name)` | `get_tzdb().locate_zone(name)`；注 1：首次引用会初始化数据库 | ¶6–¶7 |
| `current_zone()` | `get_tzdb().current_zone()` | ¶8 |

数据库是**惰性**初始化的：不用时区的程序不付出加载代价。首次调用可能较慢（要读取并解析系统的 zoneinfo 文件），也可能抛异常——这就是 `utc_clock::now()` 不能标 `noexcept` 的根源（[[time.clock]]）。

### 远程数据库（[time.zone.db.remote]）

- ¶1：**本地时区数据库**是程序首次访问时实现提供的那个。运行期间实现可以更新它，但更新**不得以任何方式影响程序**，除非程序调用本小节的函数。这个可能更新过的数据库叫**远程时区数据库**（[[g:remote-time-zone-database]]）。
- ¶2–¶6：`reload_tzdb()`：比较远程与本地的版本，相同则无效果；否则把远程数据库推到 `tzdb_list` 前面。与 `front()`、`erase_after()` 之间线程安全；不使任何指针、引用、迭代器失效；返回 `front()`；失败时抛 `runtime_error`。
- ¶7：`remote_version()` 返回最新的远程版本号。注 1：可与 `get_tzdb().version` 比较，判断是否需要重新加载。

"不得影响程序"这条保证很重要：即使操作系统在程序运行中更新了 zoneinfo 文件，同一个程序里前后两次 `locate_zone("America/New_York")->to_local(t)` 也必须给出相同结果，除非程序主动 `reload_tzdb()`。

## sys_info 与 local_info（[time.zone.info]）

### sys_info（[time.zone.info.sys]）

```cpp
struct sys_info {
  sys_seconds begin;
  sys_seconds end;
  seconds     offset;
  minutes     save;
  string      abbrev;
};
```

- ¶1：由一个 `time_zone` 加一个 `sys_time` 或 `local_time` 得到；也可从 `zoned_time` 得到。¶2（注 1）：这是低层接口，通常的换算会隐式使用它。
- ¶3：在 [`begin`, `end`) 区间内，`offset` 与 `abbrev` 有效。据此可以高效地遍历一个时区的所有切换点（从 `end` 再查下一个）。
- ¶4：`offset` 是 UTC 偏移，关系式为 `offset = local_time − sys_time`。北京是 `+8h`，纽约冬季是 `−5h`。
- ¶5：`save` 是附加信息：`save != 0min` 表示处于"夏令时"，`offset − save` **暗示**不在夏令时时的偏移。但这不权威——唯一可靠的办法是查一个 `save == 0min` 的时刻，而这样的时刻保证不在当前的 [`begin`, `end`) 中。
- ¶6：`abbrev` 是当前的缩写，如 `EST`、`CST`。缩写**不唯一**：`CST` 可以是美国中部标准时间、中国标准时间或古巴标准时间，所以不能从缩写反推时区或偏移。
- ¶7–¶8：`operator<<` 以未指明的格式输出。

### local_info（[time.zone.info.local]）

```cpp
struct local_info {
  static constexpr int unique      = 0;
  static constexpr int nonexistent = 1;
  static constexpr int ambiguous   = 2;
  int result;
  sys_info first;
  sys_info second;
};
```

¶2 描述 `local_time` → `sys_time` 换算的三种结果：

| `result` | 含义 | `first` | `second` |
|---|---|---|---|
| `unique`（¶2.1） | 唯一对应一个 UTC 时刻 | 正确的 `sys_info` | 零初始化 |
| `nonexistent`（¶2.2） | 该本地时间落在"跳过"的区间里 | 在该本地时间之前结束的 `sys_info` | 在其之后开始的 `sys_info` |
| `ambiguous`（¶2.3） | 该本地时间出现了两次 | 在其之后结束的 `sys_info` | 在其之前开始的 `sys_info` |

¶3–¶4：`operator<<` 以未指明的格式输出。

## 不存在的与有歧义的本地时间（[time.zone.exception]）

夏令时开始时，时钟从 2:00 直接跳到 3:00，于是 2:30 这个本地时间**不存在**；夏令时结束时，时钟从 2:00 退回 1:00，于是 1:30 出现**两次**。把这样的 `local_time` 转成 `sys_time` 没有唯一答案。

### nonexistent_local_time（[time.zone.exception.nonexist]）

- ¶1：将不存在的 `local_time` 转换为 `sys_time` 且未指定 `choose::earliest` 或 `choose::latest` 时抛出。派生自 `runtime_error`。
- ¶2：构造的前置条件是 `i.result == local_info::nonexistent`。
- ¶3：`what()` 的内容由 ¶3 的代码精确规定，说明该时间落在哪两个偏移之间的"空隙"里。

¶4 的例子（2016 年纽约夏令时开始于 3 月第二个星期日 2:00）：

```cpp title="tz-gap.cpp" ok
#include <chrono>
#include <iostream>

int main() {
    using namespace std::chrono;
    try {
        auto zt = zoned_time{"America/New_York",
                             local_days{Sunday[2]/March/2016} + 2h + 30min};
    } catch (const nonexistent_local_time& e) {
        std::cout << e.what() << '\n';
    }
}
```

标准给出的输出：

```text
2016-03-13 02:30:00 is in a gap between
2016-03-13 02:00:00 EST and
2016-03-13 03:00:00 EDT which are both equivalent to
2016-03-13 07:00:00 UTC
```

注意 `local_days{Sunday[2]/March/2016}`：`Sunday[2]/March` 是 `month_weekday`，`/2016` 补上年份得到 `year_month_weekday`，再显式转换为 `local_days`（[[time.cal]]）。

### ambiguous_local_time（[time.zone.exception.ambig]）

- ¶1：将有歧义的 `local_time` 转换为 `sys_time` 且未指定 `choose` 时抛出。
- ¶2：前置条件 `i.result == local_info::ambiguous`。¶3：`what()` 的格式同样由代码规定。

¶4 的例子（2016 年纽约夏令时结束于 11 月第一个星期日 2:00）：

```cpp title="tz-ambiguous.cpp" ok
#include <chrono>
#include <iostream>

int main() {
    using namespace std::chrono;
    try {
        auto zt = zoned_time{"America/New_York",
                             local_days{Sunday[1]/November/2016} + 1h + 30min};
    } catch (const ambiguous_local_time& e) {
        std::cout << e.what() << '\n';
    }
}
```

标准给出的输出：

```text
2016-11-06 01:30:00 is ambiguous.  It could be
2016-11-06 01:30:00 EDT == 2016-11-06 05:30:00 UTC or
2016-11-06 01:30:00 EST == 2016-11-06 06:30:00 UTC
```

## time_zone（[time.zone.timezone]）

```cpp
enum class choose {earliest, latest};

class time_zone {
public:
  time_zone(time_zone&&) = default;
  time_zone& operator=(time_zone&&) = default;
  // 其他构造函数未指明
  string_view name() const noexcept;
  template<class Duration> sys_info   get_info(const sys_time<Duration>& st)   const;
  template<class Duration> local_info get_info(const local_time<Duration>& tp) const;
  template<class Duration> sys_time<common_type_t<Duration, seconds>>
    to_sys(const local_time<Duration>& tp) const;
  template<class Duration> sys_time<common_type_t<Duration, seconds>>
    to_sys(const local_time<Duration>& tp, choose z) const;
  template<class Duration> local_time<common_type_t<Duration, seconds>>
    to_local(const sys_time<Duration>& tp) const;
};
```

[time.zone.overview] ¶1：`time_zone` 表示一个地理区域的全部时区切换。构造方式未指明，在数据库初始化时完成。注 1：通过 `locate_zone` 等函数访问 `const time_zone` 对象。用户无法自己创建 `time_zone`——它只能来自数据库。

成员（[time.zone.members]）：

- ¶1–¶2：`name()`，如 `"America/New_York"`。
- ¶3：`get_info(sys_time st)` 返回使 `st` ∈ [`i.begin`, `i.end`) 的 `sys_info`。¶4：`get_info(local_time)` 返回 `local_info`。
- ¶5–¶6：`to_sys(tp)`：返回 `tp` 按本时区规则对应的 UTC 时刻，精度至少为秒（输入更精细则更精细）。有歧义时抛 `ambiguous_local_time`，不存在时抛 `nonexistent_local_time`。
- ¶7：`to_sys(tp, z)`：有歧义时，`choose::earliest` 返回较早的那个 UTC 时刻，`choose::latest` 返回较晚的；**不存在时，两个候选 UTC 时刻相同（都是切换点），返回该时刻**——此时 `choose` 没有区别。
- ¶8：`to_local(tp)`：返回 `tp` 在本时区的本地时间。`sys_time` → `local_time` 总是唯一的，不会抛。

返回类型都是 `common_type_t<Duration, seconds>`：时区偏移以秒计，所以即使输入是 `local_days`，结果也至少是秒精度。

非成员（[time.zone.nonmembers]）¶1–¶2：`==` 与 `<=>` 比较 `name()`。

¶7 中"不存在时返回切换点"的选择值得注意：本地 2:30 在 2:00 → 3:00 的空隙里，`to_sys(2:30, choose::earliest)` 和 `to_sys(2:30, choose::latest)` 都返回 07:00 UTC（即本地 3:00 EDT），而不是"往前推 30 分钟"或"往后推 30 分钟"。

## zoned_traits（[time.zone.zonedtraits]）

```cpp
template<class T> struct zoned_traits {};

template<> struct zoned_traits<const time_zone*> {
  static const time_zone* default_zone();                    // locate_zone("UTC")
  static const time_zone* locate_zone(string_view name);     // std::chrono::locate_zone(name)
};
```

¶1：`zoned_traits` 用于定制 `zoned_time<Duration, TimeZonePtr>` 的默认构造函数以及接受 `string_view` 的构造函数的行为。¶2–¶3：标准为 `const time_zone*` 提供的特化中，默认时区是 **UTC**（不是本地时区），按名字查找就转发给 `locate_zone`。

`TimeZonePtr` 可以是任何"像指向时区的指针"的类型——用 `->` 能调用 `to_sys`、`to_local`、`get_info`。用户可以提供自己的时区类型（例如一个固定偏移的时区，或者一个从别的数据源加载的时区），并按需特化 `zoned_traits` 以启用默认构造和按名构造；不特化时，这些构造函数的 *Constraints* 不满足，直接不可用。

## zoned_time（[time.zone.zonedtime]）

```cpp
template<class Duration, class TimeZonePtr = const time_zone*>
class zoned_time {
public:
  using duration = common_type_t<Duration, seconds>;
private:
  TimeZonePtr        zone_;
  sys_time<duration> tp_;
  // ...
};
using zoned_seconds = zoned_time<seconds>;
```

### 不变式（overview ¶1–¶3）

- ¶1：`zoned_time` 是时区与时刻的逻辑配对。它维持不变式：**总是指向一个有效的时区，并且表示的时刻在该时区中存在且无歧义**。
- ¶2：`Duration` 不是 duration 的特化时，程序非良构。
- ¶3：所有以 `string_view` 为第一个形参的构造函数**不参与类模板实参推导**（[[over.match.class.deduct]]）。

内部存的是 `sys_time`，而不是 `local_time`。这正是不变式能成立的原因：一个 UTC 时刻在任何时区都对应唯一的本地时间，反之则不然。所有从 `local_time` 构造的路径都必须在构造时就把歧义解决掉（抛异常或用 `choose`）。

### 构造函数（[time.zone.zonedtime.ctor]）

| 形式 | 效果 | *Constraints* / 前置条件 | 段落 |
|---|---|---|---|
| `zoned_time()` | 默认时区 + 纪元 | `traits_::default_zone()` 良构 | ¶1–¶2 |
| `zoned_time(sys_time)` | 默认时区 + 该时刻 | 同上 | ¶3–¶4 |
| `explicit zoned_time(TimeZonePtr z)` | 该时区 + 纪元 | 前置：`z` 指向时区 | ¶5–¶6 |
| `explicit zoned_time(string_view name)` | 按名查找 | `traits_::locate_zone` 良构 | ¶7–¶8 |
| `zoned_time(const zoned_time<D2, TimeZonePtr>&)` | 转换精度 | `sys_time<D2>` 可隐式转换为 `sys_time<Duration>` | ¶9–¶10 |
| `zoned_time(z, sys_time)`、`(name, sys_time)` | 直接存储 | 前置：`z` 指向时区 | ¶11–¶14 |
| `zoned_time(z, local_time)`、`(name, local_time)` | `z->to_sys(tp)`：歧义或不存在时**抛异常** | `z->to_sys(local_time)` 可用 | ¶15–¶19 |
| `zoned_time(z, local_time, choose)`、`(name, ..., choose)` | `z->to_sys(tp, c)` | 同上 | ¶20–¶24 |
| `zoned_time(z, const zoned_time<D2, TZ2>&)`、`(name, ...)` | 同一时刻换个时区 | 精度可转换；前置：`z` 指向有效时区 | ¶25–¶27、¶32–¶33 |
| 上一行加 `choose` | 同上，**`choose` 无作用** | 同上 | ¶28–¶31、¶34–¶36 |

¶31 与 ¶36 的注特别说明：从另一个 `zoned_time` 构造时 `choose` 形参没有作用——源对象存的是 UTC 时刻，换时区不会产生歧义。这两个重载存在，只是为了让泛型代码可以统一地传入 `choose`。

### 推导指引

概要中的推导指引借助一个仅用于说明的别名 *time-zone-representation*：若实参可转换为 `string_view`，时区指针类型取 `const time_zone*`，否则取实参类型本身（去 cvref）。精度一律取 `common_type_t<Duration, seconds>`。所以：

```cpp
zoned_time zt1{"Asia/Shanghai", sys_days{2024y/January/1}};
    // zoned_time<seconds, const time_zone*>：days 与 seconds 的公共类型是 seconds
zoned_time zt2{current_zone(), system_clock::now()};
    // zoned_time<system_clock::duration, const time_zone*>
```

¶3 把以 `string_view` 开头的构造函数排除在 CTAD 之外，效果是：凡是以时区名开头的推导，都只经由上面的显式推导指引完成——时区指针类型统一取 `const time_zone*`，精度统一取 `common_type_t<Duration, seconds>`，不会出现由构造函数隐式生成的推导指引给出另一种结果（例如直接从 `sys_time<days>` 推出 `zoned_time<days>`）的情况。

### 成员（[time.zone.zonedtime.members]）

- ¶1–¶2：`operator=(sys_time)`：之后 `get_sys_time() == st`；时区不变。
- ¶3–¶4：`operator=(local_time)`：之后 `get_local_time() == lt`；时区不变。这里没有 `choose` 参数——遇到歧义或不存在的本地时间时，经由 `to_sys` 抛异常。
- ¶5：隐式转换为 `sys_time<duration>`；¶6：**显式**转换为 `local_time<duration>`——又是"sys 隐式、local 显式"的规律。
- ¶7–¶10：`get_time_zone()`、`get_local_time()`（`zone_->to_local(tp_)`）、`get_sys_time()`、`get_info()`（`zone_->get_info(tp_)`）。

`get_local_time()` 每次调用都会查一次时区规则；在循环里反复调用时，考虑把结果存下来。

### 非成员（[time.zone.zonedtime.nonmembers]）

- ¶1：`==` 比较 `zone_` 和 `tp_`。两个 `zoned_time` 的 `TimeZonePtr` 必须相同，`Duration` 可以不同。注意比较的是**指针**：同一数据库中同名时区是同一个对象，但来自两个不同 `tzdb` 版本的同名时区指针不相等。
- ¶2：`os << zt` 等价于 `format(os.getloc(), "{:L%F %T %Z}", zt)`，输出本地时间加缩写。

```cpp title="zoned.cpp" ok
#include <chrono>
#include <iostream>
using namespace std::chrono;

int main() {
    auto meeting = zoned_time{"America/New_York", local_days{2024y/March/15} + 9h};
    std::cout << meeting << '\n';                                    // 2024-03-15 09:00:00 EDT
    std::cout << zoned_time{"Asia/Shanghai", meeting} << '\n';       // 2024-03-15 21:00:00 CST
    std::cout << zoned_time{"Europe/London", meeting} << '\n';       // 2024-03-15 13:00:00 GMT
    std::cout << meeting.get_sys_time() << " UTC\n";                 // 2024-03-15 13:00:00 UTC
}
```

## leap_second（[time.zone.leap]）

- overview ¶1：代表闰秒插入日期和值的 `leap_second` 对象在时区数据库初始化时构造并存储（`tzdb::leap_seconds`）。可复制；构造方式未指明。
- ¶2 的例子列出 1972-07-01 到 2017-01-01 共 27 个闰秒。
- members ¶1：`date()` 返回插入闰秒的日期时间（`sys_seconds`）。¶2：`value()` 返回 `+1s`（正闰秒）或 `-1s`（负闰秒）。注 1：截至 2022 年插入的全是正闰秒。
- nonmembers ¶1–¶12：两个 `leap_second` 按 `date()` 比较；`leap_second` 与任意精度的 `sys_time` 之间可以直接比较（`==`、`<`、`>`、`<=`、`>=`、`<=>`），所以可以写 `if (l <= sys_days{2018y/March/17d})`。

`utc_clock` 的 `from_sys`/`to_sys` 正是查这张表实现的（[[time.clock]]）。负闰秒在规则中可能发生但从未发生过，标准的接口为它留了位置（`value()` 为 `-1s`）。

## time_zone_link（[time.zone.link]）

- overview ¶1：为某个 `time_zone` 提供别名。在数据库初始化时构造。只能移动。
- members ¶1–¶2：`name()` 是别名，`target()` 是被指向时区的名字。
- nonmembers ¶1–¶2：按 `name()` 比较。

例如 `"US/Eastern"` 是 `"America/New_York"` 的别名，`"Asia/Chongqing"` 是 `"Asia/Shanghai"` 的别名（具体以数据库版本为准）。`locate_zone` 会透明地解析别名（[time.zone.db.tzdb] ¶2），所以 `locate_zone("US/Eastern")->name()` 返回的是 `"America/New_York"`。

## 陷阱

!!! pitfall "把 local_time 当作 sys_time"
    `sys_days{2024y/March/15} + 9h` 是 **UTC** 的 9:00，不是纽约的 9:00。从用户输入得到的"日期 + 时间"几乎总是本地时间，应当构造 `local_days{...} + 9h`，再经由时区换算。类型系统会阻止你把 `local_time` 直接传给需要 `sys_time` 的地方，但不会阻止你一开始就选错类型。

!!! pitfall "默认构造与 sys_time 构造的时区是 UTC，不是本地"
    `zoned_time zt{system_clock::now()};` 的时区是 UTC（`zoned_traits<const time_zone*>::default_zone()` 返回 `locate_zone("UTC")`）。要本地时区，写 `zoned_time{current_zone(), system_clock::now()}`。

!!! pitfall "从 local_time 构造会抛异常"
    `zoned_time{"America/New_York", lt}` 在 `lt` 落入夏令时空隙或重叠时抛异常。处理用户输入时应当先用 `get_info(local_time)` 检查 `result`，或者直接传 `choose::earliest` / `choose::latest`。对"每天 2:30 执行的任务"这类需求，`choose` 的选择就是业务决策。

!!! pitfall "时区缩写不是标识符"
    `sys_info::abbrev` 和格式化中的 `%Z` 只供人看。`CST`、`IST`、`BST` 都对应多个时区，存储与传输时应使用 IANA 名（`"Asia/Shanghai"`）或 UTC 偏移。

## 思考题

1. 为什么 `zoned_time` 内部存 `sys_time` 而不是 `local_time`？

<details markdown="1">
<summary>答案</summary>

¶1 的不变式要求时刻"在该时区中存在且无歧义"。`sys_time` → `local_time` 是函数（每个 UTC 时刻在任何时区都有唯一的本地时间），`local_time` → `sys_time` 不是。存 `sys_time` 时不变式自动成立，`get_local_time()` 总能计算；若存 `local_time`，换时区、比较、格式化 `%z` 时都要重新面对歧义。此外，存 UTC 让 `==` 直接比较物理时刻。
</details>

2. `to_sys(lt, choose::earliest)` 与 `to_sys(lt, choose::latest)` 什么时候结果相同？

<details markdown="1">
<summary>答案</summary>

`lt` 唯一（`local_info::unique`）时显然相同；`lt` 不存在（落在空隙中）时也相同——¶7 规定两个候选 UTC 时刻是同一个切换点并返回它。只有在 `ambiguous` 时，二者才相差一个偏移差（通常 1 小时）。
</details>

3. 程序缓存了 `const time_zone* ny = locate_zone("America/New_York");`，之后调用了 `reload_tzdb()`。`ny` 还有效吗？它会用新规则吗？

<details markdown="1">
<summary>答案</summary>

仍然有效：[time.zone.db.remote] ¶4 规定 `reload_tzdb` 不使任何指针失效。但它指向的是**旧** `tzdb` 中的对象，使用旧规则。要用新规则需要重新 `locate_zone`（它查的是 `front()`，即新版本）。只有调用 `erase_after` 删除了旧 `tzdb` 之后，`ny` 才会悬空。
</details>

## 小结

| 组件 | 要点 |
|---|---|
| `tzdb` / `tzdb_list` | 惰性加载；新版本推到前面；旧指针永不失效（除非 `erase_after`） |
| `time_zone` | 只能来自数据库；`to_local` 总唯一，`to_sys` 可能抛 `nonexistent_local_time` / `ambiguous_local_time` |
| `choose` | 歧义时选早或晚；不存在时都返回切换点 |
| `sys_info` / `local_info` | `offset = local − sys`；`abbrev` 不唯一；`local_info::result` 区分三种情况 |
| `zoned_time` | 时区 + `sys_time`；不变式：时刻存在且无歧义；默认时区是 UTC |
| `leap_second` | 闰秒表，供 `utc_clock` 使用 |
| libc++ | 本机不可用（构建时关闭）；上游属实验特性 |
