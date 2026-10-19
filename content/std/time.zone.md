---
title: 时区
summary: C++ 怎样使用 IANA 时区数据库：tzdb 与 tzdb_list 的加载和运行期更新，time_zone 怎样在 sys_time 与 local_time 之间换算，夏令时切换造成的不存在和有歧义的本地时间，zoned_time 的不变式，以及闰秒表和时区别名。
status: done
covers: *
papers: P0355R7
related: time.clock, time.cal, time.format, time.parse, time.hash
tags: 标准库, chrono, 时区, 夏令时, 闰秒
updated: 2026-10-19
---

!!! tldr
    - 时区规则由各国政府决定、随时会改，所以只能在运行期查 IANA 数据库。数据库在第一次使用时加载，可能抛异常。
    - `time_zone::to_local` 总有唯一结果；`to_sys` 遇到夏令时开始时跳过的本地时间会抛 `nonexistent_local_time`，遇到结束时重复的本地时间会抛 `ambiguous_local_time`，传入 `choose::earliest` 或 `choose::latest` 可以避免。
    - `zoned_time` 把一个时区和一个 `sys_time` 打包在一起，保证表示的时刻在该时区中存在且无歧义；默认时区是 UTC，不是本机时区。
    - 重新加载数据库不会使已经拿到的 `const time_zone*` 失效，但旧指针继续使用旧规则。
    - 本机 libc++ 的构建关闭了时区数据库，本页的例子都无法在本机编译。

## 一个例子

```cpp title="zoned.cpp"
#include <chrono>
#include <iostream>
using namespace std::chrono;

int main() {
  auto meeting = zoned_time{"America/New_York", local_days{2024y/March/15} + 9h};
  std::cout << meeting << '\n';                               // 2024-03-15 09:00:00 EDT
  std::cout << zoned_time{"Asia/Shanghai", meeting} << '\n';  // 2024-03-15 21:00:00 CST
  std::cout << zoned_time{"Europe/London", meeting} << '\n';  // 2024-03-15 13:00:00 GMT
  std::cout << meeting.get_sys_time() << " UTC\n";            // 2024-03-15 13:00:00 UTC
}
```

纽约时间 3 月 15 日上午 9 点开会，换算成上海和伦敦的时间。`local_days{...} + 9h` 是一个时区尚未确定的本地时间，交给 `zoned_time` 时才和纽约的规则绑在一起。2024 年美国的夏令时从 3 月 10 日开始，所以纽约此时是 UTC−4（EDT），英国要到 3 月 31 日才切换，伦敦仍是 GMT。

!!! impl "libc++ 的状况"
    本页的例子都无法在本机编译。本机 Homebrew 构建的 libc++ 把 `_LIBCPP_HAS_TIME_ZONE_DATABASE` 定义为 0，`tzdb`、`time_zone`、`zoned_time`、`leap_second` 等名字都不存在。即使在启用了时区数据库的 libc++ 构建中，这部分也属于实验特性，需要 `-fexperimental-library`。例子按标准编写，注释中的输出取自标准的例子或者按 IANA 数据推出，可以在 Compiler Explorer 上用较新的 GCC 或 MSVC 运行。

¶1 [time.zone.general] 说明，本节描述访问 IANA 时区数据库的接口，它和 `sys_time`、`local_time` 协作，为历法类型和用户自定义的历法提供时区支持。

日期和 UTC 之间的换算是纯算术（[[time.cal]]），时区却不行。哪些地区用夏令时、哪天切换、标准偏移是多少，都由各国政府决定，随时会改，IANA 数据库每年都会发布若干个新版本。所以时区信息只能在运行期查数据库。

## 时区数据库 [time.zone.db]

### tzdb [time.zone.db.tzdb]

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

¶1 每个 vector 都已排序，便于快速查找。

¶2 `locate_zone(name)` 先在 `zones` 中找名字等于 `name` 的时区；找不到，再在 `links` 中找同名的别名，返回它的 `target()` 所指的时区。¶3 都找不到时抛 `runtime_error`。注 2 指出，正常返回时结果总是指向一个有效的 `time_zone`，永远不是空指针。

