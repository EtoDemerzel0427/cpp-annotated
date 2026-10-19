---
title: 三路比较运算符
summary: 内置 <=> 对整数给出 strong_ordering、对浮点给出 partial_ordering；它拒绝 bool 与其他类型混比、需要窄化的有符号/无符号比较、两个数组和函数指针；使用前必须包含 <compare>。
status: done
since: c++20
papers: P0515R3, P1120R0
related: expr.rel, expr.eq, expr.arith.conv, dcl.init.list, expr.type, cmp.categories, class.spaceship, over.match.oper, compare.syn
tags: 比较, 三路比较, 窄化
updated: 2026-10-19
---

!!! tldr
    - `a <=> b` 一次比较给出小于、等于、大于或无序，结果是 `<compare>` 里的比较类别类型：整数和指针得到 `std::strong_ordering`，浮点得到 `std::partial_ordering`。
    - 内置 `<=>` 比 `<` 严格：`bool` 不能与其他类型比较；常用算术转换如果要做窄化转换（典型是 `int` 对 `unsigned`），程序非良构。整型到浮点的转换例外。
    - 同一枚举类型按底层类型比较，有作用域枚举也可以；对象指针按复合指针类型比较，两个数组、函数指针、成员指针、`nullptr` 都不行。
    - 比较类别类型不是语言内建的，没有包含 `<compare>`（或 `import std;`）就使用内置 `<=>`，程序非良构。

`<=>` 是 C++20 由 [[P0515R3]] 引入的，常叫宇宙飞船运算符（spaceship operator）。它的主要用途是类类型：`auto operator<=>(const T&) const = default;` 一行就能生成全部关系比较（[[class.spaceship]]），而 `a < b` 可以改写为 `(a <=> b) < 0`（[[over.match.oper]]）。本节只讲操作数是算术类型、枚举、对象指针时的内置 `<=>`。

## 结果是什么（¶1、¶2、¶4）

```cpp run title="spaceship-arith.cpp" ok
#include <compare>
#include <limits>
#include <type_traits>

static_assert(std::is_same_v<decltype(1 <=> 2), std::strong_ordering>);
static_assert(std::is_same_v<decltype(1 <=> 2.0), std::partial_ordering>);
static_assert((-1 <=> 1L) < 0);
static_assert(std::is_eq(-0.0 <=> 0.0));                    // equivalent
static_assert((std::numeric_limits<double>::quiet_NaN() <=> 1.0)
              == std::partial_ordering::unordered);

int main() {}
```

¶2 `p <=> q` 是一个 prvalue，表示 `p` 小于、等于、大于 `q`，或者两者无法比较。结果的类型是一个**比较类别类型**（[[g:comparison-category-type]]，[[cmp.categories]]），由操作数类型决定。使用时把结果与字面量 `0` 比较，或者用 `std::is_lt`、`std::is_eq` 这类辅助函数。

¶4 两个操作数都是算术类型时，先做常用算术转换（[[expr.arith.conv]]），然后：

- ¶4.2 整型的结果是 `std::strong_ordering`，按数学大小给出 `less`、`equal` 或 `greater`。
- ¶4.3 浮点的结果是 `std::partial_ordering`，给出 `less`、`greater`、`equivalent` 或 `unordered`。有 NaN 参与时是 `unordered`，因为 NaN 与任何值都无法比较，包括它自己。

`partial_ordering` 没有 equal 这个值，只有 equivalent，所以 `-0.0 <=> 0.0` 是 `equivalent`。内置 `<=>` 从不产生 `std::weak_ordering`，它留给用户定义的类型，例如大小写不敏感的字符串。

¶1 `<=>` 从左往右结合，优先级介于移位和关系运算符之间。所以 `a <=> b < 0` 解析为 `(a <=> b) < 0`，正是使用结果的惯用写法。

## 比 `<` 更严格的地方

内置 `<` 从 C 继承了几种容易出错的混合比较。新运算符没有兼容包袱，于是直接拒绝它们。

### `bool` 只能与 `bool` 比较（¶3）

<div class="compare" markdown="1">

```cpp ok
#include <compare>
auto a = true <=> false;
// strong_ordering::greater
```

