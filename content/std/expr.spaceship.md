---
title: 三路比较运算符
summary: "内置 <=> 的结果类型（strong_ordering / partial_ordering）；bool 与非 bool 混用、需要窄化转换（如 int 对 unsigned）时非良构；同一枚举类型按底层类型比较；对象指针按复合指针类型比较；比较类别类型不是预定义的，必须先包含 <compare>"
status: done
since: c++20
papers: P0515R3, P1120R0
related: expr.rel, expr.eq, expr.arith.conv, dcl.init.list, expr.type, cmp.categories, class.spaceship, over.match.oper, compare.syn
tags: 比较, 三路比较, 窄化
updated: 2026-10-17
---

`<=>`（俗称"宇宙飞船运算符"，spaceship operator）是 C++20 由 [[P0515R3]]（Consistent comparison）引入的。它一次比较得出"小于 / 等于 / 大于 / 无序"四种结果之一，结果是一个**比较类别类型**（comparison category type，[[cmp.categories]]）的值。它的主要用途在类类型上：`auto operator<=>(const T&) const = default;` 一行代码生成全部关系比较（[[class.spaceship]]），而 `a < b` 可以被**重写**为 `(a <=> b) < 0`（[[over.match.oper]]）。

本节只管**内置**的 `<=>`：操作数是算术、枚举、对象指针时它做什么。与 `<`、`==` 这些"老"运算符相比，内置 `<=>` 刻意**更严格**——它借新运算符之机，拒绝了几种长期被认为是陷阱的混合比较（有符号对无符号、`bool` 对整数、数组对数组）。理解这些"拒绝"背后的理由，是本节的重点。

## 文法与结果（¶1–¶2）

¶1 三路比较从左往右结合，优先级介于移位与关系运算符之间：

```text
compare-expression:
    shift-expression
    compare-expression <=> shift-expression
```

这个优先级是精心选择的：`a <=> b < 0` 解析为 `(a <=> b) < 0`，正是使用比较结果的惯用写法；`a << b <=> c` 是 `(a << b) <=> c`。

¶2 `p <=> q` 是一个 prvalue，表示 `p` 小于、等于、大于 `q`，或者两者**无法比较**（incomparable）。具体是哪种比较类别类型，由下面几段按操作数类型决定。

## `bool` 不与其他类型混比（¶3）

¶3 若一个操作数是 `bool` 而另一个不是，程序**非良构**。`true <=> false` 合法（两个算术类型，见 ¶4，结果 `strong_ordering`），但 `true <=> 1` 不合法：

```cpp title="spaceship-bool.cpp" error
#include <compare>

auto a = true <=> false;   // OK: strong_ordering
auto b = true <=> 1;       // error: bool 与非 bool
```

对比之下，`true < 2` 在关系运算符中是合法的（`bool` 提升为 `int`），但它几乎总是 bug（例如把 `a < b < c` 写成链式比较）。新运算符没有历史包袱，于是直接禁止。

## 算术类型：禁止窄化（¶4）

¶4 若两个操作数都是算术类型，或者一个是整型、另一个是无作用域枚举，先做**常用算术转换**（[[expr.arith.conv]]），然后：

- ¶4.1 如果转换中需要**窄化转换**（narrowing conversion，[[dcl.init.list]]）——**整型到浮点的转换除外**——程序非良构；
- ¶4.2 否则若操作数是整型，结果类型为 `std::strong_ordering`，按数学大小给出 `less` / `equal` / `greater`；
- ¶4.3 否则操作数是浮点类型，结果为 `std::partial_ordering`：小于、大于、**等价**（equivalent）、或**无序**（unordered，有 NaN 时）。

### 为什么禁止窄化？

最典型的窄化来自"有符号对无符号"。常用算术转换把 `int` 转成 `unsigned`，于是 `-1 < 1u` 是 `false`——这是 C 继承下来的最臭名昭著的陷阱之一。`<=>` 拒绝它：

```cpp title="spaceship-narrowing.cpp" error
#include <compare>

int i = -1;
unsigned u = 1;
bool old = i < u;              // 合法但结果是 false（-1 被转换为 UINT_MAX）
auto r1 = i <=> u;             // error: int → unsigned 是窄化转换
auto r2 = -1 <=> 1u;           // error: 常量 -1 无法放进 unsigned
```

注意窄化是按 [[dcl.init.list]] 的定义判断的：**值可以放下的常量表达式不算窄化**。所以下面这些都合法：

