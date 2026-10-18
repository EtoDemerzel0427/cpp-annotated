---
title: 时间相关特征
summary: treat_as_floating_point 决定 duration 之间能否隐式转换；duration_values 给出零值与极值；common_type 特化算出"两个周期的最大公约数"；is_clock 判定时钟——以及为什么给 is_clock 加特化是 UB
status: done
covers: *
related: time.duration, time.clock.req, ratio, meta.trans.other, namespace.std
tags: 标准库, chrono, 类型特征
updated: 2026-10-18
---

本节的四个特征都是 `duration` 的"可定制点"：`duration` 本身对 `Rep` 一无所知，它要靠这些特征回答三个问题——这个表示类型能不能"无损地"做除法？它的零、最小值、最大值是什么？两个不同单位的时长相加，结果用什么单位？用户为自己的数值类型（定点数、区间算术、大整数）实例化 `duration` 时，就通过特化这些模板来回答。

## treat_as_floating_point（[time.traits.is.fp]）

```cpp
template<class Rep> struct treat_as_floating_point : is_floating_point<Rep> { };
```

¶1：`duration` 用它来判断"能否把一个 duration 转换成另一个计次周期不同的 duration"。若 `treat_as_floating_point_v<Rep>` 为真，duration 之间的隐式转换总是允许；否则是否允许取决于周期（见 [[time.duration]] 的构造函数规则）。

注 1 说明了用意：这个特征表示"这个类型像浮点数一样，做除法时损失一点精度是可以接受的"。为 `false` 时，`Rep` 被当作整数对待——除法会截断，所以 `duration` 拒绝一切需要除法的隐式转换。

这里的设计思想是：**能否隐式转换，不看值，而看类型能否承受截断**。`milliseconds` → `seconds` 对 1000ms 来说是精确的，对 1500ms 就会丢掉 500ms；编译器在编译期不知道值，所以对整数 rep 一律拒绝，强迫你写出 `duration_cast` 或 `floor`/`round` 表明你知道会截断。

```cpp title="treat-as-fp.cpp" ok
#include <chrono>
#include <type_traits>
using namespace std::chrono;

struct fixed16 { /* 某个定点数类型（演示用，省略实现） */ };
template<> struct std::chrono::treat_as_floating_point<fixed16> : std::true_type {};

static_assert( std::is_convertible_v<milliseconds, duration<double>>);   // 浮点：允许
static_assert(!std::is_convertible_v<milliseconds, seconds>);            // 整数且需要除法：拒绝
static_assert( std::is_convertible_v<seconds, milliseconds>);            // 整数但只需乘法：允许
static_assert( treat_as_floating_point_v<fixed16>);

int main() {}
```

`treat_as_floating_point` 是允许用户特化的（只要特化依赖于用户定义类型，[[namespace.std]]）；这与下文的 `is_clock` 正好相反。

## duration_values（[time.traits.duration.values]）

```cpp
template<class Rep>
struct duration_values {
  static constexpr Rep zero() noexcept;   // Rep(0)
  static constexpr Rep min() noexcept;    // numeric_limits<Rep>::lowest()
  static constexpr Rep max() noexcept;    // numeric_limits<Rep>::max()
};
```

¶1：`duration::zero()`、`min()`、`max()`（[[time.duration]]）都转发到这里。之所以单独做成特征，是因为 `Rep` 可以是类类型，它的"零"可能需要别的方式构造，这时由类型作者特化 `duration_values`。

- ¶2–¶3：`zero()` 返回 `Rep(0)` 而不是 `Rep()`。注 1 解释：`Rep()` 对某些类型可能有别的含义，比如"未初始化值"。返回值必须是加法单位元。
- ¶4–¶5：`min()` 返回 `numeric_limits<Rep>::lowest()`，且必须 `<= zero()`。注意是 `lowest()` 而不是 `numeric_limits::min()`——对浮点数，后者是最小正规格化数（一个正数）。
- ¶6–¶7：`max()` 返回 `numeric_limits<Rep>::max()`，且必须 `> zero()`。

## common_type 的特化（[time.traits.specializations]）

```cpp
template<class Rep1, class Period1, class Rep2, class Period2>
struct common_type<chrono::duration<Rep1, Period1>, chrono::duration<Rep2, Period2>> {
  using type = chrono::duration<common_type_t<Rep1, Rep2>, see below>;
};
```

¶1：结果的周期是 `Period1` 与 `Period2` 的**最大公约数**。注 1 给出算法：分子取两个分子的 gcd，分母取两个分母的 lcm。