¶4 `current_zone()` 返回这台计算机设置的本地时区。

### 访问函数 [time.zone.db.access]

| 函数 | 效果 | 段落 |
|---|---|---|
| `get_tzdb_list()` | 首次调用时初始化数据库；多个线程同时调用是安全的；得不到有效的数据库时抛 `runtime_error` | ¶1–¶4 |
| `get_tzdb()` | `get_tzdb_list().front()` | ¶5 |
| `locate_zone(name)` | `get_tzdb().locate_zone(name)` | ¶6–¶7 |
| `current_zone()` | `get_tzdb().current_zone()` | ¶8 |

数据库是惰性初始化的，不用时区的程序不付出加载的代价。第一次调用可能比较慢，要读取并解析系统的 zoneinfo 文件，也可能抛异常。这就是 `utc_clock::now()` 不能是 `noexcept` 的根源（[[time.clock]]）：它要用到数据库里的闰秒表。

### tzdb_list 与运行期更新 [time.zone.db.list] [time.zone.db.remote]

[[time.zone.db.list#1]] 规定 `tzdb_list` 是单例，唯一的对象通过 `get_tzdb_list()` 访问，里面是一个 `tzdb` 的列表。注 1 说明，只有长时间运行、需要在运行中更新时区数据库的程序才需要直接使用它；其他程序通过 `get_tzdb()`、`locate_zone()`、`current_zone()` 隐式使用列表的第一个元素。

它的接口是一个单向链表：`front()`、`erase_after()` 和前向迭代器。选择链表，是为了这样一个保证：新版本推到最前面，旧版本留在后面，所有已经拿到的 `const time_zone*` 继续有效。`erase_after(p)` 删除 `p` 之后的那个 `tzdb`，第 7 段保证除了被删的那个，不使任何指针、引用或迭代器失效。注 3 指出，第一个元素不可能被删除。

[[time.zone.db.remote#1]] 区分了两个数据库。**本地时区数据库**是程序第一次访问时实现提供的那个。程序运行期间实现可以更新数据库，但更新不得以任何方式影响程序，除非程序调用了本小节的函数。可能已经更新过的那个数据库叫做**远程时区数据库**（[[g:remote-time-zone-database]]）。

¶2 `reload_tzdb()` 比较远程和本地数据库的版本：相同则什么也不做，不同就把远程数据库推到 `tzdb_list` 的最前面。¶4 它不使任何指针、引用或迭代器失效。¶7 `remote_version()` 返回远程数据库的最新版本，可以和 `get_tzdb().version` 比较，判断是否需要重新加载。

所以即使操作系统在程序运行中更新了 zoneinfo 文件，同一个程序里前后两次 `locate_zone("America/New_York")->to_local(t)` 也必须给出相同的结果，除非程序主动调用了 `reload_tzdb()`。

## 夏令时带来的两个问题

夏令时开始时，时钟从 2:00 直接跳到 3:00，2:30 这个本地时间不存在。夏令时结束时，时钟从 2:00 退回 1:00，1:30 出现两次。把这样的本地时间转换成 UTC，没有唯一的答案。

### 不存在的本地时间 [time.zone.exception.nonexist]

```cpp title="tz-gap.cpp"
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

2016 年纽约的夏令时从 3 月第二个星期日 2:00 开始。`Sunday[2]/March` 是 `month_weekday`，`/2016` 补上年份得到 `year_month_weekday`，再显式转换成 `local_days`（[[time.cal]]）。¶4 的例子给出的输出是：

```text
2016-03-13 02:30:00 is in a gap between
2016-03-13 02:00:00 EST and
2016-03-13 03:00:00 EDT which are both equivalent to
2016-03-13 07:00:00 UTC
```

¶1 把不存在的 `local_time` 转换为 `sys_time`、又没有指定 `choose::earliest` 或 `choose::latest` 时，抛出 `nonexistent_local_time`。它派生自 `runtime_error`，¶3 用一段代码精确规定了 `what()` 的内容。

### 有歧义的本地时间 [time.zone.exception.ambig]

```cpp title="tz-ambiguous.cpp"
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

2016 年纽约的夏令时在 11 月第一个星期日 2:00 结束。¶4 的例子给出的输出是：

```text
2016-11-06 01:30:00 is ambiguous.  It could be
2016-11-06 01:30:00 EDT == 2016-11-06 05:30:00 UTC or
2016-11-06 01:30:00 EST == 2016-11-06 06:30:00 UTC
```

¶1 把有歧义的 `local_time` 转换为 `sys_time`、又没有指定 `choose` 时，抛出 `ambiguous_local_time`。

## time_zone [time.zone.timezone]

```cpp
enum class choose {earliest, latest};

class time_zone {
public:
  time_zone(time_zone&&) = default;
  time_zone& operator=(time_zone&&) = default;
  // 其他构造函数未指定
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

[[time.zone.overview#1]] 规定，`time_zone` 表示一个地理区域的全部时区切换。它怎样构造未指定，构造发生在数据库初始化的时候。用户无法自己创建 `time_zone`，只能通过 `locate_zone` 等函数拿到数据库里的 `const time_zone`。

[[time.zone.members]] 的几个成员：

- ¶1 `name()` 返回时区名，如 `"America/New_York"`。
- ¶3 `get_info(sys_time st)` 返回一个 `sys_info`，`st` 落在它的区间之内；¶4 `get_info(local_time)` 返回 `local_info`（见下文）。
- ¶5 `to_sys(tp)` 按本时区的规则返回 `tp` 对应的 UTC 时刻。¶6 有歧义时抛 `ambiguous_local_time`，不存在时抛 `nonexistent_local_time`。
- ¶7 `to_sys(tp, z)` 遇到歧义时，`choose::earliest` 返回较早的 UTC 时刻，`choose::latest` 返回较晚的。遇到不存在的本地时间时，两个候选的 UTC 时刻相同，都是切换的那一刻，于是返回它，`choose` 没有区别。
- ¶8 `to_local(tp)` 返回 `tp` 在本时区的本地时间。从 UTC 到本地时间总是唯一的，不会抛异常。

`to_sys` 和 `to_local` 的返回类型都是 `common_type_t<Duration, seconds>`：时区偏移以秒计，所以即使输入是 `local_days`，结果也至少精确到秒。

¶7 对不存在的本地时间的处理值得注意。本地 2:30 落在 2:00 到 3:00 的空隙里，`choose::earliest` 和 `choose::latest` 都返回 07:00 UTC，也就是本地的 3:00 EDT，而不是把 2:30 往前或往后推 30 分钟。

[[time.zone.nonmembers#1]] 规定两个 `time_zone` 的 `==` 和 `<=>` 比较的是 `name()`。

## sys_info 与 local_info [time.zone.info]

这两个类型是底层接口，通常的换算会隐式使用它们（[[time.zone.info.sys#2]]）。

### sys_info [time.zone.info.sys]

```cpp
struct sys_info {
  sys_seconds begin;
  sys_seconds end;
  seconds     offset;
  minutes     save;
  string      abbrev;
};
```

¶1 `sys_info` 可以由一个 `time_zone` 加一个 `sys_time` 或 `local_time` 得到，也可以从 `zoned_time` 得到。

¶3 在 [`begin`, `end`) 这段时间内，`offset` 和 `abbrev` 有效。从 `end` 再查下一段，就能高效地遍历一个时区的所有切换点。

¶4 `offset` 是 UTC 偏移，满足 `offset = local_time - sys_time`。北京是 `+8h`，纽约冬季是 `-5h`。

¶5 `save` 不为 `0min` 时，表示正处于夏令时，`offset - save` 提示了不在夏令时的偏移。但这不可靠：唯一可靠的办法是找一个 `save == 0min` 的时刻去查，而这样的时刻保证不在当前的 [`begin`, `end`) 之内。

¶6 `abbrev` 是当前的缩写，如 `EST`。缩写不唯一，`CST` 可以是美国中部标准时间，也可以是中国标准时间，所以不能从缩写反推时区或偏移。

### local_info [time.zone.info.local]

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

¶2 `local_info` 描述把一个 `local_time` 转换成 `sys_time` 的结果：

| `result` | 含义 | `first` | `second` |
|---|---|---|---|
| `unique`（¶2.1） | 唯一对应一个 UTC 时刻 | 正确的 `sys_info` | 零初始化 |
| `nonexistent`（¶2.2） | 本地时间落在跳过的空隙里 | 在它之前结束的 `sys_info` | 在它之后开始的 `sys_info` |
| `ambiguous`（¶2.3） | 本地时间出现了两次 | 在它之后结束的 `sys_info` | 在它之前开始的 `sys_info` |

处理用户输入时，可以先用 `get_info(local_time)` 检查 `result`，再决定怎样处理。

## zoned_time [time.zone.zonedtime]

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

### 不变式

[[time.zone.zonedtime.overview#1]] 规定，`zoned_time` 是一个时区和一个时刻的逻辑配对。它维持一个不变式：总是指向一个有效的时区，表示的时刻在该时区中存在且无歧义。

`zoned_time` 内部存的是 `sys_time`，而不是 `local_time`，不变式正是靠这一点成立的：一个 UTC 时刻在任何时区都对应唯一的本地时间，反过来却不一定。所有从 `local_time` 构造的途径，都必须在构造时就解决歧义，要么抛异常，要么用 `choose`。

### 构造函数 [time.zone.zonedtime.ctor]

| 形式 | 效果 | 段落 |
|---|---|---|
| `zoned_time()`、`zoned_time(sys_time)` | 默认时区，加上纪元或给定时刻 | ¶1–¶4 |
| `zoned_time(z)`、`zoned_time(name)` | 给定时区，加上纪元；两者都是 `explicit` | ¶5–¶8 |
| `zoned_time(const zoned_time<D2, TimeZonePtr>&)` | 转换精度 | ¶9–¶10 |
| `zoned_time(z, sys_time)`、`(name, sys_time)` | 直接存储 | ¶11–¶14 |
| `zoned_time(z, local_time)`、`(name, local_time)` | `z->to_sys(tp)`，歧义或不存在时抛异常 | ¶15–¶19 |
| `zoned_time(z, local_time, choose)`、`(name, ..., choose)` | `z->to_sys(tp, c)` | ¶20–¶24 |
| `zoned_time(z, zoned_time)`、`(name, zoned_time)`，可带 `choose` | 同一时刻换一个时区 | ¶25–¶36 |

默认时区和按名字查找都由 `zoned_traits` 提供（见下文），没有对应的特化时，这些构造函数不参与重载决议。

¶31 和 ¶36 的注说明，从另一个 `zoned_time` 构造时，`choose` 形参没有作用：源对象存的是 UTC 时刻，换一个时区不会产生歧义。这两个重载存在，只是为了让泛型代码可以统一地传入 `choose`。

### 类模板实参推导

类定义之后给出了一组推导指引。它们借助一个仅用于说明的别名 *time-zone-representation*：实参能转换为 `string_view` 时，时区指针类型取 `const time_zone*`，否则取实参类型本身（去掉引用和 cv 限定）。精度一律取 `common_type_t<Duration, seconds>`。

```cpp
zoned_time zt1{"Asia/Shanghai", sys_days{2024y/January/1}};
    // zoned_time<seconds, const time_zone*>：days 与 seconds 的公共类型是 seconds
zoned_time zt2{current_zone(), system_clock::now()};
    // zoned_time<system_clock::duration, const time_zone*>
```

¶3 规定，以 `string_view` 为第一个形参的构造函数不参与类模板实参推导（[[over.match.class.deduct]]）。这样，以时区名开头的推导都只经过上面的推导指引，时区指针类型统一是 `const time_zone*`，精度统一是 `common_type_t<Duration, seconds>`，不会由构造函数隐式生成的推导指引推出别的结果，比如从 `sys_time<days>` 推出 `zoned_time<days>`。

### 成员与比较 [time.zone.zonedtime.members]

- ¶1 赋值一个 `sys_time` 后，`get_sys_time()` 等于它；¶3 赋值一个 `local_time` 后，`get_local_time()` 等于它。两者都不改变时区。赋值 `local_time` 没有 `choose` 参数，遇到歧义或不存在的本地时间时，经由 `to_sys` 抛异常。
- ¶5 可以隐式转换为 `sys_time<duration>`；¶6 转换为 `local_time<duration>` 是 `explicit` 的。这和历法类型一样：和 sys 隐式互转，和 local 显式转换。
- ¶7–¶10 `get_time_zone()`、`get_local_time()`、`get_sys_time()`、`get_info()`。`get_local_time()` 是 `zone_->to_local(tp_)`，每次调用都要查一次时区规则，在循环里反复使用时可以把结果存下来。

[[time.zone.zonedtime.nonmembers#1]] 规定 `==` 比较 `zone_` 和 `tp_`。比较的是指针：同一个数据库中同名的时区是同一个对象，但来自两个版本的 `tzdb` 的同名时区，指针不相等。第 2 段规定 `os << zt` 用 `"{:L%F %T %Z}"` 格式化，输出本地时间加上缩写。

## zoned_traits [time.zone.zonedtraits]

```cpp
template<class T> struct zoned_traits {};

template<> struct zoned_traits<const time_zone*> {
  static const time_zone* default_zone();                 // locate_zone("UTC")
  static const time_zone* locate_zone(string_view name);  // std::chrono::locate_zone(name)
};
```

¶1 `zoned_traits` 用来定制 `zoned_time<Duration, TimeZonePtr>` 的默认构造函数和接受 `string_view` 的构造函数。¶2 标准为 `const time_zone*` 提供的特化中，默认时区是 UTC，不是本机时区；¶3 按名字查找转发给 `locate_zone`。

`TimeZonePtr` 可以是任何像指向时区的指针一样的类型，只要用 `->` 能调用 `to_sys`、`to_local`、`get_info`。用户可以提供自己的时区类型，比如一个固定偏移的时区，或者从别的数据源加载的时区，并按需特化 `zoned_traits`，启用默认构造和按名字构造。

## 闰秒表与时区别名

### leap_second [time.zone.leap]

[[time.zone.leap.overview#1]] 规定，表示闰秒插入日期和值的 `leap_second` 对象在数据库初始化时构造，存放在 `tzdb::leap_seconds` 中。第 2 段的例子列出了 1972-07-01 到 2017-01-01 的 27 个闰秒：

```cpp
for (auto& l : get_tzdb().leap_seconds)
  if (l <= sys_days{2018y/March/17d})
    cout << l.date() << ": " << l.value() << '\n';
```

[[time.zone.leap.members#1]] 的 `date()` 返回插入闰秒的时刻；第 2 段的 `value()` 返回 `+1s` 表示正闰秒，`-1s` 表示负闰秒。注 1 指出，截至 2022 年插入的都是正闰秒。负闰秒在规则上可能发生，但从未发生过，接口为它留了位置。

nonmembers 子条款规定，两个 `leap_second` 按 `date()` 比较，`leap_second` 和任意精度的 `sys_time` 之间也可以直接比较，所以上面可以写 `l <= sys_days{...}`。`utc_clock` 的 `from_sys` 和 `to_sys` 就是查这张表实现的（[[time.clock]]）。

### time_zone_link [time.zone.link]

[[time.zone.link.overview#1]] 规定，`time_zone_link` 为某个 `time_zone` 提供一个别名，在数据库初始化时构造，只能移动。`name()` 是别名，`target()` 是被指向的时区名；两个 `time_zone_link` 按 `name()` 比较。

例如 `"US/Eastern"` 是 `"America/New_York"` 的别名，具体以数据库的版本为准。`locate_zone` 会透明地解析别名（[[time.zone.db.tzdb#2]]），所以 `locate_zone("US/Eastern")->name()` 返回 `"America/New_York"`。

<details class="fine" markdown="1"><summary>其余条文</summary>

[time.zone.db.list]：`tzdb_list` 不可复制，其他构造方式未指定（第 1 段）；`const_iterator` 是常量迭代器，满足 *Cpp17ForwardIterator*，值类型是 `tzdb`（第 2 段）；`front()` 和 `reload_tzdb()` 之间是线程安全的（第 3 段）；`erase_after` 的前置条件是 `p` 之后的迭代器可解引用，不抛异常（第 5、9 段）；`begin`、`end`、`cbegin`、`cend` 的含义与容器相同（第 10–13 段）。

[time.zone.db.remote]：`reload_tzdb()` 与 `get_tzdb_list().front()`、`erase_after()` 之间线程安全（第 3 段），返回 `front()`（第 5 段），失败时抛 `runtime_error`（第 6 段）。

[time.zone.exception]：两个异常类的构造函数分别要求 `local_info` 的 `result` 是 `nonexistent` 或 `ambiguous`。

[time.zone.info]：`sys_info` 和 `local_info` 的 `operator<<` 以未指定的格式输出。

[time.zone.zonedtime.overview] 第 2 段：`Duration` 不是 duration 的特化时，程序非良构。

[time.zone.leap.overview]：`leap_second` 可以复制，其他构造方式未指定。

</details>

## 常见陷阱

!!! pitfall "把本地时间写成 sys_time"
    `sys_days{2024y/March/15} + 9h` 是 UTC 的 9 点，不是纽约的 9 点。用户输入的日期和时间几乎总是本地时间，应当写 `local_days{...} + 9h`，再经由时区换算。类型系统能阻止把 `local_time` 传给需要 `sys_time` 的地方，但不能阻止你一开始就选错类型。

!!! pitfall "默认时区是 UTC"
    `zoned_time zt{system_clock::now()};` 的时区是 UTC，因为 `zoned_traits<const time_zone*>::default_zone()` 返回 `locate_zone("UTC")`。要用本机时区，写 `zoned_time{current_zone(), system_clock::now()}`。

!!! pitfall "从 local_time 构造会抛异常"
    本地时间落在夏令时的空隙或重叠里时，`zoned_time{"America/New_York", lt}` 会抛异常。处理用户输入时，先用 `get_info(local_time)` 检查 `result`，或者直接传 `choose::earliest`、`choose::latest`。对于每天 2:30 执行的定时任务，选哪一个就是一个业务决策。

!!! pitfall "时区缩写不是标识符"
    `sys_info::abbrev` 和格式化中的 `%Z` 只供人阅读。`CST`、`IST`、`BST` 都对应多个时区，存储和传输时要用 IANA 名（如 `"Asia/Shanghai"`）或 UTC 偏移。

## 思考题

!!! question "思考题 1"
    为什么 `zoned_time` 内部存 `sys_time`，而不是 `local_time`？

<details markdown="1">
<summary>答案</summary>

[[time.zone.zonedtime.overview#1]] 的不变式要求时刻在该时区中存在且无歧义。从 `sys_time` 到 `local_time` 是一个函数，每个 UTC 时刻在任何时区都有唯一的本地时间；反过来不是。存 `sys_time` 时不变式自动成立，`get_local_time()` 总能算出结果。如果存 `local_time`，换时区、比较、格式化 `%z` 时都要重新面对歧义。此外，存 UTC 让 `==` 直接比较物理时刻。
</details>

!!! question "思考题 2"
    `to_sys(lt, choose::earliest)` 和 `to_sys(lt, choose::latest)` 什么时候结果相同？

<details markdown="1">
<summary>答案</summary>

`lt` 唯一时显然相同。`lt` 落在空隙里时也相同：[[time.zone.members#7]] 规定这时两个候选的 UTC 时刻是同一个切换点，返回它。只有有歧义时，两者才相差两个偏移之差，通常是 1 小时。
</details>

!!! question "思考题 3"
    程序缓存了 `const time_zone* ny = locate_zone("America/New_York");`，之后调用了 `reload_tzdb()`。`ny` 还有效吗？它用的是新规则吗？

<details markdown="1">
<summary>答案</summary>

仍然有效：[[time.zone.db.remote#4]] 规定 `reload_tzdb` 不使任何指针失效。但 `ny` 指向旧的 `tzdb` 中的对象，用的是旧规则。要用新规则，需要重新调用 `locate_zone`，它查的是 `front()`，即新版本。只有调用 `erase_after` 删掉了旧的 `tzdb` 之后，`ny` 才会悬空。
</details>
