---
title: 表达式序言
summary: 重载运算符与内置运算符的关系；算术表达式的数学结果不可表示时行为未定义（有符号溢出是 UB 的出处）；实现何时可以重组运算；浮点的超额精度。
status: draft
related: expr, intro.execution, expr.mul, over.match.oper, basic.fundamental, expr.const.core
tags: 表达式, UB, 运算符重载, 浮点
updated: 2026-10-19
---

!!! tldr
    - 重载的运算符沿用内置运算符的语法和求值顺序，但操作数要求按函数调用处理；重载的 `&&`、`||` 不短路。
    - 不能为内置类型重新定义运算符，但内置运算符作为候选参与重载决议。
    - 一元 `+`、`-` 和加减乘除余，只要数学结果在类型里表示不了，就是 UB：有符号溢出是 UB，无符号运算按模进行、不会溢出，IEEE 浮点只有除以零是 UB。
    - 常量求值更严格：有限的操作数不能算出 ∞ 或 NaN。
    - 只有运算真正满足结合律时实现才能重组它；浮点中间结果可以有超额精度，但强制转换和赋值必须舍入。

## 什么是表达式（¶1）

¶1 的注 1 给出了直观的说法：表达式是运算符和操作数组成的序列，规定了一项计算，可以产生一个值，也可以产生副作用。两者都不是必须的：`void` 函数的调用没有值，`1 + 2` 没有副作用。

表达式是一个语法结构，它的类型和值类别是编译期就确定的静态性质（[[expr.prop]]）。**求值**（evaluation）则是运行时（或常量求值时）的动作，包括计算值和引发副作用（[[intro.execution]]）。

## 重载运算符遵守什么（¶2）

```cpp run title="seq.cpp" ok
#include <iostream>

int main() {
    int i = 0;
    std::cout << i++ << ' ' << i++ << '\n';  // C++17 起保证输出 "0 1"
}
```

¶2 的注 2 说明：类类型或枚举类型的操作数可以使用重载的运算符，这时表达式按 [[over.oper]] 改写成函数调用。改写后有些规则保留，有些不保留：