```cpp error
#include <compare>
auto b = true <=> 1;
// error: bool 与非 bool
```

</div>

¶3 一个操作数是 `bool`、另一个不是，程序非良构。对比之下 `true < 2` 是合法的，`bool` 提升为 `int`。这种比较几乎总是 bug，例如把 `a < b < c` 当成链式比较。

### 不允许窄化（¶4.1）

```cpp title="spaceship-narrowing.cpp" error
#include <compare>

int i = -1;
unsigned u = 1;
bool old = i < u;              // 合法，但结果是 false：-1 被转换为 UINT_MAX
auto r1 = i <=> u;             // error: int → unsigned 是窄化转换
auto r2 = -1 <=> 1u;           // error: 常量 -1 放不进 unsigned
```

¶4.1 如果常用算术转换需要做一次**窄化转换**（narrowing conversion），程序非良构，整型到浮点的转换除外。窄化的定义来自列表初始化（[[dcl.init.list]]）：大致是目标类型不能表示源类型的全部值，例如 `int` 到 `unsigned`、`long long` 到 `int`。

有符号与无符号的比较是从 C 继承来的最著名的陷阱：常用算术转换把 `-1` 变成 `UINT_MAX`，于是 `-1 < 1u` 为假。`<=>` 拒绝这种比较。Clang 的诊断是 "argument to 'operator<=>' cannot be narrowed from type 'int' to 'unsigned int'"。

窄化的定义有一个例外：源是常量表达式、而且值能放进目标类型时不算窄化。整数提升也可能让两边变成同一类型，根本不需要转换。所以下面这些都合法：

```cpp run title="spaceship-narrowing-ok.cpp" ok
#include <compare>

unsigned u = 1;
auto a = 1 <=> u;        // 常量 1 能放进 unsigned，不算窄化
auto b = 'a' <=> 1u;     // 'a' 提升为 int，常量 97 能放进 unsigned
unsigned char uc = 200;
auto c = uc <=> -1;      // uc 提升为 int，两边都是 int
long long ll = 0;
auto d = u <=> ll;       // long long 能表示 unsigned 的全部值，u 转为 long long

int main() { return (c > 0 && d > 0) ? 0 : 1; }
```

是否窄化取决于常用算术转换的结果，而后者依赖各类型的宽度，所以同一行代码可能在一个平台合法、在另一个平台非良构。例如 `unsigned long <=> long long`：在 `long` 为 64 位的平台上，`long long` 被转换为 `unsigned long long`，这是窄化；在 `long` 为 32 位的平台上，`unsigned long` 被转换为 `long long`，合法。

整型到浮点在列表初始化里也算窄化，`long long` 转 `double` 可能丢精度，但 `<=>` 特意放过了它。整数与浮点混合比较非常常见，转换后的结果也大致正确，不像 `-1` 变成 `UINT_MAX` 那样完全改变了值。

## 枚举（¶4、¶5）

¶5 两个操作数是同一个枚举类型时，结果等于把两者转换为底层类型后再做 `<=>`。有作用域枚举不能参与算术运算，但同类型之间可以这样比较。¶4 还允许无作用域枚举与整型比较，此时按常用算术转换处理。

```cpp run title="spaceship-enum.cpp" ok
#include <compare>

enum class Level { low, mid, high };
enum Plain { p0, p1 };

static_assert((Level::low <=> Level::high) < 0);   // 同一个有作用域枚举（¶5）
static_assert((p1 <=> 0) > 0);                     // 无作用域枚举对整型（¶4）

int main() {}
```

其余组合都落入第 7 段，程序非良构：

```cpp title="spaceship-enum-bad.cpp" error
#include <compare>

enum A { a0 };
enum B { b0 };
enum class S { s0 };

auto r1 = a0 <=> b0;       // error: 两个不同的枚举类型
auto r2 = a0 <=> 1.0;      // error: ¶4 只允许枚举对整型，不允许枚举对浮点
auto r3 = S::s0 <=> 0;     // error: 有作用域枚举对整型
```

把 `r1`、`r2` 换成 `<`，在 C++20/23 中只是弃用（[[P1120R0]]），C++26 才改为非良构（[[diff.cpp23.expr]]）；`<=>` 从一开始就不允许。

