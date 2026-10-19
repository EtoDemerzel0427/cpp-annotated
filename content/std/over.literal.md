---
title: 用户定义字面量
summary: 字面量运算符怎样声明：operator""_x 的写法、保留的后缀、只能在命名空间作用域、十三种允许的形参列表、数值和字符串两种模板，除此之外它们就是普通函数。
status: draft
since: c++11
papers: N2765, P0732R2, P0482R6, CWG2521
related: lex.ext, usrlit.suffix, depr.lit, lex.name, temp.arg.nontype, basic.lookup.unqual, dcl.link
tags: 字面量, 用户定义字面量, UDL, 模板
updated: 2026-10-19
---

!!! tldr
    - 字面量运算符写作 `operator""_km`。`""` 和后缀之间加空格的写法已弃用，而且可能踩到保留标识符。
    - 用户的后缀必须以下划线开头；不以下划线开头的后缀留给标准库，含 `__` 的留给实现，使用它们是 IFNDR。
    - 字面量运算符只能声明在命名空间作用域。可以是友元，但只在类内定义的隐藏友元永远不会被字面量找到。
    - 非模板版本的形参列表只能是固定的 13 种之一：整数用 `unsigned long long`，浮点用 `long double`，字符串用指针加长度。
    - 模板版本只有两种：`template<char...>` 接收数值字面量的拼写，C++20 起类类型常量模板形参接收整个字符串。

[[lex.ext]] 讲使用的一侧：`12_km`、`"abc"_s` 这样的用户定义字面量怎样变成对 `operator""_km(12ULL)` 之类的调用。这一页讲声明的一侧：什么样的函数可以叫 `operator""_km`，它可以有什么形参。

```cpp run ok
#include <chrono>
#include <string>
namespace units {
  struct Km { long double v; };
  constexpr Km operator""_km(long double d) { return {d}; }
  constexpr Km operator""_km(unsigned long long n) { return {static_cast<long double>(n)}; }
}
int main() {
  using namespace std::literals;   // 引入标准库的 s、ms 等
  using namespace units;           // 引入 _km
  auto s = "abc"s;
  auto d = 10ms;
  auto k = 1.5_km;                 // operator""_km(1.5L)
  auto n = 2_km;                   // operator""_km(2ULL)
  return (s.size() == 3 && d.count() == 10 && k.v == 1.5L && n.v == 2.0L) ? 0 : 1;
}
```

## 名字的两种写法（¶1）

*literal-operator-id* 有两种形式：

```text
literal-operator-id:
    operator unevaluated-string identifier      // operator "" _km，已弃用
    operator user-defined-string-literal        // operator ""_km
```

两者只差 `""` 和后缀之间有没有空白，在词法上却完全不同。第一种是两个记号：空字符串 `""` 加标识符 `_km`。第二种是一个记号，即用户定义字符串字面量 `""_km`（[[lex.ext]]），`_km` 是它的 *ud-suffix*，不是独立的标识符。`operator` 和 `""` 之间的空白无关紧要。

¶1 规定：字符串必须是空的；第二种形式不能有编码前缀（`u8""_x` 不行）。第二种形式的 *ud-suffix* 或第一种形式的标识符叫做**字面量后缀标识符**（[[g:literal-suffix-identifier|literal suffix identifier]]）。第一种形式已弃用（[[depr.lit]]）。

### 为什么弃用带空格的写法

第一种形式里，后缀是一个独立的标识符，因此要受 [[lex.name]] 保留标识符规则的约束：下划线加大写字母开头的标识符，如 `_Bq`，在任何地方都保留给实现。

```cpp
double operator""_Bq(long double);    // OK：_Bq 只是 ud-suffix
double operator"" _Bq(long double);   // IFNDR：用了保留标识符 _Bq，而且这种写法已弃用
```

同一个后缀，只差一个空格，一个合法、一个 IFNDR（非良构，不要求诊断）。C++23 通过 [[CWG2521]] 弃用了带空格的写法。所以不要在 `""` 和后缀之间加空格。Clang 23 对第二行只给出 `-Wdeprecated-literal-operator` 警告，没有提到保留标识符。

### 保留的后缀

