---
title: 寻常算术转换
summary: 二元算术、比较、位运算和条件运算符怎样把两个算术或枚举操作数统一到一个公共类型。
status: done
papers: P1120R0, P2864R2, P1467R9
related: conv.prom, conv.rank, conv.integral, expr.mul, expr.add, expr.rel, expr.eq, expr.spaceship, expr.cond, dcl.enum
tags: 转换, 整数, 浮点, 枚举, 陷阱
updated: 2026-10-19
---

!!! tldr
    - 两个算术或枚举操作数参与 `+`、`<`、`&`、`?:` 等运算前，先按一个固定的五步算法转换到公共类型，这个类型通常也是结果类型。
    - 有浮点操作数时，整数一律转成浮点，即使会丢精度；两个浮点类型取等级高的那个。
    - 全是整数时先做整型提升；符号不同且无符号类型的等级不低于有符号类型时，结果是无符号类型，所以 `-1 < 0u` 为假。
    - 窄的无符号类型（`unsigned short`、`uint16_t`）会先提升为有符号的 `int`，因此它们的乘法也可能有符号溢出。
    - C++26 起，不同枚举之间、枚举与浮点之间的运算非良构；有作用域枚举只能和同类型的操作数一起用。

```cpp run ok
#include <cstdio>
int main() {
  std::printf("%d\n", -1 < 0u);   // 0
  std::printf("%d\n", -1 < 0L);   // 1
}
```

`-1 < 0u` 的结果是假。比较之前，两个操作数要先转换到同一个类型；`int` 和 `unsigned int` 的公共类型是 `unsigned int`，于是 `-1` 变成了 `UINT_MAX`。决定这个公共类型的规则叫**寻常算术转换**（[[g:usual-arithmetic-conversions|usual arithmetic conversions]]）。

## 哪些运算符使用它

| 运算符 | 条款 | 备注 |
|---|---|---|
| `*` `/` `%` | [[expr.mul]] | |
| `+` `-` | [[expr.add]] | 一方是指针时不适用 |
| `<` `>` `<=` `>=` `==` `!=` | [[expr.rel]]、[[expr.eq]] | 结果是 `bool`，公共类型只用于比较 |
| `<=>` | [[expr.spaceship]] | 另外禁止窄化（整数转浮点除外） |
| `&` `^` `\|` | [[expr.bit.and]] 等 | |
| `?:` | [[expr.cond]] | 第二、第三操作数都是算术或枚举类型时 |
| `+=` 等复合赋值 | [[expr.assign]] | 按 `E1 = E1 op E2` 计算 |

移位运算 `<<`、`>>` 不使用它：两个操作数各自做整型提升，结果类型是提升后的左操作数类型（[[expr.shift]]）。一元运算符只做整型提升，逻辑运算符把操作数按语境转换为 `bool`。

## 五步算法

¶1 算法按顺序检查五种情况，第一个适用的决定结果。

### 第 1 步：读值

¶1.1 先对两个操作数做左值到右值转换（[[conv.lval]]），后面的步骤只处理得到的 prvalue。

### 第 2 步：有作用域枚举

¶1.2 如果任一操作数是有作用域枚举类型（`enum class`，[[dcl.enum]]），就不做任何转换，另一个操作数的类型必须与它相同，否则表达式非良构。

```cpp error
enum class Color { red, green };
bool c1 = Color::red == Color::green;  // OK：类型相同
bool c2 = Color::red == 0;             // error: 类型不同
auto c3 = Color::red + Color::red;     // error: + 不接受有作用域枚举
```

`c3` 通过了这一步，但 [[expr.add]] 自己要求操作数是算术类型或无作用域枚举，所以仍然非良构。

### 第 3 步：枚举与另一枚举或浮点 {{c++26}}

¶1.3 如果一个操作数是枚举类型，另一个是不同的枚举类型或浮点类型，表达式非良构。

```cpp error
enum A { a1 };
enum B { b1 };

auto x1 = a1 + b1;         // error: 不同的枚举类型
bool x2 = a1 == b1;        // error: 比较也一样
auto x3 = a1 | b1;         // error: 位运算也一样
auto x4 = a1 + 1.0;        // error: 枚举与浮点
auto x5 = true ? a1 : b1;  // error: 条件运算符也一样

auto ok1 = a1 + 1;         // OK：枚举与整数
auto ok2 = a1 | a1;        // OK：同一枚举类型，结果是 int
auto ok3 = +a1 + +b1;      // OK：一元 + 先提升为 int
```