## 指针（¶6）

```cpp run title="spaceship-ptr.cpp" ok
#include <compare>

struct S { int a, b; };

constexpr bool f() {
    S s{};
    int arr[4]{};
    void* p = arr;          // void* 也是对象指针类型
    void* q = arr + 1;
    int* pa = arr;
    return (&s.a <=> &s.b) < 0      // 后声明的成员地址更大（[expr.rel]）
        && (p <=> q) < 0
        && (pa <=> arr) == 0;       // 一边是指针，另一边的数组退化
}
static_assert(f());

int main() {}
```

¶6 至少一个操作数是对象指针，另一个是对象指针或数组时，对两边做数组到指针、指针转换和限定转换，得到**复合指针类型**（composite pointer type，[[expr.type]]），也就是两个指针都能转换到的公共指针类型。转换后两边类型必须相同。结果是 `std::strong_ordering`：

- ¶6.1 两个指针相等（按 [[expr.eq]]），结果是 `equal`。
- ¶6.2 不等时，按 [[expr.rel]] 的偏序给出 `less` 或 `greater`。
- ¶6.3 [[expr.rel]] 不规定谁大时，例如两个无关对象的地址，结果未指定。

注 1 指出，两个操作数都是数组时不做数组到指针转换，于是两个数组无法比较，落入第 7 段。下面这些都非良构：

```cpp title="spaceship-ptr-bad.cpp" error
#include <compare>

void f(); void g();
struct S { int a, b; };
int x, y;
int arr1[2], arr2[2];

auto r1 = &f <=> &g;               // error: 函数指针不是对象指针
auto r2 = nullptr <=> nullptr;     // error: nullptr_t 不是指针类型
auto r3 = &S::a <=> &S::b;         // error: 成员指针
auto r4 = arr1 <=> arr2;           // error: 两个数组不退化（注 1）
constexpr bool r5 = (&x <=> &y) < 0;  // error: 结果未指定，不是常量表达式
```

最后一行的比较在运行期是合法的，结果未指定但不是 UB。只是在常量求值中，结果未指定的比较使表达式不再是常量表达式（[[expr.const.core]]）。需要对任意指针得到一致的全序时，用 `std::compare_three_way`（[[comparisons.three.way]]）。