¶2（注 2）解释为什么是 gcd：它是"两个参数都能**只靠乘法**转换过去"的最大周期。只靠乘法意味着整数 rep 下不截断——这正是 duration 加减、比较都先转到 common type 的原因：`1s + 1ms` 的类型是 `milliseconds`，`1s` 被乘以 1000，没有任何信息丢失。

两个"不整齐"的周期也能求出公共类型：

| `Period1` | `Period2` | 公共周期 |
|---|---|---|
| `ratio<1>`（秒） | `milli` | `milli` |
| `ratio<60>`（分） | `ratio<3600>`（时） | `ratio<60>` |
| `ratio<1, 3>` | `ratio<1, 2>` | `ratio<1, 6>` |
| `ratio<1, 30>`（30 Hz 帧） | `ratio<1, 1000>` | `ratio<1, 3000>` |

```cpp title="common-period.cpp" ok
#include <chrono>
#include <iostream>
using namespace std::chrono;

int main() {
    using third = duration<int, std::ratio<1, 3>>;
    using half  = duration<int, std::ratio<1, 2>>;
    static_assert(std::is_same_v<std::common_type_t<third, half>::period, std::ratio<1, 6>>);
    std::cout << third{1} + half{1} << '\n';     // 5[1/6]s：1/3 + 1/2 = 5/6 秒
}
```

注 2 末尾提醒：公共类型的 rep 意在能无截断地容纳转换结果，但这只是"意图"——乘法本身仍可能**溢出**。`nanoseconds` 与 `years` 的公共类型是 `nanoseconds`，把 300 年转换过去就超出了 64 位（见 [[time.duration]] 的陷阱）。

¶3：两个**同一时钟**的 time_point 的公共类型，是该时钟上以两个 duration 的公共类型为 duration 的 time_point。没有为不同时钟的 time_point 提供特化——它们本来就不能混用。

## is_clock（[time.traits.is.clock]）

```cpp
template<class T> struct is_clock;
template<class T> constexpr bool is_clock_v = is_clock<T>::value;
```

¶1：若 `T` 满足 *Cpp17Clock* 要求（[[time.clock.req]]），`is_clock<T>` 派生自 `true_type`，否则派生自 `false_type`。实现能多精确地判定是未指明的，但至少要检查：

- ¶1.1：`T::rep`、`T::period`、`T::duration`、`T::time_point` 都是有效的类型名；
- ¶1.2：`T::is_steady` 作为不求值操作数是良构的；
- ¶1.3：`T::now()` 作为不求值操作数是良构的。

也就是说，这是一个**语法检查**：`is_clock` 不能验证 `now()` 是否真的单调、`period` 是否真的是 `ratio`。实现可以检查得更多，但不能更少。libc++ 的实现就更严格：它还要求 `rep` 是算术类型或类类型、`period` 是 `ratio` 的特化、`duration` 恰好是 `duration<rep, period>`、`is_steady` 的类型是 `const bool`、`now()` 返回 `time_point`。`local_t` 没有 `now()`，所以 `is_clock_v<local_t>` 为假。

¶2：程序为 `is_clock` 添加特化，行为未定义（{{ub}}）。为什么禁止？因为标准库内部用 `is_clock` 做约束（例如格式化、`clock_cast` 的实现），如果用户能把一个不是时钟的类型"声明"成时钟，库的内部假设就会崩溃；反过来，满足要求的类型本来就会自动得到 `true`，没有特化的必要。

!!! impl "libc++ 会诊断这种特化"
    libc++ 给 `is_clock` 与 `is_clock_v` 加了内部宏 `_LIBCPP_NO_SPECIALIZATIONS`，它展开为 Clang 的 `[[clang::no_specializations]]` 属性，于是用户写出特化时编译器会报错。标准只说是 UB，这是实现提供的额外保护。

```cpp title="is-clock.cpp" ok
#include <chrono>
using namespace std::chrono;

static_assert( is_clock_v<system_clock>);
static_assert( is_clock_v<steady_clock>);
static_assert( is_clock_v<file_clock>);
static_assert(!is_clock_v<local_t>);        // 伪时钟：没有 now()
static_assert(!is_clock_v<seconds>);

int main() {}
```

## 小结

| 特征 | 作用 | 用户可特化？ |
|---|---|---|
| `treat_as_floating_point` | 决定 duration 间是否允许需要除法的隐式转换 | 可以 |
| `duration_values` | `zero()`=`Rep(0)`、`min()`=`lowest()`、`max()` | 可以 |
| `common_type<duration, duration>` | 周期取 gcd：只靠乘法、不截断 | —（标准已提供） |
| `is_clock` | 语法层面检查 *Cpp17Clock* | **不可以**，特化即 UB |
