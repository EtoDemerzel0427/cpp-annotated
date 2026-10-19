---
title: 复数
summary: std::complex<T> 只对浮点类型有定义；它与 T[2] 布局兼容的保证；转换构造何时是 explicit；运算、值函数和超越函数的要点；结果在数学上无定义时是 UB；C++26 的元组接口和 constexpr。
status: done
covers: *
papers: P1467R9, P2819R2, P1383R2
related: numerics, numeric.requirements, c.math, basic.fundamental, conv.rank, basic.lval, dcl.struct.bind, tuple.like, over.lit
tags: 标准库, complex, 浮点, 结构化绑定, 布局
updated: 2026-10-19
---

!!! tldr
    - `complex<T>` 只对没有 cv 限定的浮点类型有定义；`complex<int>` 的效果未指明。浮点特化是平凡可复制的字面类型。
    - 标准保证 `complex<T>` 可以当作 `T[2]` 访问，`complex<T>` 的数组可以当作交错排列的 `T` 数组访问，便于与 C 和数值库互操作。
    - 任何复数函数的结果在数学上无定义或不可表示时都是 UB，包括除以零和上溢。这比内建浮点运算更严格。
    - 从高精度到低精度的转换构造函数是 `explicit` 的；`z * 2` 这种混合类型的运算编译不过，要写 `z * 2.0`。
    - `norm(z)` 是模的平方，不是模；C++26 起可以用 `get<0>(z)` 和结构化绑定取得实部和虚部的引用。

## 基本用法

```cpp run title="complex-basics.cpp" ok
#include <complex>
#include <type_traits>
using namespace std::complex_literals;

static_assert(std::is_trivially_copyable_v<std::complex<double>>);
constexpr std::complex<double> z{3, 4};
// (3+4i)² + (3−4i) = −7+24i + 3−4i
constexpr auto w = z * z + std::conj(z);   // C++20 起可常量求值
static_assert(w.real() == -4 && w.imag() == 20);
static_assert(std::norm(z) == 25);          // 模的平方

auto a = 1.0 + 2i;     // complex<double>
auto b = 1.0f + 2if;   // complex<float>
static_assert(std::is_same_v<decltype(b), std::complex<float>>);

int main() {}
```

`complex<T>` 存储笛卡尔形式的实部和虚部，用 `real()`、`imag()` 读取（[complex] ¶1）。算术运算从 C++20 起是 `constexpr` 的。后缀 `i`、`il`、`if` 构造实部为零的 `complex<double>`、`complex<long double>`、`complex<float>`，它们在内联命名空间 `std::literals::complex_literals` 中（[complex.literals]）。

`if` 是关键字，却能作为后缀，因为 `2if` 整个是一个预处理记号（用户定义字面量，[[lex.ext]]），其中的 `if` 根本不会被当成关键字。

## 允许的元素类型（[complex.numbers.general] ¶2）

¶2 用不是 cv 非限定浮点类型的类型实例化 `complex` 主模板，效果未指明 {{unspec}}。未指明意味着实现可以让它编译通过：本机 libc++ 上 `complex<int>` 的乘法能编译，但 `abs`、`exp` 之类对整数分量的结果没有任何规定，不要使用。

浮点类型包括扩展浮点类型（[[basic.extended.fp]]），例如 `std::float16_t`。C++23 以前标准只有 `float`、`double`、`long double` 三个显式特化；[[P1467R9]] 把它改成所有浮点类型，并重写了转换构造函数的规则（见下文）。

¶2 还规定浮点特化是平凡可复制的字面类型（[[basic.types.general]]）：可以 `memcpy`、`bit_cast`，可以在常量表达式中构造和运算。

## 结果无定义即 UB（¶3）

!!! std
    If the result of a function is not mathematically defined or not in the range of representable values for its type, the behavior is undefined.

    函数的结果在数学上无定义，或不在其类型的可表示范围内时，行为未定义。

