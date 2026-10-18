---
title: 复数
summary: std::complex<T> 的完整合同——只对浮点类型有定义、平凡可复制的字面类型、与 T[2] 的布局兼容保证；按浮点转换秩决定 explicit 的转换构造；成员与非成员运算、norm 是模的平方、polar 的前置条件；超越函数的分支切割与 C 函数的对应、pow(0,0) 实现定义；额外重载的提升规则；C++26 的元组接口与 constexpr 化；结果在数学上无定义即 UB
status: done
covers: *
papers: P1467R9, P2819R2, P1383R2
related: numerics, numeric.requirements, c.math, basic.fundamental, conv.rank, basic.lval, dcl.struct.bind, tuple.like, over.lit
tags: 标准库, complex, 浮点, 结构化绑定, 布局
updated: 2026-10-18
---

`std::complex<T>` 是标准库里最"老"的数值类型之一（C++98 就有），但它的规范在 C++20 之后一直在变：C++20 把算术运算变成 `constexpr`，C++23 让它支持扩展浮点类型并用浮点转换秩重写了转换规则，C++26 加上了元组接口，并把超越函数也标成了 `constexpr`。

读本节需要的背景：浮点类型与**浮点转换秩**（[[basic.fundamental]]、[[conv.rank]]，[[g:floating-point-conversion-rank]]），以及类型别名访问规则（[[basic.lval]]）——后者解释了为什么 ¶4 的布局保证是一条**额外**的承诺。

本节的子条款：

| 子条款 | 内容 |
|---|---|
| [complex.numbers.general] | 允许的 `T`、UB 条件、与数组的布局兼容 |
| [complex.syn] | 概要 |
| [complex]、[complex.members]、[complex.member.ops] | 类模板与成员 |
| [complex.ops]、[complex.value.ops] | 非成员运算、`abs`/`arg`/`norm`/`conj`/`proj`/`polar` |
| [complex.transcendentals] | `exp`、`log`、`pow`、`sqrt`、三角与双曲函数 |
| [complex.tuple] | `tuple_size`/`tuple_element`/`get` {{c++26}} |
| [cmplx.over] | 对算术类型实参的额外重载 |
| [complex.literals] | `i`、`il`、`if` 后缀 |

## 允许的元素类型（[complex.numbers.general] ¶1–¶2）

¶2 有两句：

1. 用**不是** cv 非限定浮点类型的类型实例化 `complex` 主模板，效果**未指明**（{{unspec}}）。
2. `complex` 对 cv 非限定浮点类型的特化是**平凡可复制**的**字面类型**（[[basic.types.general]]）。

第一句比 [[numeric.requirements]] 的"数值类型"要求更窄：`int` 是数值类型，但 `complex<int>` 仍然没有保证。"未指明"而不是"非良构"意味着实现可以让它编译通过——本机 libc++ 上 `complex<int>` 的乘法就能编译——但 `abs`、`exp` 等函数对整数分量的结果没有任何规定，不要用。

"浮点类型"包括扩展浮点类型（[[basic.extended.fp]]）。C++23 以前，标准只有 `float`/`double`/`long double` 三个显式特化；[[P1467R9]] 把它改成"所有浮点类型"，并用浮点转换秩重写了转换构造函数的 `explicit` 条件（见下文）。

第二句给出两个实用保证：`complex<double>` 可以 `memcpy`、可以用 `bit_cast`；可以在常量表达式里构造和运算。

```cpp run title="complex-literal-type.cpp" ok
#include <complex>
#include <type_traits>

static_assert(std::is_trivially_copyable_v<std::complex<double>>);
constexpr std::complex<double> z{3, 4};
constexpr auto w = z * z + std::conj(z);          // C++20 起算术运算是 constexpr
static_assert(w.real() == -4 && w.imag() == 20);   // (3+4i)^2 + (3-4i) = -7+24i + 3-4i
static_assert(std::norm(z) == 25);                  // norm 是模的平方
```

## 结果在数学上无定义 → UB（¶3）

!!! std
    If the result of a function is not mathematically defined or not in the range of representable values for its type, the behavior is undefined.

    函数的结果在数学上无定义、或不在其类型的可表示范围内时，行为未定义。