```cpp run title="spaceship-narrowing-ok.cpp" ok
#include <compare>

unsigned u = 1;
auto a = 1 <=> u;        // OK: 常量 1 能放进 unsigned，不是窄化
auto b = 'a' <=> 1u;     // OK: 'a' 提升为 int，常量 97 能放进 unsigned
unsigned char uc = 200;
auto c = uc <=> -1;      // OK: uc 提升为 int，两边都是 int，不需要转换
long long ll = 0;
auto d = u <=> ll;       // OK（当 long long 能表示 unsigned 的全部值时）：u 转为 long long，不窄化

int main() { return (c > 0 && d > 0) ? 0 : 1; }
```

最后一行暴露了一个可移植性细节：是否窄化取决于常用算术转换的结果，而后者依赖于各类型的宽度。例如在 LP64 平台上，`unsigned long <=> long long` 两者都是 64 位，常用算术转换把 `long long` 转为 `unsigned long long`，这是窄化，非良构；在 `long` 为 32 位的平台上，同样的代码会把 `unsigned long` 转为 `long long`，合法。

### 为什么允许整型到浮点？

整型到浮点在 [[dcl.init.list]] 中也是窄化（`long long` → `double` 可能丢精度），但 `<=>` 特意放过它。原因是混合比较整数与浮点极为常见（`i <=> 0.5`、`count <=> threshold`），而它的风险与有符号/无符号问题性质不同：转换后的结果在数学上"差不多对"，而不是像 `-1 → UINT_MAX` 那样面目全非。全部禁止的话，代价远大于收益。

```cpp run title="spaceship-arith.cpp" ok
#include <compare>
#include <limits>
#include <type_traits>

static_assert(std::is_same_v<decltype(1 <=> 2), std::strong_ordering>);
static_assert(std::is_same_v<decltype(1 <=> 2.0), std::partial_ordering>);   // int → double 被允许
static_assert(std::is_same_v<decltype(true <=> false), std::strong_ordering>);
static_assert((-1 <=> 1L) < 0);
static_assert(std::is_eq(-0.0 <=> 0.0));                                     // equivalent，而非 equal
static_assert((std::numeric_limits<double>::quiet_NaN() <=> 1.0)
              == std::partial_ordering::unordered);

int main() {}
```

浮点给出 `partial_ordering` 而不是 `weak_ordering`，是因为 NaN 与任何值（包括自身）都**无序**；而 `-0.0` 与 `+0.0` 是**等价**而不是**相等**——它们可区分（`1/-0.0` 与 `1/+0.0` 不同），所以不能用 `strong_ordering::equal` 的"可替换性"语义。内置 `<=>` 从不产生 `weak_ordering`；后者留给用户定义类型（如大小写不敏感的字符串）。

## 枚举（¶5）

¶5 若两个操作数是**同一个枚举类型** `E`，结果等于把两者转换为 `E` 的底层类型后再做 `<=>`。这对**有作用域枚举**同样适用——尽管有作用域枚举不能参与算术运算，但可以直接比较：

```cpp run title="spaceship-enum.cpp" ok
#include <compare>

enum class Level { low, mid, high };
enum Plain { p0, p1 };

static_assert((Level::low <=> Level::high) < 0);   // OK: 同一有作用域枚举
static_assert((p1 <=> 0) > 0);                     // OK: 无作用域枚举对整型（¶4）

int main() {}
```

```cpp title="spaceship-enum-bad.cpp" error
#include <compare>

enum A { a0 };
enum B { b0 };
enum class S { s0 };

auto r1 = a0 <=> b0;       // error: 不同枚举类型（落入 ¶7）
auto r2 = a0 <=> 1.0;      // error: 无作用域枚举对浮点（¶4 只允许"枚举对整型"）
auto r3 = S::s0 <=> 0;     // error: 有作用域枚举对整型
```

`a0 <=> b0` 与 `a0 <=> 1.0` 对 `<` 而言在 C++20/23 中只是被**弃用**（[[P1120R0]]），C++26 才对关系与相等运算符也改成非良构（见 [[expr.arith.conv]]、[[diff.cpp23.expr]]）；而 `<=>` 从诞生起就不允许。

## 指针（¶6）

¶6 若至少一个操作数是**对象指针**类型，另一个是对象指针或数组类型：对两个操作数做数组到指针、指针转换和限定转换，使之成为**复合指针类型**（composite pointer type，[[expr.type]]），转换后两者类型必须相同。结果类型是 `std::strong_ordering`：

