---
title: 时间相关特征
summary: duration 通过四个特征了解它的表示类型：treat_as_floating_point 决定 duration 之间能否隐式转换，duration_values 给出零值和极值，common_type 特化取两个周期的最大公约数，is_clock 判定一个类型是不是时钟；程序为 is_clock 添加特化是 UB。
status: done
covers: *
related: time.duration, time.clock.req, ratio, meta.trans.other, namespace.std
tags: 标准库, chrono, 类型特征
updated: 2026-10-19
---

!!! tldr
    - 整数表示的 duration 只有在不需要除法时才能隐式转换：`seconds` 能变成 `milliseconds`，反过来不行。`treat_as_floating_point` 为真的表示类型不受这个限制。
    - `duration::zero()`、`min()`、`max()` 来自 `duration_values`，其中 `min()` 是 `numeric_limits<Rep>::lowest()`，不是 `numeric_limits<Rep>::min()`。
    - 两个 duration 的公共类型取两个周期的最大公约数，两边都只靠乘法就能转换过去，所以 `1s + 1ms` 的类型是 `milliseconds`。乘法仍可能溢出。
    - `is_clock` 只做语法层面的检查；程序为它添加特化，行为未定义。

## treat_as_floating_point（[time.traits.is.fp]）

```cpp run title="treat-as-fp.cpp" ok
#include <chrono>
#include <type_traits>
using namespace std::chrono;
using std::is_convertible_v;

struct fixed16 { /* 某个定点数类型，实现从略 */ };
template<>
struct std::chrono::treat_as_floating_point<fixed16>
    : std::true_type {};

// 浮点表示：允许
static_assert(is_convertible_v<milliseconds, duration<double>>);
// 整数表示且需要除法：拒绝
static_assert(!is_convertible_v<milliseconds, seconds>);
// 整数表示但只需乘法：允许
static_assert(is_convertible_v<seconds, milliseconds>);
static_assert(treat_as_floating_point_v<fixed16>);

int main() {}
```

```cpp
template<class Rep> struct treat_as_floating_point : is_floating_point<Rep> { };
```

¶1 `duration` 用这个特征判断能否把一个 duration 转换为计次周期不同的另一个 duration。如果 `treat_as_floating_point_v<Rep>` 为真，duration 之间总可以隐式转换；否则能否隐式转换取决于两者的周期（见 [[time.duration]] 的构造函数）。

注 1 说明了用意：这个特征表示一个类型的行为像浮点数，做除法时损失一点精度是可以接受的。为 `false` 时，`Rep` 被当作整数，除法会截断。

`milliseconds` 转 `seconds` 对 1000ms 是精确的，对 1500ms 会丢掉 500ms。编译器在编译期不知道值，所以对整数表示一律拒绝需要除法的隐式转换，要求你写 `duration_cast`、`floor` 或 `round`，表明你知道会截断。

上例中 `fixed16` 的特化是允许的：按 [[namespace.std]]，程序可以特化标准库类模板，只要特化依赖于程序定义的类型。下文的 `is_clock` 正好相反。

## duration_values（[time.traits.duration.values]）

```cpp
template<class Rep>
struct duration_values {
  static constexpr Rep zero() noexcept;   // Rep(0)
  static constexpr Rep min() noexcept;    // numeric_limits<Rep>::lowest()
  static constexpr Rep max() noexcept;    // numeric_limits<Rep>::max()
};
```

¶1 `duration` 用这个特征构造表示类型的特殊值，`duration::zero()`、`min()`、`max()`（[[time.duration]]）都转发到这里。单独做成特征，是因为 `Rep` 可以是类类型，构造这些值可能需要别的办法，这时由类型的作者特化 `duration_values`。

- ¶2–¶3 `zero()` 返回 `Rep(0)`，返回值必须是加法单位元。注 1 解释为什么不用 `Rep()`：对某些类型，`Rep()` 可能有别的含义，比如一个未初始化的值。
- ¶4–¶5 `min()` 返回 `numeric_limits<Rep>::lowest()`，必须小于等于 `zero()`。对浮点类型，`numeric_limits<Rep>::min()` 是最小的正规格化数，是个正数，所以这里用的是 `lowest()`。
- ¶6–¶7 `max()` 返回 `numeric_limits<Rep>::max()`，必须大于 `zero()`。