函数指针被排除，是因为 `<` 对不等的函数指针本来就只给出未指定的结果（[[expr.rel#5]] 注 1），没有比较大小的意义。同理，`p <=> nullptr` 和 `p <=> 0` 也非良构，因为空指针常量既不是对象指针也不是数组。

## 必须先包含 `<compare>`（¶8）

```cpp title="spaceship-no-include.cpp" error
// 没有 #include <compare>
auto r = 1 <=> 2;   // error: std::strong_ordering 未声明
```

¶8 `std::strong_ordering`、`std::weak_ordering`、`std::partial_ordering` 不是预定义的类型，由 `<compare>`（[[compare.syn]]）或标准库模块声明。使用这些类型之前，如果找不到它们的标准库声明，程序非良构。隐式的使用也算：使用内置 `<=>`，或者返回类型为 `auto` 的默认化 `operator<=>`，都会隐式用到它们。

Clang 的诊断是 "cannot use builtin operator '<=>' because type 'std::strong_ordering' was not found; include <compare>"。很多标准头文件间接包含了 `<compare>`，所以这个错误通常只在精简的翻译单元里出现。

这样设计，比较类别的全部接口（与 `0` 比较、`is_eq` 等）都可以放在库里定义和演进，语言只负责选择哪个类别、哪个值。`std::initializer_list` 和 `std::type_info` 也是语言依赖库类型的例子。

## 实现视角

!!! impl
    - libstdc++ 和 libc++ 都把比较类别类型实现为只含一个 `signed char` 成员的类，`sizeof` 为 1。`(a <=> b) < 0` 优化后通常与直接写 `a < b` 生成相同的代码。
    - `r < 0` 这类接口通过一个只能由字面量 `0` 构造的参数类型实现，所以 `r < 1` 无法编译。这是库的约定，不是核心语言规则。

## 历史与演进

!!! history
    - C++20：[[P0515R3]] 引入 `<=>` 和比较类别。内置 `<=>` 从一开始就拒绝有符号/无符号的窄化比较、`bool` 混比和数组比较。[[P1120R0]] 同时弃用了 `==`、`<` 等旧运算符上的数组比较，以及枚举与浮点、不同枚举之间的算术转换。
    - C++26：这些被弃用的用法在旧运算符上也成为非良构（[[diff.cpp23.expr]]）。`<` 与 `<=>` 仍有差别：`-1 < 1u`、`true < 2`、不等函数指针的 `<` 至今合法，对应的 `<=>` 都非良构。
    - `<=>` 是一个新记号，这改变了词法分析。C++17 中 `<=` 后紧跟 `>` 的代码，例如模板实参 `Y<operator<=> y;`（意思是 `Y<operator<= > y;`），在 C++20 中会被切成 `<=>`，从而非良构（[[diff.cpp17.lex]]）。

## 常见误解

!!! pitfall "`<=>` 与 `<` 接受相同的操作数"
    `<=>` 拒绝需要窄化的 `int` 对 `unsigned`、`bool` 对非 `bool`、函数指针，`<` 都接受。

!!! pitfall "浮点的 `<=>` 能给出全序"
    NaN 使结果为 `unordered`。需要浮点全序时用 `std::strong_order`（[[cmp.alg]]），它按 IEEE 754 的 totalOrder 排序。

!!! pitfall "无关指针的 `<=>` 是 UB"
    不是 UB，只是结果未指定；在常量求值中它不是常量。

## 思考题

!!! question "思考题 1"
    设 `int` 为 32 位、`long` 为 64 位。下面哪些良构？

    ```cpp
    #include <compare>
    short s = -1; unsigned short us = 1; unsigned int ui = 1; long l = -1;
    auto a = s <=> us;
    auto b = s <=> ui;
    auto c = l <=> ui;
    auto d = 1.0f <=> 1LL;
    ```

<details markdown="1">
<summary>答案</summary>

- `a`：`short` 和 `unsigned short` 都提升为 `int`，不再需要转换。良构，`strong_ordering::less`。
- `b`：`s` 提升为 `int`，`int` 对 `unsigned int` 要把 `s` 转为 `unsigned int`，`s` 不是常量，这是窄化。非良构。
- `c`：64 位的 `long` 能表示 `unsigned int` 的全部值，`ui` 转为 `long`，不窄化。良构，结果 `less`。
- `d`：`1LL` 转为 `float`，整型到浮点的窄化被第 4.1 项豁免。良构，`partial_ordering`。
</details>

!!! question "思考题 2"
    第 6 段为什么写成“至少一个是对象指针，另一个是对象指针或数组”，而不是“两个都是指针”？

<details markdown="1">
<summary>答案</summary>

为了允许指针与数组比较：`int* p; int a[3]; p <=> a`。数组经数组到指针转换后再求复合指针类型。两个都是数组的情形由注 1 排除，落入第 7 段。

这个写法也把空指针常量排除在外：`nullptr` 的类型是 `std::nullptr_t`，`0` 是 `int`，都不是对象指针或数组，所以 `p <=> nullptr` 和 `p <=> 0` 都非良构。这与 `<` 一致，[[expr.rel]] 同样要求两边转换后都是指针；只有 `==` 接受空指针常量（[[expr.eq]]）。
</details>

## 小结

| 操作数 | 结果类型 | 限制 | 段落 |
|---|---|---|---|
| `bool` 与非 `bool` | | {{ill-formed}} | ¶3 |
| 整型，或整型对无作用域枚举 | `strong_ordering` | 需要窄化则非良构（整型到浮点除外） | ¶4 |
| 含浮点 | `partial_ordering` | 同上；NaN 给出 `unordered` | ¶4 |
| 同一枚举类型 | 按底层类型 | | ¶5 |
| 对象指针，或指针对数组 | `strong_ordering` | 无关指针结果未指定 | ¶6 |
| 两个数组、函数指针、成员指针、`nullptr`、不同枚举、枚举对浮点 | | {{ill-formed}} | ¶6 注 1、¶7 |
| 未声明比较类别类型 | | {{ill-formed}} | ¶8 |