- ¶6.1 两指针**相等**（按 [[expr.eq]]）：`equal`；
- ¶6.2 否则，若两者**不等**：按 [[expr.rel]] 的规则，`q` 大于 `p` 时为 `less`，`p` 大于 `q` 时为 `greater`；
- ¶6.3 否则（关系运算符的结果未指定时）：结果**未指定**。

注 1 特别指出：如果**两个操作数都是数组**，**不**进行数组到指针转换——于是两个数组无法比较，落到 ¶7 非良构。这与 C++26 对 `==`、`<` 的修改一致（[[expr.rel]]）。

```cpp run title="spaceship-ptr.cpp" ok
#include <compare>

struct S { int a, b; };

constexpr bool f() {
    S s{};
    int arr[4]{};
    void* p = arr;          // void* 也是对象指针类型
    void* q = arr + 1;
    int* pa = arr;
    return (&s.a <=> &s.b) < 0          // 后声明的成员地址更大（[expr.rel]）
        && (p <=> q) < 0
        && (pa <=> arr) == 0;           // 一边是指针，另一边是数组：数组退化
}
static_assert(f());

int main() {}
```

```cpp title="spaceship-ptr-bad.cpp" error
#include <compare>

void f(); void g();
struct S { int a, b; };
int x, y;
int arr1[2], arr2[2];

auto r1 = &f <=> &g;               // error: 函数指针不是对象指针
auto r2 = nullptr <=> nullptr;     // error: nullptr_t 不是指针
auto r3 = &S::a <=> &S::b;         // error: 成员指针
auto r4 = arr1 <=> arr2;           // error: 两个数组不退化（注 1）
constexpr bool r5 = (&x <=> &y) < 0;  // error: 结果未指定 ⇒ 不是常量表达式
```

最后一行在**运行期**是合法的（结果未指定，但不是 UB）；只是在常量求值中，"结果未指定的比较"使表达式不是核心常量表达式（[[expr.const.core]]）。需要对任意指针得到一致的全序时，使用 `std::compare_three_way`（[[comparisons.three.way]]），它对指针使用实现定义的严格全序。

函数指针被排除在外与 `<` 的情况一致：对不等的函数指针做关系比较，结果本就未指定（[[expr.rel]] 注 1），没有意义；`<=>` 干脆不允许。

## 比较类别类型不是预定义的（¶8）

¶8 `std::strong_ordering`、`std::weak_ordering`、`std::partial_ordering` **不是**语言内建的类型；它们由标准库头文件 `<compare>`（[[compare.syn]]）或标准库模块声明。如果在使用这些类型之前没有可达的标准库声明——**即使是隐式使用**，比如使用内置 `<=>`，或者在返回类型为 `auto` 的默认化 `operator<=>` 中——程序非良构：

```cpp title="spaceship-no-include.cpp" error
// 没有 #include <compare>
auto r = 1 <=> 2;   // error: 内置 <=> 的结果类型 std::strong_ordering 未声明
```

Clang 的诊断是 "cannot use builtin operator '<=>' because type 'std::strong_ordering' was not found; include <compare>"。

这是一个有意的设计：核心语言依赖标准库类型的情况很少（另见 `std::initializer_list`、`std::type_info`、`std::nullptr_t` 的声明方式），这样做可以把比较类别的全部接口（与字面量 `0` 比较、`is_eq` 等辅助函数）放在库里定义和演进，语言只负责"选哪个类别、哪个值"。

## 实现视角

!!! impl
    - 比较类别类型在 libstdc++ 与 libc++ 中都实现为只含一个 `signed char` 成员的类（`sizeof` 为 1），`less`/`equal`/`greater` 对应 −1/0/1 一类的小整数，`partial_ordering::unordered` 用另一个专用值表示。`(a <=> b) < 0` 在优化后通常与直接写 `a < b` 生成相同的代码。
    - 与 `0` 比较的接口（`r < 0`）在库中通过一个只能由字面量 `0` 构造的参数类型实现，所以 `r < 1` 无法编译——这同样是库的约定，不是核心语言规则。
    - Clang 对窄化的诊断形如 "argument to 'operator<=>' cannot be narrowed from type 'int' to 'unsigned int'"。

## 历史与演进