¶1 最后说，有些后缀保留给将来的标准化（[[usrlit.suffix]]），使用它们的声明是 IFNDR。规则有两条：不以下划线开头的后缀保留给标准库，所以标准库的 `s`、`sv`、`ms`、`i` 都不带下划线，不会和用户代码冲突；含双下划线的后缀保留给实现。

```cpp
float operator""E(const char*);           // IFNDR：不以下划线开头
int   operator""__x(unsigned long long);  // IFNDR：含 __
```

标准不要求诊断，Clang 23 对两者都警告 `no literal will invoke this operator`。对 `""E` 它还额外报一个默认为错误的诊断 `-Wreserved-user-defined-literal`：C++11 之前 `"..."E` 可以是字符串后跟一个宏名，Clang 要求在字符串和标识符之间加空格。

## 只能在命名空间作用域（¶2）

¶2 声明符名字是 *literal-operator-id* 的声明，必须声明属于命名空间的函数或函数模板（可以是友元），或者函数模板的显式实例化、显式特化。这样声明的函数叫**字面量运算符**（[[g:literal-operator|literal operator]]），函数模板叫**字面量运算符模板**（[[g:literal-operator-template|literal operator template]]）。

字面量 `12_km` 没有对象，无从调用成员函数，所以字面量运算符不能是类的成员：

```cpp error
struct S {
  int operator""_x(unsigned long long);   // error: 必须在命名空间作用域
};
```