## common_type 的特化（[time.traits.specializations]）

```cpp run title="common-period.cpp" ok
#include <chrono>
#include <iostream>
using namespace std::chrono;

int main() {
  using third = duration<int, std::ratio<1, 3>>;
  using half  = duration<int, std::ratio<1, 2>>;
  using C = std::common_type_t<third, half>;
  static_assert(std::is_same_v<C::period, std::ratio<1, 6>>);
  std::cout << third{1} + half{1} << '\n';   // 5[1/6]s，即 5/6 秒
}
```

```cpp
template<class Rep1, class Period1, class Rep2, class Period2>
struct common_type<chrono::duration<Rep1, Period1>, chrono::duration<Rep2, Period2>> {
  using type = chrono::duration<common_type_t<Rep1, Rep2>, see below>;
};
```

¶1 结果的周期是 `Period1` 与 `Period2` 的最大公约数。注 1 给出算法：分子取两个分子的最大公约数，分母取两个分母的最小公倍数。

¶2 注 2 解释为什么取最大公约数：它是两个 duration 都能不经除法转换过去的最大周期。只用乘法意味着整数表示也不会截断。duration 的加减和比较都先转换到公共类型，所以 `1s + 1ms` 的类型是 `milliseconds`，`1s` 乘以 1000，没有信息丢失。

| `Period1` | `Period2` | 公共周期 |
|---|---|---|
| `ratio<1>`（秒） | `milli` | `milli` |
| `ratio<60>`（分） | `ratio<3600>`（时） | `ratio<60>` |
| `ratio<1, 3>` | `ratio<1, 2>` | `ratio<1, 6>` |
| `ratio<1, 30>`（30 Hz 的帧） | `milli` | `ratio<1, 3000>` |

注 2 还说，公共类型的表示类型意在能无截断地容纳转换结果，但这只是意图，乘法本身仍可能溢出。`nanoseconds` 与 `years` 的公共类型是 `nanoseconds`，把 300 年换算成纳秒就超出了 64 位整数的范围（见 [[time.duration]]）。

¶3 同一个时钟的两个 time_point 的公共类型，是这个时钟上、以两者 duration 的公共类型为 duration 的 time_point。标准没有为不同时钟的 time_point 提供特化，它们本来就不能混用。

## is_clock（[time.traits.is.clock]）

```cpp run title="is-clock.cpp" ok
#include <chrono>
using namespace std::chrono;

static_assert( is_clock_v<system_clock>);
static_assert( is_clock_v<steady_clock>);
static_assert( is_clock_v<file_clock>);
static_assert(!is_clock_v<local_t>);   // 伪时钟，没有 now()
static_assert(!is_clock_v<seconds>);

int main() {}
```

¶1 如果 `T` 满足 *Cpp17Clock* 要求（[[time.clock.req]]），`is_clock<T>` 派生自 `true_type`，否则派生自 `false_type`。实现在多大程度上判定一个类型不满足要求是未指定的，但至少要检查：

- ¶1.1 `T::rep`、`T::period`、`T::duration`、`T::time_point` 都有效，且都是类型；
- ¶1.2 `T::is_steady` 作为不求值操作数是良构的；
- ¶1.3 `T::now()` 作为不求值操作数是良构的。

这是一个语法检查。它不能验证 `now()` 是否真的单调，也不能验证 `is_steady` 是否如实声明。实现可以检查更多，但不能更少。

`local_t` 是一个伪时钟，用来构成 `local_time`，表示还没有确定时区的本地时间。它没有 `now()`，所以 `is_clock_v<local_t>` 为假。

¶2 程序为 `is_clock` 添加特化，行为未定义（{{ub}}）。这与 `<type_traits>` 中大多数类型特征的规则一致（[[meta.rqmts]]）：`is_clock` 的值应当如实反映类型是否满足要求，满足要求的类型本来就会得到 `true`，不需要特化；允许特化只会让一个不是时钟的类型冒充时钟。

!!! impl "libc++ 会诊断这种特化"
    libc++ 给 `is_clock` 和 `is_clock_v` 加了 Clang 的 `[[clang::no_specializations]]` 属性。本机对 `template<> struct std::chrono::is_clock<X> : std::true_type {};` 报错 `'is_clock' cannot be specialized`。标准只说是 UB，这是实现提供的额外保护。