这条规则对 `<complex>` 的所有函数生效，包括 `operator/`。内建浮点运算则有一层豁免：[[expr.pre#4]] 规定，结果是该类型拥有的无穷或 NaN 时不算 UB，所以 IEEE 浮点上 `1e308 * 10.0` 得到 +inf 是良定义的。`complex` 没有这层豁免。

因此 `complex<double>(1, 0) / complex<double>(0, 0)` 在标准意义上是 UB，尽管本机 libc++ 实际返回 `(inf,nan)`。`complex` 的规范比 C99 的附录 G（复数的 IEEE 语义）更早，标准从未要求它按 IEEE 规则处理无穷和 NaN。可移植的代码要在除数可能为零、模可能溢出的地方自己先检查。

## 与 T[2] 的布局兼容（¶4）

```cpp run title="complex-layout.cpp" ok
#include <complex>
#include <cstdio>
#include <vector>

// 以交错 double 数组接收复数的 C 风格接口
void scale(double* p, std::size_t n, double k) {
  for (std::size_t j = 0; j < 2 * n; ++j) p[j] *= k;
}

int main() {
  std::vector<std::complex<double>> v{{1, 2}, {3, 4}};
  scale(reinterpret_cast<double*>(v.data()), v.size(), 10);
  auto& parts = reinterpret_cast<double(&)[2]>(v[1]);
  parts[1] = -1;                                    // 改虚部
  std::printf("(%g,%g) (%g,%g)\n", v[0].real(), v[0].imag(),
              v[1].real(), v[1].imag());           // (10,20) (30,-1)
}
```

按核心语言，这段代码本来过不了两关。一是类型别名规则：[[basic.lval]] 只允许通过对象的动态类型、对应的有无符号类型或 `char`、`unsigned char`、`std::byte` 访问对象，`double` 不在其列。二是指针算术只能在同一个数组内进行（[[expr.add]]）。何况标准没有规定 `complex` 的私有成员是 `T re, im;` 还是 `T v[2];`。

¶4 由库直接担保这些表达式有定义。若 `z` 是 `cv complex<T>` 类型的左值：

- ¶4.1 `reinterpret_cast<cv T(&)[2]>(z)` 良构；
- ¶4.2 它的 `[0]` 指代 `z` 的实部；
- ¶4.3 它的 `[1]` 指代 `z` 的虚部。

此外，若 `a` 是 `cv complex<T>*` 类型的表达式，且 `a[i]` 有定义：

- ¶4.4 `reinterpret_cast<cv T*>(a)[2 * i]` 指代 `a[i]` 的实部；
- ¶4.5 `reinterpret_cast<cv T*>(a)[2 * i + 1]` 指代 `a[i]` 的虚部。

这是为了与 C 的 `double _Complex`（C 规定它与 `double[2]` 布局相同）以及 FFTW、LAPACK 等以交错数组传递复数的库互操作。

!!! lawyer "保证的边界"
    ¶4 只担保这几个表达式指代实部和虚部。它没有说 `complex<T>` 是标准布局类型，也没有直接说 `sizeof(complex<T>) == 2 * sizeof(T)`，虽然从 ¶4.4–4.5 可以推出相邻元素之间没有填充。反方向不在保证之内：把一块 `double` 数组 `reinterpret_cast` 成 `complex<double>*` 再调用成员函数，那里并没有 `complex` 对象，违反 [[basic.life]]。

## 构造与成员（[complex.members]、[complex.member.ops]）

构造函数 `complex(const T& re = T(), const T& im = T())` 不是 `explicit` 的，所以 `complex<double> z = 1.5;` 合法，表示 1.5 + 0i。

转换构造函数是 `template<class X> constexpr explicit(see below) complex(const complex<X>&)`。¶3 规定，`explicit` 中的表达式为 `false` 当且仅当 `T` 的浮点转换秩（[[conv.rank]]，[[g:floating-point-conversion-rank]]）大于等于 `X` 的。也就是说，只有不丢精度的方向（`float → double`、`double → long double`，以及秩相等的类型之间）才是隐式的。

```cpp title="complex-conversion.cpp" error
#include <complex>

std::complex<float>  f{1.0f, 2.0f};
std::complex<double> d = f;   // OK：double 的秩不低于 float
std::complex<float>  g{d};    // OK：直接初始化可以用 explicit 构造函数
std::complex<float>  h = d;   // error: 复制初始化不考虑 explicit 构造函数
```

这与内建类型不同：`float x = 1.0;` 是合法的隐式转换，只在列表初始化中才算窄化。`complex` 把降秩转换必须显式写进了类型本身。

`real()`、`imag()` 返回值而不是引用（¶4、¶6），`real(T)`、`imag(T)` 用来赋值（¶5、¶7）。所以 `&z.real()` 是对纯右值取地址，非良构。在 C++26 之前，要原地修改分量只能用这两个 setter 或 ¶4 的数组视图。

复合赋值（[complex.member.ops]）：与标量的 `+=`、`-=` 只作用于实部（¶1、¶3），与标量的 `*=`、`/=` 作用于整个复数（¶5、¶7）。与 `complex<X>` 的复合赋值都是模板，允许混合精度。

## 非成员运算（[complex.ops]）

二元 `+ - * /` 各有三个重载：`complex op complex`、`complex op T`、`T op complex`，都定义为复制左操作数再做复合赋值（¶2、¶4–¶6）。

!!! pitfall "混合类型的运算不会自动提升"
    重载形如 `template<class T> complex<T> operator*(const complex<T>&, const T&)`，`T` 要从两个实参一致地推导。`std::complex<double> z; z * 2;` 推导失败，因为 `2` 是 `int`，与 `double` 冲突，必须写 `z * 2.0`。同样，`1 + 2i` 不能编译，要写 `1.0 + 2i`；`complex<float> * double` 也不行。

`operator==` 只声明了 `complex == complex` 和 `complex == T` 两个（¶7–¶8），`!=` 和 `T == complex` 由 C++20 的重写候选得到（[[over.match.oper]]）。没有任何大小比较运算符。

流插入（¶14）的格式是 `(re,im)`。它先写进一个复制了格式标志、locale 和精度的 `ostringstream`，再整体输出，所以 `setw` 作用于整个 `(re,im)`。¶15 的注释提醒，在以逗号为小数点的 locale 下 `(1,5,2)` 有歧义，加上 `showpoint` 可以消除。流提取（¶10）接受 `u`、`(u)`、`(u,v)` 三种形式。

## 值函数（[complex.value.ops]）

| 函数 | 返回 | 备注 |
|---|---|---|
| `real`、`imag` | 实部、虚部 | ¶1–¶2 |
| `abs` | 模 | ¶3 |
| `arg` | 辐角，即 `atan2(imag(x), real(x))` | ¶4 |
| `norm` | 模的平方 | ¶5 |
| `conj` | 共轭 | ¶6 |
| `proj` | 在黎曼球面上的投影 | ¶7–¶8，与 C 的 `cproj` 相同：所有无穷都映到 (+∞, ±0) |
| `polar(rho, theta)` | 模为 `rho`、辐角为 `theta` 的复数 | ¶9 前置条件：`rho` 非负且不是 NaN，`theta` 有限 |

`norm` 常被误当作模。用它比较大小以避免开方是对的，当作长度用就错了。`std::polar(-1.0, 0.0)` 违反前置条件，是 UB，不会得到 −1 + 0i。

[cmplx.over] ¶1–¶2 为 `arg`、`norm`、`conj`、`proj`、`imag`、`real` 提供了接受实数的额外重载：实参是浮点类型 `T` 时如同先转换成 `complex<T>`，是整数类型时如同先转换成 `complex<double>`。所以 `std::real(3)` 返回 `double` 的 3.0，`std::conj(2.5f)` 返回 `complex<float>`。`abs` 不在其中，`std::abs(3)` 是 `<cstdlib>` 的整数版本。

## 超越函数（[complex.transcendentals]）

`acos`、`asin`、`atan`、`acosh`、`asinh`、`atanh` 的 *Remarks* 都写着与 C 的 `cacos` 等函数行为相同（¶2–¶12 的偶数段）；`log`、`sqrt` 的注释说意图与 C 的 `clog`、`csqrt` 相同。分支切割和特殊值的处理因此继承自 C 的附录 G。

- ¶16–¶17 `log`：`imag(log(x))` 总在 [−π, π] 内，分支切割沿负实轴。区间两端都闭合，是因为有带符号的零：`log(complex(-1, +0.0))` 的虚部是 +π，`log(complex(-1, -0.0))` 的虚部是 −π。
- ¶18 `log10` 定义为 `log(x) / log(10)`。
- ¶20 `pow` 定义为 `exp(y * log(x))`；`pow(0, 0)` 的值由实现定义 {{impl}}，本机 libc++ 给出 `(nan,nan)`。
- ¶24–¶25 `sqrt` 的结果在右半平面，分支切割沿负实轴，同样靠零的符号区分两侧。

```cpp run title="branch-cut.cpp" ok
#include <complex>
#include <cstdio>

int main() {
  std::complex<double> above(-1.0, +0.0), below(-1.0, -0.0);
  auto a = std::log(above), b = std::log(below);
  std::printf("%g %g\n", a.imag(), b.imag());   // 3.14159 -3.14159
  auto s = std::sqrt(above), t = std::sqrt(below);
  std::printf("%g %g\n", s.imag(), t.imag());   // 1 -1
}
```

!!! impl "libc++ 的 sqrt"
    本机 libc++ 中 `std::sqrt(complex<double>(-1, 0))` 的实部是 `6.12323e-17` 而不是 0。它通过 `polar(sqrt(abs(x)), arg(x) / 2)` 计算，而 `cos(π/2)` 在浮点中不是精确的零。与 `csqrt` 相同只是注释中的意图，不具规范效力，所以这不算违规，但说明不要对复数函数的结果做精确比较。

[cmplx.over] ¶3 为 `pow` 提供了混合类型重载：一个实参是 `complex<T1>`、另一个是 `T2` 或 `complex<T2>` 时，两者都转换成 `complex<common_type_t<T1, T3>>`。`T2` 是整数类型时 `T3` 为 `double`，否则 `T3` 就是 `T2`。如果 `common_type_t<T1, T3>` 不良构，程序非良构。

```cpp run title="pow-promotion.cpp" ok
#include <complex>
#include <type_traits>

std::complex<float> z{1, 2};
// 整数实参按 double 参与提升
static_assert(std::is_same_v<decltype(std::pow(z, 2)),
                             std::complex<double>>);
static_assert(std::is_same_v<decltype(std::pow(z, 2.0f)),
                             std::complex<float>>);
static_assert(std::is_same_v<decltype(std::real(1)), double>);

int main() {}
```

所以 `std::pow(complex<float>, 2)` 的结果是 `complex<double>`。想留在 `float` 精度，要写 `pow(z, 2.0f)`，或者直接写 `z * z`。

当前草案的概要中，所有值函数和超越函数都是 `constexpr` 的，这一扩展来自 [[P1383R2]] {{c++26}}。本机 libc++ 尚未跟进：`norm`、`conj` 和四则运算能常量求值（C++20 起就是），`abs`、`arg`、`exp` 不行。

## 元组接口（[complex.tuple]）{{c++26}}

```cpp run title="complex-tuple.cpp" ok
#include <complex>
#include <tuple>

int main() {
  std::complex<double> z{1, 2};
  auto& [re, im] = z;     // 绑定到实部与虚部
  im = -im;               // 原地共轭
  std::get<0>(z) *= 3;
  return z == std::complex<double>(3, -2) ? 0 : 1;
}
```

[[P2819R2]] 给 `complex` 加上了元组协议。¶1 `tuple_size<complex<T>>` 为 2，`tuple_element<I, complex<T>>::type` 为 `T`，要求 `I < 2`。¶2–¶3 `get<I>(z)` 有四个重载，返回实部（`I == 0`）或虚部的引用，并且是 `noexcept` 的。

这样 `complex` 满足 [[tuple.like]]，可以用于结构化绑定（[[dcl.struct.bind]]），`get<0>(z) = 5;` 也成了原地修改实部的合法写法。以前只有 ¶4 的 `reinterpret_cast` 能做到这一点，`get` 可以看作那条布局保证在类型安全层面的对应物。

<details class="fine" markdown="1"><summary>其余条文</summary>

[complex.numbers.general] ¶1：头文件 `<complex>` 定义一个类模板和许多操作复数的函数。

[complex.member.ops] ¶9–¶18：从 `complex<X>` 赋值，以及与 `complex<X>` 的四种复合赋值，各自返回 `*this`。

[complex.ops]：一元 `+` 返回 `complex<T>(lhs)`，一元 `-` 返回 `complex<T>(-lhs.real(), -lhs.imag())`（¶1、¶3）。流提取在输入错误时调用 `is.setstate(ios_base::failbit)`（¶11），整个提取由一系列更简单的提取组成（¶13）。

[complex.literals] ¶2–¶4：每个后缀都有 `long double` 和 `unsigned long long` 两个重载，所以 `2i` 和 `2.5i` 都可以。不以下划线开头的字面量后缀保留给标准库（[[usrlit.suffix]]）。

</details>

## 思考题

!!! question "1"
    `std::complex<double> z; double* p = &z.real();` 能编译吗？在 C++23 和 C++26 中，怎样合法地得到指向实部的指针？

<details markdown="1">
<summary>答案</summary>

不能。`real()` 返回 `double` 的值，`&z.real()` 对纯右值取地址，非良构。

C++23：用 [complex.numbers.general] ¶4.2 的保证，写 `&reinterpret_cast<double(&)[2]>(z)[0]`。

C++26：写 `&std::get<0>(z)`，[complex.tuple] ¶3 规定它返回实部的引用。
</details>

!!! question "2"
    假设 `double` 是 IEEE binary64。`std::complex<double>(1, 0) / std::complex<double>(0, 0)` 的行为是什么？`1.0 / 0.0` 呢？`std::complex<double>(1e308, 0) * 10.0` 呢？

<details markdown="1">
<summary>答案</summary>

第一个：结果在数学上无定义，按 [complex.numbers.general] ¶3 是 UB。

第二个：内建除法，[[expr.mul]] 规定第二操作数为零时是 UB；[[expr.pre#4]] 的注释也指出，对遵循 ISO/IEC 60559 的类型，除以零是算术表达式唯一的 UB 情形。

第三个：结果不在 `double` 的可表示范围内，按 ¶3 是 UB。同样的上溢若发生在内建运算 `1e308 * 10.0` 中，结果是 +inf，是良定义的。
</details>