!!! history
    - **C++20**：[[P0515R3]] 引入 `<=>` 与比较类别；内置 `<=>` 从一开始就拒绝有符号/无符号混比、`bool` 混比、数组比较。同期的 [[P1120R0]] 借机**弃用**了 `==`、`<` 等老运算符上的数组比较以及枚举与浮点/不同枚举之间的算术转换。
    - **C++26**：上述被弃用的比较对老运算符也成为非良构（[[diff.cpp23.expr]]）。至此 `<=>` 与关系/相等运算符在"哪些类型组合可以比较"上基本对齐——唯一显著的差别仍是有符号/无符号：`-1 < 1u` 至今合法（只是常被编译器警告），`-1 <=> 1u` 非良构。
    - 引入 `<=>` 也改变了词法：`<=>` 成为一个新记号，`operator<=>` 之后紧跟 `>` 的旧代码可能改变含义（[[diff.cpp17.lex]]）。

## 陷阱

!!! pitfall "以为 `<=>` 与 `<` 接受相同的操作数"
    `<=>` 拒绝 `int` 对 `unsigned`（非常量、或常量放不下）、`bool` 对非 `bool`、函数指针；`<` 都接受。

!!! pitfall "忘记 `#include <compare>`"
    内置 `<=>` 也需要比较类别类型的声明。很多标准头文件间接包含了 `<compare>`，所以这个错误常常只在精简的翻译单元里出现。

!!! pitfall "以为浮点 `<=>` 能给出全序"
    NaN 使结果为 `unordered`。需要浮点全序时用 `std::strong_order`（[[cmp.alg]]），它按 IEEE 754 的 totalOrder 排序。

!!! pitfall "以为无关指针的 `<=>` 是 UB"
    不是 UB，而是**结果未指定**；在常量求值中不是常量。

## 思考题

!!! question "思考题 1"
    下面哪些是良构的？（假设 `int` 32 位、`long` 64 位）

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

- `a`：`short` 与 `unsigned short` 都提升为 `int`，无需进一步转换 → 良构，`strong_ordering`，结果 `less`。这正是整数提升"救了"窄类型的情形。
- `b`：`s` 提升为 `int`，`int` 对 `unsigned int` → `int` 转为 `unsigned int`，`s` 不是常量 → 窄化 → **非良构**。
- `c`：`long`（64 位）能表示 `unsigned int` 的全部值 → `ui` 转为 `long`，不窄化 → 良构，结果 `less`。
- `d`：`1LL` 转为 `float`，整型到浮点的窄化被 ¶4.1 豁免 → 良构，`partial_ordering`。
</details>

!!! question "思考题 2"
    为什么 ¶6 要求"至少一个操作数是对象指针类型"，而不是"两个都是指针"？

<details markdown="1">
<summary>答案</summary>

为了允许"指针对数组"的比较：`int* p; int a[3]; p <=> a`。此时一边是指针、一边是数组，数组经数组到指针转换后再求复合指针类型。如果要求两边都是指针类型，这种自然的写法就不能用了。而"两个都是数组"被注 1 排除（不做数组到指针转换），从而落入 ¶7 非良构。另一方面，"另一个操作数是对象指针**或数组**"也意味着：**空指针常量不在其列**。`p <=> nullptr`（`std::nullptr_t` 不是指针类型）和 `p <=> 0`（`int`）都落入 ¶7，非良构——Clang 分别报 "invalid operands" 和 "ordered comparison between pointer and zero"。这与 `<` 一致：[[expr.rel]] 同样要求转换后两边都是指针（只是 `==` 对空指针常量网开一面，见 [[expr.eq]]）。与空指针做"大小比较"本来就没有意义。
</details>

## 小结

| 操作数 | 结果类型 | 限制 | 段落 |
|---|---|---|---|
| `bool` 与非 `bool` | — | {{ill-formed}} | ¶3 |
| 整型（含整型对无作用域枚举） | `strong_ordering` | 需要窄化（整型→浮点除外）则非良构 | ¶4 |
| 含浮点 | `partial_ordering` | 同上；NaN 给出 `unordered` | ¶4 |
| 同一枚举类型（含有作用域枚举） | 按底层类型 | — | ¶5 |
| 对象指针（或指针对数组） | `strong_ordering` | 无关指针结果未指定 | ¶6 |
| 两个数组、函数指针、成员指针、`nullptr_t`、指针对 `0`、不同枚举、枚举对浮点 | — | {{ill-formed}} | ¶6 注 1、¶7 |
| 未声明比较类别类型 | — | {{ill-formed}} | ¶8 |