两个不相关枚举之间的运算几乎总是写错了，例如把文件模式和权限位按位或在一起；枚举与浮点混合运算也没有合理的含义。真需要时，用一元 `+` 或 `static_cast<int>` 写明意图。

同一枚举类型的两个操作数、枚举与整数的组合都不受影响，所以用无作用域枚举做位标志（`flags | FLAG_A`）的代码照常编译。

!!! history "从弃用到删除"
    C++17 及以前，这些运算都合法：枚举先做整型提升，再按整数规则转换。C++20 由 [[P1120R0]] 把它们标为弃用，Clang 在 `-std=c++20` 下给出 `-Wdeprecated-enum-enum-conversion`、`-Wdeprecated-enum-float-conversion` 等警告。C++26 由 [[P2864R2]] 删除（{{removed:C++26}}），Clang 23 在 `-std=c++2c` 下对上例全部报错。

### 第 4 步：有浮点操作数

¶1.4 如果任一操作数是浮点类型：

- ¶1.4.1 两者类型相同，不再转换。
- ¶1.4.2 一个不是浮点类型（整数或无作用域枚举），就把它转换为另一个操作数的浮点类型。
- ¶1.4.3 两者的**浮点转换等级**（[[conv.rank#2]]）不同且可比较，等级低的转换为等级高的类型。
- ¶1.4.4 等级相同，**子等级**（subrank，[[conv.rank#3]]）低的转换为子等级高的类型。
- ¶1.4.5 等级不可比较，表达式非良构。

只用 `float`、`double`、`long double` 时，这条规则就是向更宽的类型靠拢。后三条是 C++23 加入扩展浮点类型（[[P1467R9]]）时写的：浮点类型的等级按值集的包含关系排序，值集互不包含的两个类型等级不可比较。

| 操作数 | 结果类型 | 依据 |
|---|---|---|
| `float` + `double` | `double` | 等级 |
| `int` + `float` | `float` | ¶1.4.2，不管 `int` 的值能否精确表示 |
| `std::float16_t` + `float` | `float` | float16 的值集是 float 的真子集 |
| `std::float32_t` + `float`（值集相同） | `std::float32_t` | 等级相同，`std::floatN_t` 的子等级更高 |
| `std::float64_t` + `double`（值集相同） | `std::float64_t` | 同上 |
| `std::bfloat16_t` + `std::float16_t` | 非良构 | 一个范围大，一个精度高，等级不可比较 |

```cpp
#include <stdfloat>
auto a = std::float16_t(1) + 1.0f;                  // float
auto b = std::float32_t(1) + 1.0f;                  // std::float32_t
auto c = std::bfloat16_t(1) + std::float16_t(1);    // error: 等级不可比较
```

这个例子没有标判定：本机 libc++ 还没有提供 `<stdfloat>`，无法在本地验证，结论直接来自 [[conv.rank]] 和本节条文。

!!! pitfall "`int` + `float` 会丢精度"
    ¶1.4.2 无条件地把整数转换为浮点类型：`16777217 + 0.0f` 等于 `16777216.0f`，因为 `float` 只有 24 位有效数字。`long long` 与 `float` 混合运算时，损失更大。

### 第 5 步：两个整数

¶1.5 剩下的情况是两个操作数都是整数或无作用域枚举。先对每个操作数做**整型提升**（[[conv.prom]]），得到 `T1`、`T2`。这一项的脚注指出，提升之后 `bool`、`char8_t`、`char16_t`、`char32_t`、`wchar_t` 和枚举都已变成某个整数类型。然后按下面的顺序确定公共类型 `C`：

- ¶1.5.1 `T1`、`T2` 相同，`C` 就是这个类型。
- ¶1.5.2 两者同为有符号或同为无符号，`C` 是等级（[[conv.rank#1]]）较高的那个。
- ¶1.5.3 一个有符号（记为 `S`），一个无符号（记为 `U`）：
    - ¶1.5.3.1 `U` 的等级不低于 `S`，`C` 是 `U`；
    - ¶1.5.3.2 否则，如果 `S` 能表示 `U` 的全部值，`C` 是 `S`；
    - ¶1.5.3.3 否则，`C` 是 `S` 对应的无符号类型。

```text
           提升 → T1, T2
                │
      相同？ ── 是 ──→ C = T1
                │否
   同符号？ ── 是 ──→ C = 等级高者
                │否（S 与 U）
rank(U) ≥ rank(S)？ ── 是 ──→ C = U
                │否
S 能表示 U 全部值？ ── 是 ──→ C = S
                │否
                └──→ C = unsigned S
```

整数的位宽由实现决定，所以有些结果依赖平台。下表按 LP64（64 位 Linux 和 macOS：`int` 32 位，`long` 和 `long long` 64 位）给出：

| 操作数 | 提升后 | 规则 | 结果类型 |
|---|---|---|---|
| `short` + `short` | `int`, `int` | ¶1.5.1 | `int` |
| `unsigned short` + `int` | `int`, `int` | ¶1.5.1 | `int` |
| `char` + `bool` | `int`, `int` | ¶1.5.1 | `int` |
| `int` + `long` | 不变 | ¶1.5.2 | `long` |
| `int` + `unsigned` | 不变 | ¶1.5.3.1 | `unsigned` |
| `long` + `unsigned` | 不变 | ¶1.5.3.2：64 位 `long` 能表示所有 32 位 `unsigned` | `long` |
| `long` + `unsigned long` | 不变 | ¶1.5.3.1：等级相同 | `unsigned long` |
| `long long` + `unsigned long` | 不变 | ¶1.5.3.3 | `unsigned long long` |

```cpp ok
#include <type_traits>
template<class A, class B> using R = decltype(A{} + B{});
static_assert(std::is_same_v<R<short, short>, int>);
static_assert(std::is_same_v<R<unsigned short, int>, int>);
static_assert(std::is_same_v<R<int, unsigned>, unsigned>);
static_assert(std::is_same_v<R<unsigned long, long long>, unsigned long long>);
#if __SIZEOF_LONG__ == 8 && __SIZEOF_INT__ == 4
static_assert(std::is_same_v<R<long, unsigned>, long>);   // LP64：¶1.5.3.2
#endif
```

¶1.5.3.3 只在一种情况下用到：有符号类型的等级更高，却装不下无符号类型的全部值。LP64 上的 `long long` 与 `unsigned long` 正是如此。`unsigned long` 的等级等于 `long`，低于 `long long`，所以 ¶1.5.3.1 不适用；两者都是 64 位，`long long` 装不下 `unsigned long` 的全部值，¶1.5.3.2 也不适用。结果是第三个类型 `unsigned long long`。

## 有符号与无符号混合

¶1.5.3.1 是 C 和 C++ 里最常引发 bug 的规则之一：等级相同时，有符号类型转换为无符号类型。

```cpp run title="sign.cpp" ok
#include <cstdio>
#include <utility>
#include <vector>

int main() {
  std::printf("%d\n", -1 < 0u);                 // 0
  std::printf("%d\n", -1L < 0u);                // LP64 上 1，LLP64 上 0
  std::printf("%d\n", -1 < (unsigned short)0);  // 1

  std::vector<int> v;
  std::printf("%zu\n", v.size() - 1);           // 18446744073709551615

  std::printf("%d\n", std::cmp_less(-1, 0u));   // 1
}
```

第二行的结果依赖平台。LP64 上 `long` 是 64 位，能表示所有 `unsigned`，按 ¶1.5.3.2 在 `long` 中比较；Windows 的 LLP64 上 `long` 只有 32 位，按 ¶1.5.3.1 在 `unsigned long` 中比较，结果为 0。

第三行说明窄的无符号类型反而安全：`unsigned short` 先提升为有符号的 `int`，比较在 `int` 中进行。

第四行是容器下标的常见问题。`size()` 返回无符号类型，`v` 为空时 `v.size() - 1` 回绕成最大值，`for (int i = 0; i < v.size() - 1; ++i)` 会一直循环到越界访问。

GCC 和 Clang 的 `-Wsign-compare` 能发现大部分混合符号比较（GCC 在 C++ 的 `-Wall` 中开启，Clang 在 `-Wextra` 中开启），`-Wsign-conversion` 覆盖更多隐式转换。C++20 的 `<utility>` 提供 `std::cmp_less`、`std::cmp_equal` 等函数，按数学值比较不同符号的整数；`std::in_range<T>(x)` 检查 `x` 能否用 `T` 表示。

!!! pitfall "无符号的窄类型也会有符号溢出"
    `unsigned short a = 65535, b = 65535;` 之后计算 `a * b`，两个操作数先提升为 `int`，乘积 4294836225 超出 32 位 `int` 的范围，是有符号溢出，属于未定义行为（[[expr.pre]]）。UBSan 会报告 `signed integer overflow`。`uint16_t` 也是如此。安全的写法是 `1u * a * b` 或 `static_cast<unsigned>(a) * b`。

### 三路比较拒绝混合符号

`<=>` 在寻常算术转换之后还要求转换不是窄化（整数转浮点除外），否则非良构（[[expr.spaceship]]）。`int` 转 `unsigned` 是窄化，所以混合符号的三路比较直接报错：

```cpp error
#include <compare>
auto f(int i, unsigned u)        { return i <=> u; }  // error: int → unsigned 窄化
auto g(unsigned short a, int b)  { return a <=> b; }  // OK：提升后都是 int
auto h(long long a, unsigned b)  { return a <=> b; }  // OK：unsigned → long long 不窄化
```

!!! impl
    寻常算术转换完全在编译期决定，不产生运行时检查。它影响的是生成什么指令：`int` 的溢出是 UB 而 `unsigned` 会回绕，所以用 `int` 做循环下标时，编译器可以把它直接加宽成 64 位地址偏移；用 `unsigned` 时必须保留 32 位回绕的语义，有时会多出零扩展指令。

## 历史

!!! history
    整数部分的规则沿袭 C。ANSI C 在无符号保持（unsigned-preserving）和值保持（value-preserving）两种提升方案之间选择了后者，所以 `unsigned short` 提升为 `int` 而不是 `unsigned int`。C++11 加入 `long long` 时，规则改用整数转换等级（[[conv.rank]]）表述，以容纳扩展整数类型。C++20 弃用枚举与不同枚举、枚举与浮点的混合运算，并让 `<=>` 拒绝窄化；C++23 加入扩展浮点类型和浮点子等级；C++26 删除了被弃用的枚举运算。

## 思考题

!!! question "1. 在 LP64 平台上，`unsigned long` 与 `long long` 相加的结果是什么类型？"

<details markdown="1">
<summary>答案</summary>

`unsigned long long`。提升后类型不变，符号不同，`U` 是 `unsigned long`，`S` 是 `long long`。`unsigned long` 的等级等于 `long`，低于 `long long`，¶1.5.3.1 不适用；64 位的 `long long` 不能表示 64 位 `unsigned long` 的全部值，¶1.5.3.2 也不适用。按 ¶1.5.3.3，取 `long long` 对应的无符号类型。
</details>

!!! question "2. `enum E { a }; enum F { b };` 中 `a == b` 在 C++26 非良构。`a == +b` 和 `static_cast<E>(b) == a` 呢？"

<details markdown="1">
<summary>答案</summary>

都良构。一元 `+` 对 `b` 做整型提升，`+b` 是 `int`，于是 `a == +b` 是枚举与整数的组合，不触发 ¶1.3。`static_cast<E>(b) == a` 的两个操作数是同一个枚举类型，同样不触发 ¶1.3，两者提升为 `int` 后比较。
</details>

!!! question "3. `char c = 'a'; auto d = c + c;` 中 `d` 是什么类型？`char` 有无符号会影响这个类型吗？"

<details markdown="1">
<summary>答案</summary>

`d` 是 `int`。只要 `int` 比 `char` 宽，无论 `char` 有无符号，`int` 都能表示 `char` 的全部值，按 [[conv.prom#2]] 总是提升为 `int`，再按 ¶1.5.1 得到 `int`。`char` 有无符号只影响值（`'\xff'` 是 -1 还是 255），不影响类型。
</details>