这条规则对 `<complex>` 的**所有**函数生效，包括 `operator/`。它比核心语言更严格：当前草案的 [[expr.pre#4]] 对内建浮点运算豁免了"结果是该类型拥有的无穷或 NaN"的情况，而本条没有这层豁免。于是 `complex<double>(1, 0) / complex<double>(0, 0)` 在标准意义上是 UB——即便实现实际上会返回某个无穷或 NaN（本机 libc++ 给出 `(inf,nan)`）。

为什么这么严？`complex` 的规范远早于 C99 的附录 G（IEEE 复数运算），标准从未要求 `complex` 按 IEEE 语义处理无穷与 NaN。想写可移植的代码，在除数可能为零、或模可能溢出的地方，要自己先检查。

## 与 `T[2]` 的布局兼容（¶4）

¶4 是本节对 language lawyer 最有价值的一段。若 `z` 是 `cv complex<T>` 类型的左值：

- ¶4.1 `reinterpret_cast<cv T(&)[2]>(z)` 良构；
- ¶4.2 其 `[0]` 指代 `z` 的实部；
- ¶4.3 其 `[1]` 指代 `z` 的虚部。

此外，若 `a` 是 `cv complex<T>*` 类型的表达式、且 `a[i]` 良定义，则：

- ¶4.4 `reinterpret_cast<cv T*>(a)[2 * i]` 指代 `a[i]` 的实部；
- ¶4.5 `reinterpret_cast<cv T*>(a)[2 * i + 1]` 指代 `a[i]` 的虚部。

为什么这需要专门写出来？按核心语言，`complex<double>` 是类类型，把它的地址 `reinterpret_cast` 成 `double*` 再访问，要过两道关：类型别名规则（[[basic.lval]] ¶11 只允许通过动态类型、对应有/无符号类型、`char`/`unsigned char`/`std::byte` 访问），以及指针算术只能在同一数组内进行（[[expr.add]]）。`complex` 的私有成员到底是 `T re, im;` 还是 `T v[2];`，标准并不规定，一般的类根本无法保证"跨越对象做 `[2*i+1]`"是合法的。¶4 由库直接担保这些表达式有定义，这是为了与 C 的 `double _Complex`（C 规定它与 `double[2]` 布局相同）以及 FFTW、LAPACK 等以交错数组传递复数的库互操作。

```cpp run title="complex-layout.cpp" ok
#include <complex>
#include <cstdio>
#include <vector>

// 一个以交错 double 数组接收复数的 C 风格接口
void scale_interleaved(double* p, std::size_t n, double k) {
  for (std::size_t j = 0; j < 2 * n; ++j) p[j] *= k;
}

int main() {
  std::vector<std::complex<double>> v{{1, 2}, {3, 4}};
  scale_interleaved(reinterpret_cast<double*>(v.data()), v.size(), 10);   // ¶4.4–4.5
  double (&parts)[2] = reinterpret_cast<double(&)[2]>(v[1]);              // ¶4.1
  parts[1] = -1;                                                          // ¶4.3：改虚部
  std::printf("(%g,%g) (%g,%g)\n", v[0].real(), v[0].imag(), v[1].real(), v[1].imag());
  // 输出 (10,20) (30,-1)
}
```

!!! lawyer "保证的边界"
    ¶4 只担保**这几个表达式**指代实部/虚部；它没有说 `complex<T>` 是标准布局类型，也没有说 `sizeof(complex<T>) == 2 * sizeof(T)`（虽然从 ¶4.4–4.5 可以推出相邻元素之间没有填充）。反方向——把一块 `double` 数组 `reinterpret_cast` 成 `complex<double>*` 再调用成员函数——**不在**保证之内：那里根本没有 `complex` 对象，调用其成员函数违反 [[basic.life]]。

## 类模板与成员（[complex]、[complex.members]、[complex.member.ops]）

类模板只存储笛卡尔分量 `real()`、`imag()`（[complex] ¶1）。成员要点：

**构造函数**。`complex(const T& re = T(), const T& im = T())`，后置条件 `real() == re && imag() == im`（[complex.members] ¶1）。注意它不是 `explicit` 的，所以 `complex<double> z = 1.5;` 合法，表示 `1.5 + 0i`。

**转换构造函数** `template<class X> constexpr explicit(see below) complex(const complex<X>&)`，¶3：`explicit` 中的表达式为 `false` 当且仅当 `T` 的浮点转换秩**大于等于** `X` 的。换句话说，只有不会丢精度的方向（`float → double`、`double → long double`，以及秩相等的类型之间）才是隐式的。

```cpp title="complex-conversion.cpp" error
#include <complex>

std::complex<float>  f{1.0f, 2.0f};
std::complex<double> d = f;     // OK：double 的秩 ≥ float，隐式
std::complex<float>  g{d};      // OK：直接初始化可以用 explicit 构造函数
std::complex<float>  h = d;     // error：复制初始化不考虑 explicit 构造函数
```

这条规则与核心语言对内建浮点类型的处理不同：`float x = 1.0;`（`double → float`）是合法的隐式转换，只在列表初始化中才算窄化。`complex` 把"降秩转换必须显式"写进了类型本身。

**实部/虚部访问**。`real()`/`imag()` 返回值，`real(T)`/`imag(T)` 赋值（¶4–¶7）。因为 getter 返回的是值而不是引用，想原地修改分量只能用 setter、¶4 的数组视图，或 C++26 的 `get<0>(z)`。

**复合赋值**（[complex.member.ops]）。与标量的 `+=`、`-=` 只作用于实部、保留虚部（¶1、¶3）；与标量的 `*=`、`/=` 作用于整个复数（¶5、¶7）。与 `complex<X>` 的复合赋值都是模板，允许混合精度。

## 非成员运算（[complex.ops]）

- 一元 `+`、`-`；二元 `+ - * /` 各有三个重载：`complex op complex`、`complex op T`、`T op complex`。¶2、¶4–¶6 用"复制左操作数再用复合赋值"来定义：`complex<T>(lhs) op= rhs`。
- `operator==` 只有两个重载（`complex == complex`、`complex == T`），¶7 规定比较实部与虚部，¶8 说明 `T` 实参的虚部视为 `T()`。`!=` 和 `T == complex` 由 C++20 的重写候选得到（[[over.match.oper]]）。**没有**任何序关系运算符。
- 流插入 ¶14 按"先写到一个复制了 flags/locale/precision 的 `ostringstream`，再整体输出"定义，格式是 `(re,im)`；这样 `setw` 作用在整个 `(re,im)` 上而不是只作用于实部。¶15 的注释提醒：在以逗号为小数点的 locale 下 `(1,5,2)` 有歧义，加 `showpoint` 可以消除。
- 流提取 ¶10 接受 `u`、`(u)`、`(u,v)` 三种形式；失败时设置 `failbit`。

!!! pitfall "混合类型的算术不会自动提升"
    二元运算符是 `template<class T> complex<T> operator*(const complex<T>&, const T&)`，`T` 要从两个实参**一致地**推导。于是 `std::complex<double> z; z * 2;` 推导失败（`2` 是 `int`，与 `double` 冲突）——必须写 `z * 2.0`。同理 `complex<float> * double` 也无法编译。这和 `<cmath>` 的"额外重载"规则不同，[cmplx.over] 只为 `pow` 和几个值函数提供了混合类型重载。

## 值函数（[complex.value.ops]）

| 函数 | 返回 | 备注 |
|---|---|---|
| `real`、`imag` | 分量 | ¶1–¶2 |
| `abs` | 模 | ¶3 |
| `arg` | 辐角，等于 `atan2(imag(x), real(x))` | ¶4 |
| `norm` | **模的平方** | ¶5；不是"范数"意义上的模 |
| `conj` | 共轭 | ¶6 |
| `proj` | 黎曼球面上的投影 | ¶7–¶8：与 C 的 `cproj` 行为相同——把所有无穷映到 `(+inf, ±0)` |
| `polar(rho, theta)` | 模为 `rho`、辐角为 `theta` 的复数 | ¶9 前置条件：`rho` 非负且非 NaN，`theta` 有限 |

`polar` 的前置条件是 {{ub}} 级别的：`std::polar(-1.0, 0.0)` 不会给你 `-1+0i`，而是违反前置条件。

!!! pitfall "norm 不是 abs"
    很多人以为 `norm` 返回 \|z\|。它返回 \|z\|²。用 `norm` 比较大小（避免开方）是对的；把它当长度用就错了。

## 超越函数（[complex.transcendentals]）

`acos`、`asin`、`atan`、`acosh`、`asinh`、`atanh` 的 *Remarks* 都写"与 C 函数 `cacos` 等行为相同"（¶2、¶4、…、¶12）；`log`、`sqrt` 的注释说意图与 C 的 `clog`、`csqrt` 相同。这样 C++ 的分支切割、特殊值处理就继承自 C 附录 G。几个有规范意义的点：

- **`log`**（¶16–¶17）：对所有 `x`，`imag(log(x))` 在 [−π, π] 内；分支切割沿负实轴。区间两端都闭合，是因为有带符号零：`log(complex(-1, +0.0))` 的虚部是 +π，`log(complex(-1, -0.0))` 是 −π。
- **`log10`**（¶18）：定义为 `log(x) / log(10)`。
- **`pow`**（¶20–¶21）：定义为 `exp(y * log(x))`；`pow(0, 0)` 的值**由实现定义**（{{impl}}）。本机 libc++ 给出 `(nan,nan)`。
- **`sqrt`**（¶24–¶25）：结果在右半平面；分支切割沿负实轴，同样靠零的符号区分两侧。

```cpp run title="branch-cut.cpp" ok
#include <complex>
#include <cstdio>

int main() {
  std::complex<double> above(-1.0, +0.0), below(-1.0, -0.0);
  auto a = std::log(above), b = std::log(below);
  std::printf("%g %g\n", a.imag(), b.imag());     // 3.14159 -3.14159
  auto s = std::sqrt(above), t = std::sqrt(below);
  std::printf("%g %g\n", s.imag(), t.imag());     // 1 -1
}
```

!!! impl "libc++ 的 sqrt"
    本机 libc++ 中 `std::sqrt(complex<double>(-1, 0))` 的实部是 `6.12323e-17` 而不是精确的 0：它通过 `polar(sqrt(abs(x)), arg(x) / 2)` 计算，`cos(π/2)` 不是精确的零。标准只说"语义意图与 `csqrt` 相同"（注释，非规范），所以这不算违规，但说明不要对复数函数的结果做精确比较。

**constexpr**：当前草案的概要中，所有值函数与超越函数都是 `constexpr`。这一扩展来自 [[P1383R2]]，是 C++26 的内容 {{c++26}}。本机 libc++ 尚未跟进：`std::norm`、`std::conj` 和四则运算可以常量求值（C++20 就是 `constexpr` 的），`std::abs`、`std::arg`、`std::exp` 不行。

## 元组接口（[complex.tuple]）{{c++26}}

[[P2819R2]] 给 `complex` 加上了元组协议：

- `tuple_size<complex<T>>` 为 2，`tuple_element<I, complex<T>>::type` 为 `T`，*Mandates*：`I < 2`（¶1）；
- `get<I>(z)` 有四个引用重载，返回实部（`I == 0`）或虚部的**引用**（¶2–¶3）。

这让 `complex` 满足 [[tuple.like]]，可以用于结构化绑定（[[dcl.struct.bind]]），也让 `get<0>(z) = 5;` 成为原地修改实部的合法写法——这在以前只能借助 ¶4 的 `reinterpret_cast`。

```cpp run title="complex-tuple.cpp" ok
#include <complex>
#include <tuple>

int main() {
  std::complex<double> z{1, 2};
  auto& [re, im] = z;          // 引用绑定到实部与虚部
  im = -im;                    // 原地共轭
  std::get<0>(z) *= 3;
  return (z == std::complex<double>(3, -2)) ? 0 : 1;
}
```

`get` 是 `noexcept` 的，并且返回的是对 `complex` 内部存储的引用——这在 C++26 以前没有任何接口暴露过。可以把它看作 ¶4 的布局保证在类型安全层面的对应物。

## 额外重载（[cmplx.over]）

¶1–¶2：`arg`、`norm`、`conj`、`proj`、`imag`、`real` 还有额外的 `constexpr` 重载，保证：

- ¶2.1 实参是浮点类型 `T` 时，等价于先转换成 `complex<T>`；
- ¶2.2 实参是整数类型时，等价于先转换成 `complex<double>`。

所以 `std::real(3)` 返回 `double` 的 `3.0`，`std::conj(2.5f)` 返回 `complex<float>`。注意 `abs` 不在列表里：`std::abs(3)` 是 `<cstdlib>` 的整数版本，与复数无关。

¶3：`pow` 有额外重载：一个实参是 `complex<T1>`、另一个是 `T2` 或 `complex<T2>` 时，两个实参都转换成 `complex<common_type_t<T1, T3>>`，其中 `T2` 是整数类型时 `T3` 为 `double`，否则 `T3` 为 `T2`。若 `common_type_t<T1, T3>` 不良构，程序**非良构**。

```cpp run title="pow-promotion.cpp" ok
#include <complex>
#include <type_traits>

std::complex<float> z{1, 2};
static_assert(std::is_same_v<decltype(std::pow(z, 2)),    std::complex<double>>); // int → 视作 double
static_assert(std::is_same_v<decltype(std::pow(z, 2.0f)), std::complex<float>>);
static_assert(std::is_same_v<decltype(std::real(1)),      double>);
```

`std::pow(complex<float>, 2)` 的结果是 `complex<double>`，这常常出乎意料——想留在 `float` 精度，要写 `pow(z, 2.0f)`，或者干脆写 `z * z`。

## 字面量后缀（[complex.literals]）

¶1：后缀 `i`、`il`、`if` 分别构造虚部为给定值、实部为零的 `complex<double>`、`complex<long double>`、`complex<float>`。每个后缀都有 `long double` 与 `unsigned long long` 两个重载（¶2–¶4），所以 `2i` 和 `2.5i` 都可以。它们位于内联命名空间 `std::literals::complex_literals` 中。

```cpp run title="complex-literals.cpp" ok
#include <complex>
#include <type_traits>
using namespace std::complex_literals;

auto a = 1.0 + 2i;       // complex<double>
auto b = 1.0f + 2if;     // complex<float>：if 是关键字，但可以作为字面量后缀
static_assert(std::is_same_v<decltype(a), std::complex<double>>);
static_assert(std::is_same_v<decltype(b), std::complex<float>>);
```

`if` 是关键字，却能作为字面量后缀：`2if` 整个是**一个**预处理记号（*user-defined-integer-literal*，[[lex.ext]]），其中的 `if` 是记号内部的 *ud-suffix*，根本不会被识别成关键字；声明 `operator""if` 时同理，`""if` 是一个 *user-defined-string-literal* 记号（[[over.literal]]）。不以下划线开头的后缀保留给标准库。另外 `1 + 2i` 不能编译：`int + complex<double>` 同样受"模板实参一致推导"所限，要写 `1.0 + 2i`。

## 思考题

!!! question "1"
    `std::complex<double> z; double* p = &z.real();` 能编译吗？如何在 C++23 与 C++26 中各自合法地得到指向实部的指针？

<details markdown="1">
<summary>答案</summary>

不能。`real()` 返回 `T` 的**值**（[complex] 概要），`&z.real()` 对纯右值取地址，非良构。

C++23：用 [complex.numbers.general] ¶4.2 的保证，`&reinterpret_cast<double(&)[2]>(z)[0]`。

C++26：`&std::get<0>(z)`（[complex.tuple] ¶3，返回实部的引用），不需要 `reinterpret_cast`。
</details>

!!! question "2"
    `std::complex<double>(1, 0) / std::complex<double>(0, 0)` 的行为是什么？`1.0 / 0.0` 呢？（假设 `double` 是 IEEE binary64。）

<details markdown="1">
<summary>答案</summary>

前者：结果在数学上无定义，按 [complex.numbers.general] ¶3 是 UB。

后者：内建除法，[[expr.mul]] 规定第二操作数为零时是 UB；[[expr.pre#4]] 的注释也指出，对遵循 ISO/IEC 60559 的类型，除以零是算术表达式唯一的 UB 情况。所以两者都是 UB，但出处不同；而像 `1e308 * 10.0` 这种上溢，内建运算得到 +inf 是良定义的，`complex` 的运算上溢却仍然落在 ¶3 的 UB 里。
</details>

## 小结

| 规则 | 出处 | 后果 |
|---|---|---|
| `T` 不是浮点类型 | [complex.numbers.general] ¶2 | 未指明 |
| 浮点特化 | ¶2 | 平凡可复制、字面类型 |
| 结果无定义/不可表示 | ¶3 | UB（比核心语言更严） |
| 与 `T[2]` 布局兼容 | ¶4 | `reinterpret_cast` 到 `T(&)[2]` 和 `T*` 访问分量有定义 |
| 转换构造 | [complex.members] ¶3 | 降秩方向 `explicit` |
| `pow(0, 0)` | [complex.transcendentals] ¶20 | 实现定义 |
| `polar` 实参 | [complex.value.ops] ¶9 | `rho ≥ 0` 且非 NaN、`theta` 有限，否则 UB |
| 元组接口 | [complex.tuple] | C++26，支持结构化绑定与 `get` 引用 |
| `pow` 混合类型 | [cmplx.over] ¶3 | 整数实参按 `double` 参与提升 |
