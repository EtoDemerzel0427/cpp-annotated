---
title: Time zones
summary: "How C++ uses the IANA time zone database: loading tzdb and tzdb_list and updating them at run time, how time_zone converts between sys_time and local_time, the nonexistent and ambiguous local times caused by daylight saving transitions, the invariant of zoned_time, and the leap second table and time zone links."
updated: 2026-10-19
---

!!! tldr
    - Time zone rules are set by governments and can change at any time, so they can only be looked up in the IANA database at run time. The database is loaded on first use, which may throw.
    - `time_zone::to_local` always has a unique result; `to_sys` throws `nonexistent_local_time` for a local time skipped when daylight saving time begins, and `ambiguous_local_time` for a local time repeated when it ends. Passing `choose::earliest` or `choose::latest` avoids both.
    - `zoned_time` bundles a time zone with a `sys_time`, guaranteeing that the time point it represents exists and is unambiguous in that time zone; the default time zone is UTC, not the computer's local time zone.
    - Reloading the database does not invalidate a `const time_zone*` you already hold, but the old pointer keeps using the old rules.
    - The libc++ build in our tests has the time zone database disabled, so none of the examples on this page compile with it.

## An example

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

A meeting at 9 a.m. on March 15, New York time, converted to Shanghai and London time. `local_days{...} + 9h` is a local time whose time zone is not yet determined; it is tied to New York's rules only when it is handed to `zoned_time`. In 2024, US daylight saving time began on March 10, so New York is at UTC−4 (EDT) here, while the UK does not switch until March 31, so London is still on GMT.

!!! impl "The state of libc++"
    None of the examples on this page compile in our tests. The Homebrew build of libc++ we use defines `_LIBCPP_HAS_TIME_ZONE_DATABASE` as 0, so names such as `tzdb`, `time_zone`, `zoned_time` and `leap_second` do not exist. Even in libc++ builds with the time zone database enabled, this part is an experimental feature that needs `-fexperimental-library`. The examples are written to the standard, and the output in the comments is taken from the standard's examples or derived from the IANA data; they can be run on Compiler Explorer with a recent GCC or MSVC.

¶1 [time.zone.general] explains that this subclause describes an interface for accessing the IANA time zone database, which interoperates with `sys_time` and `local_time` to provide time zone support for the calendar types and for user-defined calendars.

Converting between dates and UTC is pure arithmetic ([[time.cal]]); time zones are not. Which regions use daylight saving time, on which day they switch, and what the standard offset is are all decided by governments and can change at any time; the IANA database publishes several new releases every year. So time zone information can only be looked up in the database at run time.

## The time zone database [time.zone.db]

### tzdb [time.zone.db.tzdb]

```cpp
struct tzdb {
  string                 version;        // e.g. "2024a"
  vector<time_zone>      zones;
  vector<time_zone_link> links;
  vector<leap_second>    leap_seconds;
  const time_zone* locate_zone(string_view tz_name) const;
  const time_zone* current_zone() const;
};
```

¶1 Each vector is sorted to enable fast lookup.

¶2 `locate_zone(name)` first looks in `zones` for a time zone whose name equals `name`; failing that, it looks in `links` for a link with that name and returns the time zone that its `target()` refers to. ¶3 If neither is found, it throws `runtime_error`. Note 2 points out that on normal return the result always points to a valid `time_zone`, never a null pointer.

¶4 `current_zone()` returns the local time zone the computer is set to.

### Access functions [time.zone.db.access]

| Function | Effect | Paragraphs |
|---|---|---|
| `get_tzdb_list()` | Initializes the database on the first call; concurrent calls from multiple threads are safe; throws `runtime_error` if a valid database cannot be obtained | ¶1–¶4 |
| `get_tzdb()` | `get_tzdb_list().front()` | ¶5 |
| `locate_zone(name)` | `get_tzdb().locate_zone(name)` | ¶6–¶7 |
| `current_zone()` | `get_tzdb().current_zone()` | ¶8 |

The database is lazily initialized, so programs that do not use time zones do not pay the cost of loading it. The first call may be slow, because it reads and parses the system's zoneinfo files, and it may throw. This is the root reason `utc_clock::now()` cannot be `noexcept` ([[time.clock]]): it uses the leap second table in the database.

### tzdb_list and run-time updates [time.zone.db.list] [time.zone.db.remote]

