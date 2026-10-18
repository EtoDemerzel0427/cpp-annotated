---
title: 乘性运算符
summary: "* / % 的操作数类型与常用算术转换；整数除法向零截断（C++11 起）与余数的符号；除以零、INT_MIN / -1 与 INT_MIN % -1 的 UB；整数提升带来的隐蔽溢出"
status: done
related: expr.arith.conv, conv.prom, expr.pre, basic.fundamental, expr.shift, expr.add, expr.const.core
tags: 算术, 整数, UB
updated: 2026-10-17
---

乘性运算符 `*`、`/`、`%` 是最简单的一类运算符，本节也只有四段。但 C++ 整数算术的陷阱几乎都集中在这里：常用算术转换会悄悄把操作数改成别的类型，有符号溢出是 UB，除以零是 UB，负数除法的舍入方向曾经由实现定义，还有初学者想不到的 `INT_MIN / -1`。本节与 [[expr.add]]、[[expr.shift]] 一起，完整回答了整数运算何时有定义；其背后的总原则是 [[expr.pre#4]]：结果在数学上无定义或不在结果类型的可表示范围内时，行为未定义。

## 文法与结合性（¶1）

¶1 `*`、`/`、`%` 同属一级，从左往右结合：`a * b / c` 是 `(a * b) / c`，`a / b * c` 是 `(a / b) * c`。在整数运算里，这一点会影响结果：

```cpp run title="mul-assoc.cpp" ok
int main() {
    int a = 7, b = 2, c = 3;
    int x = a / b * c;     // (7 / 2) * 3 = 3 * 3 = 9
    int y = a * c / b;     // (7 * 3) / 2 = 21 / 2 = 10
    return (x == 9 && y == 10) ? 0 : 1;
}
```

先乘后除精度更高，但更容易溢出；先除后乘不易溢出，但丢精度。编译器不能替你重排，因为整数乘除不满足结合律，而且重排可能改变是否溢出。

乘性表达式的操作数是 *pm-expression*（[[expr.mptr.oper]]），所以 `a * s.*pm` 是 `a * (s.*pm)`。

## 操作数类型（¶2）

¶2 规定：

- `*` 和 `/` 的操作数必须是算术类型或无作用域枚举类型；
- `%` 的操作数必须是整型或无作用域枚举类型，浮点数没有 `%`，要用 `std::fmod`；
- 操作数要经过**常用算术转换**（usual arithmetic conversions，[[expr.arith.conv]]），转换后的公共类型就是结果类型。

```cpp title="mul-types.cpp" error
enum class Color { red, green };
enum E1 { e1 };
enum E2 { e2 };

auto a = 5.0 % 2;           // error: % 不接受浮点
auto b = Color::red * 2;    // error: 有作用域枚举不参与算术
auto c = e1 * e2;           // error: 两个不同枚举类型（C++26 起非良构）
auto d = e1 * 2.0;          // error: 枚举与浮点混合（C++26 起非良构）
```

最后两行在 C++20/23 中只是弃用，C++26 由 [[P2864R2]] 改为非良构（见 [[diff.cpp23.expr]]、[[expr.arith.conv]]）。同一个无作用域枚举与整数混用（`e1 * 2`）仍然合法，枚举先经整数提升。

### 整数提升的隐患

常用算术转换的第一步是**整数提升**（[[conv.prom]]）：比 `int` 窄的类型（`char`、`short`、`unsigned short`、`bool`……）先提升为 `int`（若 `int` 能表示其全部值）。由此产生了一个经典 UB：两个 `unsigned short` 相乘，实际执行的却是有符号的 `int` 乘法：

```cpp run title="mul-promotion-ub.cpp" ub flags="-std=c++2c -O0 -fsanitize=undefined"
int main() {
    unsigned short a = 65535;
    unsigned short b = 65535;
    unsigned r = a * b;   // UB: a、b 提升为 int，65535 * 65535 超出 int 范围（int 为 32 位时）
    return r == 0;
}
```

程序员以为是无符号运算（无符号绕回有定义，[[basic.fundamental]]），实际却是有符号溢出。UBSan 的报告是 "signed integer overflow: 65535 * 65535 cannot be represented in type 'int'"。修正方法是在运算前显式转换：`unsigned(a) * b`。`uint16_t`、`uint8_t` 的乘法在 32 位 `int` 平台上都有同样问题。

## 乘法（¶3）

¶3 二元 `*` 表示乘法，标准对此没有更多规定。越界的情况统一由 [[expr.pre#4]] 处理：`*`、`/`、`%` 都是**算术表达式**（arithmetic expression），如果数学结果既不在结果类型的可表示范围内，也不是该类型所拥有的 ±∞ 或 NaN，行为未定义。

- **有符号整数**：结果超出范围 → {{ub}}。C++20 起整数采用二进制补码表示（[[basic.fundamental]]），但这并没有让有符号溢出变得有定义。C++20 只规定了表示方式和转换的结果，**算术溢出仍是 UB**；
- **无符号整数**：按模 2<sup>N</sup> 运算，数学结果本身就被定义为模意义下的值，永不溢出（[[basic.fundamental]]）；
- **浮点**：若类型遵循 IEC 60559，溢出按 IEEE 规则得到 ±∞。这是该类型拥有的值，所以不是 UB。[[expr.pre#4]] 的注释明确指出，对这样的类型，**除以零是算术表达式唯一的 UB 情形**。但有定义不等于是常量：有限操作数产生非有限结果（如 `max * 2`、`inf * 0`）的表达式不是核心常量表达式（[[expr.const.core]]）。

## 除法与取余（¶4）

### 除以零

!!! std
    If the second operand of / or % is zero, the behavior is undefined.

    `/` 或 `%` 的第二操作数为零时，行为未定义。

这条规则**对浮点除法同样成立**。即使类型遵循 IEC 60559（`std::numeric_limits<double>::is_iec559` 为 `true`），除以零也仍然是 UB，这是浮点算术中唯一保留下来的 UB（[[expr.pre#4]] 注 4）。实践中硬件会得到 ∞ 或 NaN，主流编译器在运行期给出的也是这个结果；但在常量求值中，除以零使表达式不再是常量表达式（[[expr.const.core]] 排除了一切 UB），所以下面两个都会被拒绝：

```cpp title="mul-div-zero-const.cpp" error
constexpr double x = 1.0 / 0.0;   // error: 不是常量表达式（除以零）
constexpr int    y = 5 % 0;       // error: 不是常量表达式（除以零）
```

运行期的浮点除以零不在 `-fsanitize=undefined` 的默认检查集合中，需要显式加 `-fsanitize=float-divide-by-zero`。这恰好反映了现实情况：标准说它是 UB，而实现按 IEEE 给了它定义。

### 向零截断

!!! std
    For integral operands, the / operator yields the algebraic quotient with any fractional part discarded;

    对整型操作数，`/` 得到代数商并丢弃小数部分。

丢弃小数部分就是**向零截断**（[[g:truncation-toward-zero]]，标准脚注也这样称呼）：`7 / 2 == 3`、`-7 / 2 == -3`（而不是向下取整的 `-4`）。

### 余数的符号

¶4 接着用一个恒等式定义 `%`：若商 `a/b` 在结果类型中可表示，则

> `(a/b)*b + a%b == a`

由向零截断和这个恒等式可以直接推出：**余数的符号与被除数 `a` 相同**（或为零），与除数 `b` 的符号无关。

```cpp run title="mul-sign.cpp" ok
static_assert( 7 /  2 ==  3 &&  7 %  2 ==  1);
static_assert(-7 /  2 == -3 && -7 %  2 == -1);   // 余数随被除数为负
static_assert( 7 / -2 == -3 &&  7 % -2 ==  1);   // 除数的符号不影响余数的符号
static_assert(-7 / -2 ==  3 && -7 % -2 == -1);

int main() {}
```

由此产生一个常见 bug：用 `x % 2 == 1` 判断奇数，对负奇数不成立（`-3 % 2 == -1`）。正确写法是 `x % 2 != 0`。需要数学意义上的非负模（如环形缓冲区下标、日期计算）时，要自己修正：`((a % n) + n) % n`。

!!! history "C++11 之前：舍入方向由实现定义"
    C++98/03 只规定两个操作数都非负时余数非负；其他情况下余数的符号由实现定义（标准脚注建议采用 Fortran 式的向零截断）。C99 率先把向零截断写成硬性规定，C++11 随之跟进，形成今天的措辞。当时几乎所有硬件的除法指令本来就向零截断，所以这次改动几乎没有破坏任何实际代码，却让 `%` 的行为从大体可移植变成了有保证的可移植。

### `INT_MIN / -1` 与 `INT_MIN % -1`

¶4 最后一句规定，若商不可表示，`a/b` 和 `a%b` 的行为都未定义。对二进制补码的 `int`，唯一的情形就是 `INT_MIN / -1`：数学结果是 2<sup>31</sup>，比 `INT_MAX` 大 1。

```cpp title="mul-intmin.cpp" error
#include <climits>

constexpr int q = INT_MIN / -1;   // error: 不是常量表达式（商不可表示，UB）
constexpr int r = INT_MIN % -1;   // error: 不是常量表达式（同样是 UB）
```

`INT_MIN % -1` 的数学值明明是 0，完全可以表示，为什么也是 UB？因为标准以商可表示为前提来定义 `%`，商不可表示时，恒等式就无从谈起。这样规定的实际动机来自硬件：x86 的 `idiv` 指令同时产生商和余数，商溢出时触发 #DE 异常（与除以零是同一个异常），进程收到 `SIGFPE` 崩溃。如果标准要求 `INT_MIN % -1 == 0`，编译器就必须在每个可能为 `-1` 的除数前插入分支。把它定为 UB，编译器就可以直接发出一条 `idiv`。

!!! impl "实现视角"
    - **x86/x86-64**：`idiv` 在除数为 0 或商溢出时都触发 #DE，在 Linux 上表现为 `SIGFPE`（"Floating point exception"，尽管与浮点无关）。`INT_MIN / -1` 和 `INT_MIN % -1` 在运行期通常就是这样崩溃的。
    - **AArch64**：`sdiv` 不陷入，除以零得 0，`INT_MIN / -1` 得 `INT_MIN`。同样的 UB 程序在 ARM 上不崩溃，而是给出错误结果，可见 UB 的后果确实因平台而异。
    - **除以常量**：编译器把 `x / 10` 变成乘以一个特定常数再移位（参见 Granlund–Montgomery 的经典方法），因为乘法远比除法快。有符号数除以 2 的幂时不能直接算术右移（右移向负无穷舍入，见 [[expr.shift]]），编译器会先给负数加上 `2^k - 1` 的偏置再移位。这就是 `x / 2` 对 `int` 比对 `unsigned` 多出几条指令的原因。
    - **UBSan**：`-fsanitize=signed-integer-overflow`、`integer-divide-by-zero` 默认包含在 `undefined` 中；`float-divide-by-zero` 需要单独开启。

## 陷阱

!!! pitfall "以为 `%` 是数学模运算"
    C++ 的 `%` 是截断取余，结果符号随被除数。`-1 % 5 == -1`，不是 4。

!!! pitfall "以为窄无符号类型的乘法不会溢出"
    `uint16_t * uint16_t` 是 `int * int`。乘积超过 `INT_MAX` 就是 UB。

!!! pitfall "以为 C++20 的二进制补码让溢出有定义了"
    C++20 规定的是有符号整数的表示和转换，算术溢出仍然是 UB；`INT_MIN / -1` 也仍然是 UB。

!!! pitfall "以为浮点除以零一定得到 ∞"
    那是 IEEE 754 的保证，不是 C++ 标准的保证。对 IEC 60559 类型，浮点溢出到 ∞ 有定义，浮点除以零却仍是 UB。在要求常量表达式的地方，它会直接使程序非良构。

## 思考题

!!! question "思考题 1"
    设 `int` 为 32 位。`long long x = INT_MIN; x / -1` 有定义吗？`INT_MIN / -1LL` 呢？`INT_MIN / -1u` 呢？

<details markdown="1">
<summary>答案</summary>

- `x / -1`：`x` 是 `long long`，`-1` 经常用算术转换变为 `long long`，商 2<sup>31</sup> 在 `long long` 中可表示 → 有定义，结果 2147483648。
- `INT_MIN / -1LL`：同理，`INT_MIN` 转换为 `long long` → 有定义。
- `INT_MIN / -1u`：`-1u` 是 `unsigned int`（值 4294967295），常用算术转换把 `INT_MIN` 转为 `unsigned int`（值 2147483648），无符号除法 `2147483648 / 4294967295 == 0`。有定义，但结果是 0，大概不是你想要的。
</details>

!!! question "思考题 2"
    为什么标准不干脆把 `a % b` 定义为与 `b` 同号的数学模（像 Python 那样）？

<details markdown="1">
<summary>答案</summary>

因为主流硬件的除法指令（x86 `idiv`、ARM `sdiv` 等）都是向零截断的，余数自然与被除数同号。若语言要求向下取整（floor division），每次有符号除法后都要额外判断符号并修正，多出分支或几条指令。C 和 C++ 选择直接映射硬件，把需要数学模的场合留给程序员显式修正。Python 等语言把正确性和直观性放在性能之前，选择了 floor division。
</details>

## 小结

| 情形 | 结果 | 依据 |
|---|---|---|
| `%` 用于浮点、有作用域枚举 | {{ill-formed}} | ¶2 |
| 不同枚举之间、枚举与浮点混合 | {{ill-formed}}（C++26；之前弃用） | ¶2、[[expr.arith.conv]] |
| 除数为零（整数或浮点） | {{ub}} | ¶4 |
| 整数除法 | 向零截断（C++11 起保证） | ¶4 |
| 余数符号 | 与被除数相同 | ¶4 恒等式 |
| `INT_MIN / -1`、`INT_MIN % -1` | {{ub}}（商不可表示） | ¶4 |
| 有符号乘法溢出 | {{ub}} | [[expr.pre#4]] |
| IEC 60559 浮点溢出 | ±∞，有定义（但非常量） | [[expr.pre#4]] |
| 无符号乘法 | 模 2<sup>N</sup> | [[basic.fundamental]] |