它可以是友元，但用户定义字面量只做非限定查找（[[lex.ext#2]]），没有实参依赖查找（ADL），字面量本身也没有类类型的实参可供 ADL 使用。所以只在类内定义的隐藏友元永远找不到：

```cpp error
struct S {
  friend int operator""_x(unsigned long long) { return 1; }   // 声明合法，但是隐藏友元
};
int a = 2_x;   // error: 非限定查找找不到 operator""_x
```

惯例是把字面量运算符放进一个专门的命名空间，由用户 `using namespace` 引入，就像开头的 `units` 和标准库的 `std::literals`。

## 允许的形参列表（¶3–¶4）

¶3 字面量运算符的形参列表必须等价于下面 13 种之一：

| 形参列表 | 用于 | 调用形式 |
|---|---|---|
| `const char*` | 整数、浮点字面量的原始拼写 | `operator""X("123")` |
| `unsigned long long int` | 整数字面量 | `operator""X(123ULL)` |
| `long double` | 浮点字面量 | `operator""X(1.5L)` |
| `char`、`wchar_t`、`char8_t`、`char16_t`、`char32_t` | 字符字面量 | `operator""X('a')` |
| `const char*, std::size_t`，以及 `wchar_t`、`char8_t`、`char16_t`、`char32_t` 的对应版本 | 字符串字面量 | `operator""X("abc", 3)` |

任何形参有默认实参，程序非良构。

等价意味着写法可以不同而类型相同：`const char* const` 的顶层 `const` 会被调整掉，`std::size_t` 也可以写成它的底层类型。但类型必须恰好是这些。整数版本不能是 `int`，浮点版本不能是 `double`：运算符总是用能容纳任何值的最大类型接收实参，范围检查由运算符自己做。

```cpp
#include <cstddef>
int operator""_a(int);                      // error: 整数版本必须是 unsigned long long
double operator""_miles(double);            // error: 浮点版本必须是 long double
int operator""_d(unsigned long long = 0);   // error: 不能有默认实参
int operator""_y(const char*, std::size_t, int);   // error: 不在列表中
```

禁止默认实参，是因为 [[lex.ext]] 完全按形参列表的形状选择调用方式。`(const char*, std::size_t = 0)` 既可以当原始版本，又可以当字符串版本，会让分类失去意义。

¶4 只有一个 `const char*` 形参的字面量运算符叫**原始字面量运算符**（[[g:raw-literal-operator|raw literal operator]]）。它收到的是整数或浮点字面量未经解释的拼写，所以能处理超出任何内建类型范围的字面量：

```cpp run ok
constexpr unsigned long long operator""_ndigits(const char* s) {
  unsigned long long n = 0;
  for (; *s; ++s) if (*s != '\'') ++n;
  return n;
}
static_assert(1234567890123456789012345_ndigits == 25);   // unsigned long long 装不下，原始拼写不受影响
int main() {}
```

原始字面量运算符不用于字符串字面量，`"abc"_x` 需要 `(const char*, std::size_t)` 版本或字符串字面量运算符模板。

## 两种模板（¶5）

¶5 字面量运算符模板只有两种，而且函数形参列表都必须为空，所有信息经模板实参传入：

- **数值字面量运算符模板**（[[g:numeric-literal-operator-template|numeric literal operator template]]）：模板形参列表只有一个元素类型为 `char` 的常量模板形参包，即 `template<char...>`。`101_bin` 调用 `operator""_bin<'1', '0', '1'>()`。
- **字符串字面量运算符模板**（[[g:string-literal-operator-template|string literal operator template]]）{{c++20}}：模板形参列表只有一个类类型的常量模板形参。字符串字面量能作为这个形参的模板实参时，`"..."_x` 调用 `operator""_x<"...">()`。

```cpp run ok
#include <cstddef>
template<char... Cs>
constexpr int operator""_bin() {   // 数值字面量运算符模板
  int v = 0;
  ((v = v * 2 + (Cs - '0')), ...);
  return v;
}
static_assert(101_bin == 5);

template<std::size_t N>
struct FixedString {
  char s[N];
  constexpr FixedString(const char (&a)[N]) {
    for (std::size_t i = 0; i < N; ++i) s[i] = a[i];
  }
};
template<FixedString F>
constexpr std::size_t operator""_len() { return sizeof(F.s) - 1; }   // 字符串字面量运算符模板
static_assert("hello"_len == 5);
int main() {}
```

字符串模板让字符串的内容成为编译期常量，可以在编译期解析格式串、单位等。它依赖 C++20 允许类类型作为常量模板形参（[[P0732R2]]，[[temp.arg.nontype]]）。在那之前，GCC 和 Clang 提供过 `template<class T, T...>` 形式的扩展，标准没有接受它，Clang 至今对它给出 `-Wgnu-string-literal-operator-template` 警告。

```cpp
template<char...> int operator""_j(const char*);   // error: 模板的函数形参列表必须为空
template<int N> int operator""_n();                // error: 既不是 char... 也不是类类型形参
```

数值模板不能用于字符串字面量，反之亦然：

```cpp error
template<char...> int operator""_t();
int a = "abc"_t;   // error: 字符串字面量需要 (const char*, size_t) 版本或字符串模板
```

## 其余规则（¶6–¶8）

¶6 字面量运算符和字面量运算符模板不能有 C 语言链接（[[dcl.link]]），C 里没有这样的名字。`extern "C" void operator""_m(long double);` 非良构。

¶7 的注 1 指出，除了上面这些限制，字面量运算符就是普通的命名空间作用域函数和函数模板：按普通函数查找，遵循同样的重载决议规则，可以是 `inline`、`constexpr` 或 `consteval`，可以有内部、模块或外部链接，可以显式调用，可以取地址。

```cpp run ok
namespace {
  constexpr int operator""_k(unsigned long long v) { return int(v) * 1000; }   // 内部链接
}
int main() {
  static_assert(3_k == 3000);
  auto p = &operator""_k;    // 取地址：int(*)(unsigned long long)
  int v = operator""_k(4);   // 显式调用：4 是 int，按普通规则转换为 unsigned long long
  return p(1) + v - 5000;
}
```

显式调用不经过 [[lex.ext]] 的改写，`operator""_k(4)` 就是一次普通的函数调用。

字面量运算符常写成 `consteval`，这样非法的字面量在编译期就被拒绝：

```cpp run ok
consteval unsigned char operator""_u8(unsigned long long v) {
  if (v > 255) throw "out of range";   // 常量求值中抛出异常：调用不是常量表达式
  return static_cast<unsigned char>(v);
}
int main() {
  auto x = 200_u8;
  // auto y = 300_u8;   // error: 不是常量表达式
  return x == 200 ? 0 : 1;
}
```

¶8 的例子汇总了上面的规则：

| 声明 | 判定 | 原因 |
|---|---|---|
| `void operator ""_km(long double);` | OK | `operator` 后的空格无关紧要 |
| `string operator "" _i18n(const char*, std::size_t);` | OK，已弃用 | 带空格的写法 |
| `template <char...> double operator ""_π();` | OK | 后缀可以用通用字符名（标准写作 `_\u03C0`） |
| `float operator ""_e(const char*);` | OK | 原始字面量运算符 |
| `float operator ""E(const char*);` | IFNDR | 后缀不以下划线开头 |
| `double operator""_Bq(long double);` | OK | `_Bq` 不是标识符记号 |
| `double operator"" _Bq(long double);` | IFNDR | 用了保留标识符 `_Bq` |
| `float operator " "B(const char*);` | 非良构 | 字符串不是空的 |
| `string operator ""5X(const char*, std::size_t);` | 非良构 | `5X` 不是合法的后缀 |
| `double operator ""_miles(double);` | 非良构 | 形参列表不在 ¶3 中 |
| `template <char...> int operator ""_j(const char*);` | 非良构 | 模板的函数形参列表必须为空 |
| `extern "C" void operator ""_m(long double);` | 非良构 | C 语言链接 |

!!! impl
    - Itanium C++ ABI 用 `li` 加后缀名修饰字面量运算符，例如 `operator""_km(long double)` 修饰为 `_Zli3_kme`。
    - Clang 的诊断比较清楚，如 `invalid literal operator parameter type 'double', did you mean 'long double'?`、`literal operator 'operator""_x' must be in a namespace or global scope`、`literal operator must have C++ linkage`。
    - 数值模板为每个不同的拼写生成一个特化，`1_x` 和 `01_x` 也不同。大量使用会增加编译时间和符号数量；运行时通常没有代价，因为运算符一般是 `constexpr` 或 `consteval` 并被内联。

## 历史与演进

!!! history
    - C++11 的 [[N2765]] 引入用户定义字面量：原始、整数、浮点、字符、字符串五类字面量运算符，以及数值字面量运算符模板。
    - C++14 的标准库开始提供字面量后缀（`std::string` 的 `s`，`<chrono>` 的 `h`、`min`、`ms`，`<complex>` 的 `i` 等），都放在 `std::literals` 的内联命名空间里。
    - C++20 的 [[P0732R2]] 允许类类型作为常量模板形参，并据此加入字符串字面量运算符模板；[[P0482R6]] 加入 `char8_t`，相应地多了两种形参列表。
    - C++23 的 [[CWG2521]] 弃用了带空格的写法，并澄清了它与保留标识符的关系。

## 常见误解

!!! pitfall "`-5_km` 把 -5 传给运算符"
    负号不是字面量的一部分。`-5_km` 是对 `5_km` 的结果应用一元 `-`，返回类型需要支持一元 `-`。

!!! pitfall "形参用 `int` 或 `double` 也行"
    整数版本只能是 `unsigned long long`，浮点版本只能是 `long double`。需要更窄的类型时，在函数里检查范围，最好写成 `consteval`。

## 思考题

!!! question "1. 同时声明了 `int operator""_x(unsigned long long)` 和 `int operator""_x(const char*)`，`12_x` 和 `1.5_x` 各调用哪个？"

<details markdown="1">
<summary>答案</summary>

`12_x` 调用 `unsigned long long` 版本。[[lex.ext#3]] 先看有没有形参为 `unsigned long long` 的字面量运算符，有就用它，原始版本不参与比较。`1.5_x` 是浮点字面量，没有 `long double` 版本，于是使用原始字面量运算符，调用 `operator""_x("1.5")`。这个选择是 [[lex.ext]] 按固定顺序做的，不是 [[over.match]] 的转换序列排序。
</details>

!!! question "2. `int operator""_s(const wchar_t*, unsigned long);` 和 `int operator""_s(const wchar_t*, unsigned);` 哪个合法？"

<details markdown="1">
<summary>答案</summary>

取决于实现。¶3 要求形参列表等价于 `const wchar_t*, std::size_t`，而 `std::size_t` 是某个实现定义的无符号整型的别名。在 64 位 Linux 和 macOS（LP64）上它是 `unsigned long`，第一个声明合法，第二个非良构；在别的平台上可能相反。可移植的代码应直接写 `std::size_t`。
</details>