| 方面 | 重载运算符 |
|---|---|
| 语法（优先级、结合性、操作数个数） | 与内置运算符相同 |
| 求值顺序 | 与内置运算符相同（[[over.match.oper#2]]） |
| 对操作数类型和值类别的要求 | 改由函数调用的规则决定，看形参类型 |
| 运算符之间的关系，如 `++a` 等价于 `a += 1` | 不保证 |

求值顺序相同是 C++17 的变化。在那之前，`a << b` 改写为 `operator<<(a, b)` 后，两个实参谁先求值是未指定的，`std::cout << i++ << i++` 是 UB。C++17 规定内置 `<<` 的左操作数先于右操作数求值，重载版本也沿用这个顺序，于是上例保证输出 `0 1`。

顺序相同不等于短路行为相同。重载的 `&&`、`||` 是普通的函数调用，两个操作数都会求值：

```cpp run title="no-short-circuit.cpp" ok
#include <cstdio>

struct B { bool v; };
B operator&&(B a, B b) { return {a.v && b.v}; }

B noisy(bool v) { std::puts("evaluated"); return {v}; }

int main() {
    B r = B{false} && noisy(true);   // 仍然打印 "evaluated"
    return r.v;
}
```

对操作数的要求改由函数调用决定，例子是赋值。内置 `=` 要求左操作数是可修改的左值（[[expr.assign]]），而类的 `operator=` 是普通成员函数，所以 `std::string() = "x"` 是合法的：在一个纯右值上调用成员函数，临时对象被实质化（[[conv.rval]]）。

## 内置运算符不能改写，但参与重载决议（¶3）

¶3 [[expr.compound]] 描述的是运算符作用于没有重载它的类型时的效果。运算符重载不能修改**内置运算符**（built-in operator）的规则，也就是不能为两个 `int` 重新定义 `+`。具体的保证在 [[over.oper]]：运算符函数至少要有一个类类型或枚举类型的形参。

```cpp run error
int operator+(int, int);   // error: 至少要有一个类或枚举类型的形参
```

不过内置运算符会参与重载决议。[[over.built]] 为每个运算符列出了一组假想的内置候选函数，例如 `operator+(double, double)`。类类型的操作数如果能经用户定义转换变成 `double`，内置候选就可能被选中；这时先对操作数施行用户定义转换，再按 [[expr.compound]] 的内置规则继续。

```cpp run ok
struct Meters {
    double v;
    operator double() const { return v; }   // 非 explicit 转换函数
};

double total(Meters a, Meters b) {
    return a + b;    // 选中内置候选 operator+(double, double)，
                     // 两个操作数先经 Meters::operator double() 转换
}
```

!!! note
    这也是给类加一个隐式 `operator bool` 会带来许多意外的原因：`a + b`、`a < 1` 这样的表达式都可能经由内置候选变得合法。C++11 的 `explicit operator bool` 只在按语境转换为 `bool` 的场合（`if` 的条件、`!`、`&&` 等）起作用（[[conv#4]]），避免了这个问题。

## 算术表达式的 UB（¶4）

```cpp run title="overflow.cpp" ub
#include <climits>
#include <cstdio>

int main(int argc, char**) {
    int big = INT_MAX - 1 + argc;    // argc == 1 时为 INT_MAX
    unsigned u = UINT_MAX;
    u = u + 1;                       // OK：无符号按模运算，u == 0
    int bad = big + 1;               // UB：INT_MAX + 1 不可表示
    int q = INT_MIN / -argc;         // UB：2^31 不可表示（argc == 1）
    std::printf("%u %d %d\n", u, bad, q);
}
```

本机加 `-fsanitize=undefined` 运行，UBSan 在两处 UB 分别报告 signed integer overflow 和 "division of -2147483648 by -1 cannot be represented"。依据是 ¶4。

¶4 先定义**算术表达式**（[[g:arithmetic-expression|arithmetic expression]]）：一元 `+`、`-`（[[expr.unary.op]]），加法和减法（[[expr.add]]），乘法、除法和取余（[[expr.mul]]），并且每个操作数（可能经过转换后）都是算术类型。所以：

- 指针算术 `p + 1` 不是算术表达式，它的 UB 由 [[expr.add]] 单独规定。
- 移位 `<<`、`>>` 不在其中，负的移位量、移位量不小于宽度这些 UB 由 [[expr.shift]] 规定。
- 复合赋值 `+=` 和自增 `++` 本身不是算术表达式，但它们是用算术表达式定义的（注 3），所以同样受这条规则约束。

然后是规则本身：

!!! std
    The behavior of evaluating an arithmetic expression is undefined if the mathematical result is neither in the range of representable values for its type nor a negative infinity, positive infinity, or NaN that is among the values of the type.

也就是说，数学结果既不在类型的可表示范围内，也不是该类型拥有的 ±∞ 或 NaN 时，行为未定义。按类型看：

| 类型 | 情况 | 结论 |
|---|---|---|
| 有符号整数 | 数学结果超出 `[min, max]` | {{ub}}，这就是有符号溢出 |
| 无符号整数 | 运算本身按模 2<sup>N</sup> 定义（[[basic.fundamental#2]]） | 结果总在范围内，不会溢出 |
| IEEE 754 浮点 | 溢出舍入为 ±∞，非法运算得到 NaN，这些都是类型里的值 | 只有除以零是 UB（注 4） |
| 不符合 IEEE 的浮点 | 溢出 | {{ub}} |
| 任何类型 | 除数为零 | {{ub}}，由 [[expr.mul#4]] 单独规定 |

!!! ub "有符号溢出为什么是 UB 而不是回绕"
    C++20 起有符号整数必须用二进制补码表示（[[basic.fundamental]]），但溢出仍然是 UB，这是有意保留的。编译器可以据此假设 `i + 1 > i` 恒为真，可以把 `int` 循环变量扩展成 64 位下标而不必模拟 32 位回绕，还能做强度削减和向量化。需要回绕语义时用无符号类型；需要饱和语义时用 `<numeric>` 中的 `std::saturating_add` 等函数。

### IEEE 浮点与常量表达式（注 4）

注 4 指出，如果操作数类型符合 ISO/IEC 60559（即 IEEE 754），除以零是算术表达式唯一的 UB 情形；但有些在运行时有定义的浮点表达式不是核心常量表达式。[[expr.const.core#2.9]] 把下面三种排除在常量表达式之外：

- 所有操作数有限，结果却不是有限值（溢出到 ∞）；
- 有操作数是 signaling NaN；
- 没有操作数是 NaN，结果却是 NaN（如 `inf * 0`、`inf - inf`）。

换句话说，运行时可以得到 ∞ 和 NaN，编译期却不能凭空产生它们；已有的 ∞ 和 quiet NaN 可以参与运算并传播。下面改编自标准的例 1，标准用 `std::float32_t`，这里换成 `double` 并假设它符合 IEEE binary64：

```cpp
#include <limits>
constexpr double mx  = std::numeric_limits<double>::max();
constexpr double inf = std::numeric_limits<double>::infinity();
constexpr double nan = std::numeric_limits<double>::quiet_NaN();

constexpr double inf2 = inf * 2;   // OK：∞ 的传播
constexpr double nan2 = nan * 2;   // OK：NaN 的传播（Clang 拒绝，见下）
constexpr double tiny = std::numeric_limits<double>::min() / mx;  // OK：下溢舍入为 0
constexpr double oflo = mx * 2;    // error: 有限操作数得到非有限结果（Clang 接受，见下）
constexpr double udef = inf * 0;   // error: 没有 NaN 操作数却得到 NaN
constexpr double div0 = mx / 0;    // error: 除以零是 UB
```

!!! impl "Clang 与标准的分歧"
    本机 Clang 23 对这个例子有两处与标准不同：它拒绝 `nan2`，把有 NaN 参与的运算一律视为非常量；又接受 `oflo`，允许常量求值溢出到 ∞。`udef` 和 `div0` 则都被拒绝。这是较新的标准措辞与实现之间的差距，写编译期浮点代码时不要依赖这些边界情况。

注 5 提醒，除以零、以零为除数取余以及各种浮点异常的处理因机器而异，有时可以通过库函数调整，例如 `<cfenv>` 的浮点环境。

## 重组运算的限制（¶5）

```cpp run title="assoc.cpp" ok
#include <cstdio>
int main() {
    double a = 1e16, b = -1e16, c = 1.0;
    std::printf("%g %g\n", (a + b) + c, a + (b + c));  // 打印 "1 0"
}
```

¶5 的注 6 说明，只有运算真正满足结合律或交换律时，实现才能按数学规则重组它们。标准的例子是 `a = a + 32760 + b + 5;`：在溢出会触发异常、`int` 范围是 [-32768, 32767] 的机器上，它必须按 `((a + 32760) + b) + 5` 计算，不能改写成 `(a + b) + 32765`，因为原表达式不溢出时，改写后的可能溢出。在溢出不触发异常、结果可逆的机器上，这些改写都是允许的，因为结果相同。这正是 as-if 规则（[[intro.abstract]]）的体现。脚注 34 补充，实现永远不能假定重载运算符满足结合律或交换律。

这一段最实用的推论是：浮点加法不满足结合律，所以编译器在默认模式下不能把 `(a + b) + c` 改成 `a + (b + c)`，也就不能自动向量化浮点求和。GCC 和 Clang 的 `-ffast-math`（具体是其中的 `-fassociative-math`）就是让编译器放弃这项保证。

## 浮点超额精度（¶6）

¶6 浮点操作数的值和浮点表达式的结果，可以用比类型要求更高的精度和范围表示，类型并不因此改变。这是为 x87 这样寄存器是 80 位扩展精度的硬件准备的：`float` 运算可以在 80 位寄存器里完成，中间结果不必每次舍入到 `float`。

脚注 35 补充，强制转换和赋值仍然必须执行它们规定的转换。所以写 `(float)x`、`static_cast<double>(e)` 或赋值给变量时，多余的精度必须丢掉，程序员可以借此强制舍入。

!!! impl "实现视角"
    - 现代 x86-64 默认用 SSE2 做标量浮点运算，`FLT_EVAL_METHOD` 为 0，基本不存在超额精度；32 位 x86 使用 x87 时，`FLT_EVAL_METHOD` 通常为 2。
    - GCC 在 x87 上默认并不严格遵守赋值时丢弃超额精度的要求，需要 `-ffloat-store` 或 `-fexcess-precision=standard`。
    - 把 `a * b + c` 融合成一条 FMA 指令（浮点收缩，contraction）通常也被视为利用了这项自由，Clang 用 `-ffp-contract=` 控制它。

## 历史与演进

!!! history
    - 旧措辞是：表达式求值过程中，如果结果在数学上没有定义或者不在其类型的可表示范围内，行为未定义。这句话适用于一切表达式，范围宽泛，也没有说清浮点 ∞ 和 NaN 的地位。当前草案改为只针对算术表达式，并明确承认 ±∞ 和 NaN；同时 [[expr.const.core]] 补上了非有限结果不是常量表达式的规则。
    - C++17 的 [[P0145R3]] 细化了求值顺序，并规定重载运算符沿用对应内置运算符的顺序，使 `std::cout << i++ << i++` 有了确定的结果。
    - C++20 规定有符号整数用二进制补码表示（[[P1236R1]]），但溢出仍然是 UB。

## 常见误解

!!! pitfall "只用无符号类型就不会溢出"
    `unsigned short a = 65535, b = 65535; auto c = a * b;` 中，两个操作数先经整型提升变成 `int`（[[conv.prom]]），乘积 4294836225 超出 32 位 `int` 的范围，这是有符号溢出，是 UB，尽管源码里一个有符号类型都没写。本机 UBSan 报告 "65535 * 65535 cannot be represented in type 'int'"。写成 `1u * a * b` 才安全。

!!! pitfall "先加再检查是否溢出"
    对有符号的 `x`，`if (x + 1 < x) handle_overflow();` 没有用。溢出本身就是 UB，编译器可以假设它不发生，把条件折叠为 `false`。应当先比较，例如 `if (x == INT_MAX)`，或者用 `__builtin_add_overflow`、`std::saturating_add`。

## 思考题

!!! question "思考题 1"
    `-INT_MIN` 是 UB 吗？`0u - 1` 呢？

<details markdown="1">
<summary>答案</summary>

`-INT_MIN` 是 UB。一元 `-` 是算术表达式（¶4.1），数学结果 2<sup>31</sup> 不能用 `int` 表示。顺带一提，`-2147483648` 是一元负号作用于字面量 2147483648，在 32 位 `int` 的平台上这个字面量的类型是 `long` 或 `long long`，所以这个表达式反而没有问题。

`0u - 1` 有定义。寻常算术转换后两个操作数都是 `unsigned`，无符号运算按模 2<sup>N</sup> 进行，结果是 `UINT_MAX`。
</details>

!!! question "思考题 2"
    在浮点类型符合 IEEE 754 的实现上，`double d = 1e308 * 10;` 在运行时是 UB 吗？写成 `constexpr double d = 1e308 * 10;` 呢？

<details markdown="1">
<summary>答案</summary>

运行时不是 UB。IEEE 类型的值包括 +∞，结果舍入为 +∞；按注 4，只有除以零是 UB。

写成 `constexpr` 时，按标准是非良构的：所有操作数有限而结果不是有限值，不是核心常量表达式（[[expr.const.core#2.9]]）。本机 Clang 23 实际上接受这种写法，见上文的实现说明。
</details>

!!! question "思考题 3"
    为什么 C++17 保证 `std::cout << f() << g();` 先调用 `f` 再调用 `g`，而 `h(f(), g())` 不保证？

<details markdown="1">
<summary>答案</summary>

`std::cout << f() << g()` 解析为 `(std::cout << f()) << g()`，改写为 `operator<<(operator<<(std::cout, f()), g())`。C++17 规定内置 `<<` 的左操作数先于右操作数求值，[[over.match.oper#2]] 又要求重载运算符的操作数按内置运算符的顺序求值，所以包含 `f()` 的左操作数先于 `g()` 求值。

`h(f(), g())` 是普通函数调用。[[expr.call]] 只规定各形参的初始化之间不确定定序（indeterminately sequenced），即一定一前一后，但不规定谁先。
</details>

## 小结

!!! summary
    - 重载运算符的语法和求值顺序与内置运算符相同，对操作数的要求和运算符间的恒等关系则不同；重载的 `&&`、`||` 不短路。
    - 内置运算符不能重新定义，但作为 [[over.built]] 的候选参与重载决议。
    - 算术表达式的数学结果不可表示即为 UB：有符号溢出是 UB，无符号运算不会溢出，IEEE 浮点只有除以零是 UB。
    - 常量求值更严格：有限的操作数不能算出 ∞ 或 NaN。
    - 只有运算真正满足结合律时才能重组；浮点可以有超额精度，但强制转换和赋值必须舍入。