[[time.zone.db.list#1]] specifies that `tzdb_list` is a singleton whose only object is accessed through `get_tzdb_list()` and holds a list of `tzdb`. Note 1 explains that only long-running programs that need to update the time zone database while running need to use it directly; other programs use the first element of the list implicitly through `get_tzdb()`, `locate_zone()` and `current_zone()`.

Its interface is that of a singly linked list: `front()`, `erase_after()` and forward iterators. A linked list was chosen for this guarantee: a new version is pushed to the front, old versions stay behind it, and every `const time_zone*` already obtained remains valid. `erase_after(p)` erases the `tzdb` after `p`, and paragraph 7 guarantees that it invalidates no pointers, references or iterators other than those to the erased one. Note 3 points out that the first element can never be erased.

[[time.zone.db.remote#1]] distinguishes two databases. The **local time zone database** is the one the implementation supplies when the program first accesses it. The implementation may update the database while the program is running, but the update must not affect the program in any way unless the program calls the functions of this subclause. The possibly updated database is called the **remote time zone database** ([[g:remote-time-zone-database]]).

¶2 `reload_tzdb()` compares the versions of the remote and local databases: if they are the same it does nothing; if they differ, it pushes the remote database to the front of `tzdb_list`. ¶4 It invalidates no pointers, references or iterators. ¶7 `remote_version()` returns the latest version of the remote database, which can be compared with `get_tzdb().version` to decide whether reloading is needed.

So even if the operating system updates the zoneinfo files while the program is running, two calls to `locate_zone("America/New_York")->to_local(t)` in the same program must give the same result, unless the program itself calls `reload_tzdb()`.

## Two problems caused by daylight saving time

When daylight saving time begins, the clock jumps straight from 2:00 to 3:00, and the local time 2:30 does not exist. When it ends, the clock falls back from 2:00 to 1:00, and 1:30 occurs twice. Converting such a local time to UTC has no unique answer.

### Nonexistent local times [time.zone.exception.nonexist]

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

In 2016, daylight saving time in New York began at 2:00 on the second Sunday of March. `Sunday[2]/March` is a `month_weekday`, `/2016` supplies the year to give a `year_month_weekday`, which is then explicitly converted to `local_days` ([[time.cal]]). The example in ¶4 gives the output:

```text
2016-03-13 02:30:00 is in a gap between
2016-03-13 02:00:00 EST and
2016-03-13 03:00:00 EDT which are both equivalent to
2016-03-13 07:00:00 UTC
```

¶1 `nonexistent_local_time` is thrown when converting a nonexistent `local_time` to a `sys_time` without specifying `choose::earliest` or `choose::latest`. It derives from `runtime_error`, and ¶3 specifies the content of `what()` exactly with a piece of code.

### Ambiguous local times [time.zone.exception.ambig]

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

In 2016, daylight saving time in New York ended at 2:00 on the first Sunday of November. The example in ¶4 gives the output:

```text
2016-11-06 01:30:00 is ambiguous.  It could be
2016-11-06 01:30:00 EDT == 2016-11-06 05:30:00 UTC or
2016-11-06 01:30:00 EST == 2016-11-06 06:30:00 UTC
```

¶1 `ambiguous_local_time` is thrown when converting an ambiguous `local_time` to a `sys_time` without specifying `choose`.

## time_zone [time.zone.timezone]

```cpp
enum class choose {earliest, latest};

class time_zone {
public:
  time_zone(time_zone&&) = default;
  time_zone& operator=(time_zone&&) = default;
  // other constructors unspecified
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

[[time.zone.overview#1]] specifies that a `time_zone` represents all time zone transitions for a specific geographic area. How it is constructed is unspecified; construction happens when the database is initialized. Users cannot create a `time_zone` themselves; they can only obtain a `const time_zone` from the database through functions such as `locate_zone`.

Some members in [[time.zone.members]]:

- ¶1 `name()` returns the time zone name, such as `"America/New_York"`.
- ¶3 `get_info(sys_time st)` returns a `sys_info` whose range contains `st`; ¶4 `get_info(local_time)` returns a `local_info` (see below).
- ¶5 `to_sys(tp)` returns the UTC time point corresponding to `tp` under this time zone's rules. ¶6 It throws `ambiguous_local_time` if the local time is ambiguous, and `nonexistent_local_time` if it does not exist.
- ¶7 For an ambiguous local time, `to_sys(tp, z)` returns the earlier UTC time point for `choose::earliest` and the later one for `choose::latest`. For a nonexistent local time, the two candidate UTC time points are the same, the moment of the transition, so that is returned and `choose` makes no difference.
- ¶8 `to_local(tp)` returns the local time of `tp` in this time zone. The conversion from UTC to local time is always unique and does not throw.

The return types of both `to_sys` and `to_local` use `common_type_t<Duration, seconds>`: time zone offsets are in seconds, so even if the input is `local_days`, the result has at least seconds precision.

The handling of nonexistent local times in ¶7 deserves attention. Local 2:30 falls in the gap from 2:00 to 3:00; `choose::earliest` and `choose::latest` both return 07:00 UTC, that is, local 3:00 EDT, rather than pushing 2:30 forward or back by 30 minutes.

[[time.zone.nonmembers#1]] specifies that `==` and `<=>` on two `time_zone`s compare `name()`.

## sys_info and local_info [time.zone.info]

These two types are low-level interfaces; the usual conversions use them implicitly ([[time.zone.info.sys#2]]).

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

¶1 A `sys_info` can be obtained from a `time_zone` plus a `sys_time` or a `local_time`, or from a `zoned_time`.

¶3 `offset` and `abbrev` are in effect within [`begin`, `end`). Querying the next range from `end` lets you iterate efficiently over all the transitions of a time zone.

¶4 `offset` is the UTC offset, satisfying `offset = local_time - sys_time`. Beijing is `+8h`, New York in winter is `-5h`.

¶5 A `save` other than `0min` indicates that daylight saving time is in effect, and `offset - save` hints at the offset when not in daylight saving time. But this is not reliable: the only reliable way is to look up a time point where `save == 0min`, and such a time point is guaranteed not to be within the current [`begin`, `end`).

¶6 `abbrev` is the current abbreviation, such as `EST`. Abbreviations are not unique: `CST` can be US Central Standard Time or China Standard Time, so you cannot infer a time zone or offset from an abbreviation.

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

¶2 `local_info` describes the result of converting a `local_time` to a `sys_time`:

| `result` | Meaning | `first` | `second` |
|---|---|---|---|
| `unique` (¶2.1) | Maps to exactly one UTC time point | The correct `sys_info` | Zero-initialized |
| `nonexistent` (¶2.2) | The local time falls in a skipped gap | The `sys_info` that ends just before it | The `sys_info` that begins just after it |
| `ambiguous` (¶2.3) | The local time occurs twice | The `sys_info` that ends just after it | The `sys_info` that begins just before it |

When handling user input, you can first check `result` with `get_info(local_time)`, then decide what to do.

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

### The invariant

[[time.zone.zonedtime.overview#1]] specifies that `zoned_time` is a logical pairing of a time zone and a time point. It maintains an invariant: it always refers to a valid time zone and represents a time point that exists and is not ambiguous in that time zone.

`zoned_time` stores a `sys_time` internally, not a `local_time`, and this is exactly what makes the invariant hold: a UTC time point corresponds to a unique local time in any time zone, but not the other way round. Every way of constructing from a `local_time` must resolve the ambiguity at construction, either by throwing or by using `choose`.

### Constructors [time.zone.zonedtime.ctor]

| Form | Effect | Paragraphs |
|---|---|---|
| `zoned_time()`, `zoned_time(sys_time)` | Default time zone, plus the epoch or the given time point | ¶1–¶4 |
| `zoned_time(z)`, `zoned_time(name)` | Given time zone, plus the epoch; both are `explicit` | ¶5–¶8 |
| `zoned_time(const zoned_time<D2, TimeZonePtr>&)` | Converts precision | ¶9–¶10 |
| `zoned_time(z, sys_time)`, `(name, sys_time)` | Stores directly | ¶11–¶14 |
| `zoned_time(z, local_time)`, `(name, local_time)` | `z->to_sys(tp)`; throws if ambiguous or nonexistent | ¶15–¶19 |
| `zoned_time(z, local_time, choose)`, `(name, ..., choose)` | `z->to_sys(tp, c)` | ¶20–¶24 |
| `zoned_time(z, zoned_time)`, `(name, zoned_time)`, optionally with `choose` | Same time point in another time zone | ¶25–¶36 |

The default time zone and lookup by name are both provided by `zoned_traits` (see below); if there is no corresponding specialization, these constructors do not participate in overload resolution.

The notes in ¶31 and ¶36 explain that when constructing from another `zoned_time`, the `choose` parameter has no effect: the source object stores a UTC time point, and changing the time zone cannot create ambiguity. These two overloads exist only so that generic code can pass `choose` uniformly.

### Class template argument deduction

A set of deduction guides follows the class definition. They use an exposition-only alias *time-zone-representation*: if the argument is convertible to `string_view`, the time zone pointer type is `const time_zone*`; otherwise it is the argument type itself (with references and cv-qualifiers removed). The precision is always `common_type_t<Duration, seconds>`.

```cpp
zoned_time zt1{"Asia/Shanghai", sys_days{2024y/January/1}};
    // zoned_time<seconds, const time_zone*>: the common type of days and seconds is seconds
zoned_time zt2{current_zone(), system_clock::now()};
    // zoned_time<system_clock::duration, const time_zone*>
```

¶3 specifies that the constructors whose first parameter is `string_view` do not participate in class template argument deduction ([[over.match.class.deduct]]). This way, every deduction starting with a time zone name goes only through the deduction guides above: the time zone pointer type is uniformly `const time_zone*` and the precision is uniformly `common_type_t<Duration, seconds>`, and the guides implicitly generated from the constructors cannot deduce something else, such as `zoned_time<days>` from a `sys_time<days>`.

### Members and comparison [time.zone.zonedtime.members]

- ¶1 After assigning a `sys_time`, `get_sys_time()` equals it; ¶3 after assigning a `local_time`, `get_local_time()` equals it. Neither changes the time zone. Assigning a `local_time` takes no `choose` argument; for an ambiguous or nonexistent local time it throws via `to_sys`.
- ¶5 It implicitly converts to `sys_time<duration>`; ¶6 the conversion to `local_time<duration>` is `explicit`. This is the same as for the calendar types: implicit conversion to and from sys, explicit conversion to local.
- ¶7–¶10 `get_time_zone()`, `get_local_time()`, `get_sys_time()`, `get_info()`. `get_local_time()` is `zone_->to_local(tp_)`, which looks up the time zone rules on every call; when it is used repeatedly in a loop, you can store the result.

[[time.zone.zonedtime.nonmembers#1]] specifies that `==` compares `zone_` and `tp_`. It compares pointers: time zones with the same name in the same database are the same object, but same-named time zones from two versions of `tzdb` have unequal pointers. Paragraph 2 specifies that `os << zt` formats with `"{:L%F %T %Z}"`, printing the local time plus the abbreviation.

## zoned_traits [time.zone.zonedtraits]

```cpp
template<class T> struct zoned_traits {};

template<> struct zoned_traits<const time_zone*> {
  static const time_zone* default_zone();                 // locate_zone("UTC")
  static const time_zone* locate_zone(string_view name);  // std::chrono::locate_zone(name)
};
```

¶1 `zoned_traits` is used to customize the default constructor of `zoned_time<Duration, TimeZonePtr>` and the constructors taking a `string_view`. ¶2 In the specialization the standard provides for `const time_zone*`, the default time zone is UTC, not the computer's local time zone; ¶3 lookup by name forwards to `locate_zone`.

`TimeZonePtr` can be any type that behaves like a pointer to a time zone, as long as `to_sys`, `to_local` and `get_info` can be called through `->`. Users can supply their own time zone type, such as a fixed-offset time zone or one loaded from another data source, and specialize `zoned_traits` as needed to enable default construction and construction by name.

## The leap second table and time zone links

### leap_second [time.zone.leap]

[[time.zone.leap.overview#1]] specifies that `leap_second` objects, representing the date and value of leap second insertions, are constructed when the database is initialized and stored in `tzdb::leap_seconds`. The example in paragraph 2 lists the 27 leap seconds from 1972-07-01 to 2017-01-01:

```cpp
for (auto& l : get_tzdb().leap_seconds)
  if (l <= sys_days{2018y/March/17d})
    cout << l.date() << ": " << l.value() << '\n';
```

`date()` in [[time.zone.leap.members#1]] returns the time point at which the leap second is inserted; `value()` in paragraph 2 returns `+1s` for a positive leap second and `-1s` for a negative one. Note 1 points out that as of 2022 all inserted leap seconds have been positive. A negative leap second is possible under the rules but has never happened; the interface leaves room for it.

The nonmembers subclause specifies that two `leap_second`s compare by `date()`, and that a `leap_second` can also be compared directly with a `sys_time` of any precision, which is why the code above can write `l <= sys_days{...}`. `from_sys` and `to_sys` of `utc_clock` are implemented by looking up this table ([[time.clock]]).

### time_zone_link [time.zone.link]

[[time.zone.link.overview#1]] specifies that a `time_zone_link` provides an alternative name for a `time_zone`; it is constructed when the database is initialized and is move-only. `name()` is the alternative name and `target()` is the name of the time zone it refers to; two `time_zone_link`s compare by `name()`.

For example, `"US/Eastern"` is a link to `"America/New_York"`, depending on the version of the database. `locate_zone` resolves links transparently ([[time.zone.db.tzdb#2]]), so `locate_zone("US/Eastern")->name()` returns `"America/New_York"`.

<details class="fine" markdown="1"><summary>Remaining wording</summary>

[time.zone.db.list]: `tzdb_list` is not copyable, and other means of construction are unspecified (paragraph 1); `const_iterator` is a constant iterator meeting *Cpp17ForwardIterator* with value type `tzdb` (paragraph 2); `front()` is thread-safe with respect to `reload_tzdb()` (paragraph 3); `erase_after` has the precondition that the iterator after `p` is dereferenceable, and throws nothing (paragraphs 5 and 9); `begin`, `end`, `cbegin` and `cend` mean the same as for containers (paragraphs 10–13).

[time.zone.db.remote]: `reload_tzdb()` is thread-safe with respect to `get_tzdb_list().front()` and `erase_after()` (paragraph 3), returns `front()` (paragraph 5), and throws `runtime_error` on failure (paragraph 6).

[time.zone.exception]: the constructors of the two exception classes require the `result` of the `local_info` to be `nonexistent` or `ambiguous`, respectively.

[time.zone.info]: `operator<<` for `sys_info` and `local_info` prints in an unspecified format.

[time.zone.zonedtime.overview] paragraph 2: if `Duration` is not a specialization of duration, the program is ill-formed.

[time.zone.leap.overview]: `leap_second` is copyable, and other means of construction are unspecified.

</details>

## Common pitfalls

!!! pitfall "Writing a local time as sys_time"
    `sys_days{2024y/March/15} + 9h` is 9:00 UTC, not 9:00 in New York. Dates and times entered by users are almost always local times; write `local_days{...} + 9h` and convert through a time zone. The type system can stop you from passing a `local_time` where a `sys_time` is needed, but not from choosing the wrong type in the first place.

!!! pitfall "The default time zone is UTC"
    The time zone of `zoned_time zt{system_clock::now()};` is UTC, because `zoned_traits<const time_zone*>::default_zone()` returns `locate_zone("UTC")`. To use the computer's local time zone, write `zoned_time{current_zone(), system_clock::now()}`.

!!! pitfall "Construction from local_time can throw"
    When the local time falls in a daylight saving gap or overlap, `zoned_time{"America/New_York", lt}` throws. When handling user input, first check `result` with `get_info(local_time)`, or pass `choose::earliest` or `choose::latest` directly. For a scheduled job that runs at 2:30 every day, which one to pick is a business decision.

!!! pitfall "Time zone abbreviations are not identifiers"
    `sys_info::abbrev` and `%Z` in formatting are for human readers only. `CST`, `IST` and `BST` each correspond to several time zones; for storage and transmission, use IANA names (such as `"Asia/Shanghai"`) or UTC offsets.

## Questions

!!! question "Question 1"
    Why does `zoned_time` store a `sys_time` internally rather than a `local_time`?

<details markdown="1">
<summary>Answer</summary>

The invariant of [[time.zone.zonedtime.overview#1]] requires the time point to exist and be unambiguous in the time zone. The mapping from `sys_time` to `local_time` is a function: every UTC time point has a unique local time in any time zone; the reverse is not true. Storing a `sys_time` makes the invariant hold automatically, and `get_local_time()` can always compute a result. If a `local_time` were stored, changing time zones, comparing, and formatting `%z` would all have to face the ambiguity again. In addition, storing UTC lets `==` compare physical time points directly.
</details>

!!! question "Question 2"
    When do `to_sys(lt, choose::earliest)` and `to_sys(lt, choose::latest)` give the same result?

<details markdown="1">
<summary>Answer</summary>

Obviously when `lt` is unique. Also when `lt` falls in a gap: [[time.zone.members#7]] specifies that the two candidate UTC time points are then the same transition point, which is returned. Only when the local time is ambiguous do the two differ, by the difference between the two offsets, usually 1 hour.
</details>

!!! question "Question 3"
    A program caches `const time_zone* ny = locate_zone("America/New_York");` and later calls `reload_tzdb()`. Is `ny` still valid? Does it use the new rules?

<details markdown="1">
<summary>Answer</summary>

It is still valid: [[time.zone.db.remote#4]] specifies that `reload_tzdb` invalidates no pointers. But `ny` points to an object in the old `tzdb` and uses the old rules. To use the new rules, call `locate_zone` again; it looks in `front()`, the new version. Only after `erase_after` has erased the old `tzdb` does `ny` dangle.
</details>
