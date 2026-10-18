---
title: 用户定义字面量
summary: 字面量运算符与字面量运算符模板的声明规则：literal-operator-id 的两种写法（带空格者已弃用）、保留的后缀、只能在命名空间作用域、十三种允许的形参列表、数值与字符串两种模板、不得有 C 语言链接；除此之外它们就是普通函数。
status: draft
since: c++11
papers: N2765, P0732R2, P0482R6
related: lex.ext, usrlit.suffix, depr.lit, lex.name, temp.arg.nontype, basic.lookup.unqual, dcl.link
tags: 字面量, 用户定义字面量, UDL, 模板
updated: 2026-10-18
---

[[lex.ext]] 讲的是**使用**一侧：`12_km`、`"abc"_s` 这样的用户定义字面量怎样被改写成对 `operator""_km(12ULL)` 之类的调用。本节讲**声明**一侧：什么样的函数可以叫 `operator""_km`，它能有什么样的形参，模板又该长什么样。两节合在一起才是完整的用户定义字面量（UDL）。

本节在第 12 章"重载"里，是因为字面量运算符同运算符函数一样有特殊的名字，而且同名的多个字面量运算符构成重载集——但它们的选择规则其实主要由 [[lex.ext]] 规定（先找原生形参版本，再退回到原始/模板版本），而不是由 [[over.match]] 的普通排序决定。

## 文法：*literal-operator-id* 的两种写法

```
literal-operator-id:
    operator unevaluated-string identifier         // 形式一：operator "" _km   {{deprecated}}
    operator user-defined-string-literal           // 形式二：operator ""_km
```

两种写法差的是 `""` 与后缀之间有没有空白，但在词法上完全不同：

- 形式一是两个记号：空字符串字面量 `""` + 标识符 `_km`；
- 形式二是**一个**记号：用户定义字符串字面量 `""_km`（[[lex.ext]]），后缀 `_km` 是它的 *ud-suffix*，并不作为独立的标识符出现。

## ¶1：空串、后缀标识符、弃用与保留

¶1 规定：

- 形式二里的用户定义字符串字面量不得有**编码前缀**（`u8""_x`、`L""_x` 都不行）；
- 两种形式里的字符串都必须是**空的**（`operator " "_x` 不行）；
- 形式二的 *ud-suffix* 或形式一的 *identifier* 称为**字面量后缀标识符**（[[g:literal-suffix-identifier|literal suffix identifier]]）；
- **形式一已弃用**（[[depr.lit]]）；
- 有些字面量后缀标识符保留供将来标准化（[[usrlit.suffix]]），使用这种后缀的声明 **IFNDR**。

[[usrlit.suffix]] 的保留规则只有两条：**不以下划线开头**的后缀保留给标准（所以标准库的 `s`、`sv`、`ms`、`i`、`if` 都不带下划线——它们永远不会与用户代码冲突）；**含双下划线** `__` 的后缀保留给实现。

### 为什么要弃用带空格的写法

形式一里后缀是一个独立的**标识符**记号，因而受 [[lex.name]] 中保留标识符规则的约束：以下划线加大写字母开头的标识符（如 `_Bq`）在任何地方都保留给实现。于是

```cpp
double operator""_Bq(long double);    // OK：_Bq 只是 ud-suffix，不是标识符记号
double operator"" _Bq(long double);   // IFNDR：使用了保留标识符 _Bq；而且这种写法已弃用
```

同一个后缀，写法差一个空格，一个合法、一个 IFNDR——这种怪异的差别正是 C++23 弃用形式一的原因（经 [[CWG2521]] 处理）。对作者而言结论很简单：**永远不要在 `""` 和后缀之间加空格**。Clang 对形式一给出 `-Wdeprecated-literal-operator` 警告。

```cpp run ok
double operator""_Bq(long double v) { return double(v); }    // 推荐写法
int main() { return 1.0_Bq == 1.0 ? 0 : 1; }
```

### 保留后缀与 Clang 的态度

```cpp
float operator""E(const char*);       // IFNDR：E 不以下划线开头，保留给标准
int   operator""__x(unsigned long long);   // IFNDR：含 __，保留给实现
```

标准说 IFNDR，即编译器可以默不作声地接受。Clang 23 对 `__x` 给出警告（"user-defined literal suffixes containing '__' are reserved; no literal will invoke this operator"）；对 `""E` 则直接报错——它在词法阶段把 `""E` 当作"字面量后面紧跟标识符"处理（C++11 之前 `"..."E` 可能是合法的宏拼接写法），这一诊断默认是错误级别。

保留后缀的声明在标准库**内部**是允许的——`std::string operator""s(const char*, std::size_t)` 正是这样声明的。在用户代码里写同样的声明，Clang 警告 "user-defined literal suffixes not starting with '_' are reserved"。

## ¶2：只能在命名空间作用域

¶2 *declarator-id* 是 *literal-operator-id* 的声明，必须声明一个**属于命名空间**的函数或函数模板（可以是友元函数），或者函数模板的显式实例化/特化。这样声明的函数是**字面量运算符**（[[g:literal-operator|literal operator]]），函数模板是**字面量运算符模板**（[[g:literal-operator-template|literal operator template]]）。

字面量运算符不能是类成员——因为字面量 `12_km` 没有"对象"，无从调用成员函数。

```cpp error
struct S {
  int operator""_x(unsigned long long);    // error: 必须在命名空间作用域
};
```

"可以是友元"——但要注意，用户定义字面量的查找是**非限定查找**（[[lex.ext#2]]），没有 ADL（字面量没有可供 ADL 使用的类类型实参）。所以只在类内定义的**隐藏友元**字面量运算符**永远找不到**：

```cpp error
struct S {
  friend int operator""_x(unsigned long long) { return 1; }   // 合法声明，但是隐藏友元
};
int a = 2_x;    // error: 非限定查找找不到 operator""_x
```

在命名空间作用域再声明一次即可让它可见。实践中的惯例是把字面量运算符放进一个专门的命名空间（标准库用 `std::literals::chrono_literals` 等内联命名空间），由用户 `using namespace` 引入：

```cpp run ok
#include <chrono>
#include <string>
namespace units {
  struct Km { long double v; };
  constexpr Km operator""_km(long double d) { return {d}; }
  constexpr Km operator""_km(unsigned long long n) { return {static_cast<long double>(n)}; }
}
int main() {
  using namespace std::literals;    // 引入 s、ms 等
  using namespace units;            // 引入 _km
  auto s = "abc"s;
  auto d = 10ms;
  auto k = 1.5_km;
  auto n = 2_km;
  return (s.size() == 3 && d.count() == 10 && k.v == 1.5L && n.v == 2.0L) ? 0 : 1;
}
```

## ¶3–¶4：十三种形参列表

¶3 字面量运算符（非模板）的 *parameter-declaration-clause* 必须**等价于**以下之一：

| 形参列表 | 用于 | 调用形式（[[lex.ext]]） |
|---|---|---|
| `const char*` | 整数/浮点字面量的**原始**形式 | `operator""X("123")` |
| `unsigned long long int` | 整数字面量 | `operator""X(123ULL)` |
| `long double` | 浮点字面量 | `operator""X(1.5L)` |
| `char`、`wchar_t`、`char8_t`、`char16_t`、`char32_t` | 字符字面量 | `operator""X('a')` |
| `const char*, std::size_t` 及 `wchar_t`、`char8_t`、`char16_t`、`char32_t` 四个版本 | 字符串字面量 | `operator""X("abc", 3)` |

若某个形参有**默认实参**，程序非良构。

"等价于"意味着写法可以不同而类型相同：`const char* const`（顶层 const 被调整掉）、`std::size_t` 写成它的底层类型都可以。但类型必须**完全**是这些：整数版本不能是 `int` 或 `long long`，浮点版本不能是 `double`——这样做是为了让一个字面量运算符能接收**任何**值都不丢精度的最大类型，范围检查交给运算符自己（或交给 `consteval`）。

```cpp
#include <cstddef>
int operator""_a(int);                    // error: 整数版本必须是 unsigned long long
double operator""_miles(double);          // error: 浮点版本必须是 long double
int operator""_d(unsigned long long = 0); // error: 不得有默认实参
int operator""_y(const char*, std::size_t, int);   // error: 不在列表中
```

¶4 **原始字面量运算符**（[[g:raw-literal-operator|raw literal operator]]）：只有一个 `const char*` 形参的字面量运算符。它接收整数或浮点字面量**未经解释的拼写**（以空字符结尾的字符串），因此可以处理超出任何内建类型范围的字面量：

```cpp run ok
constexpr unsigned long long digits(const char* s) {
  unsigned long long n = 0;
  for (; *s; ++s) if (*s != '\'') ++n;
  return n;
}
constexpr unsigned long long operator""_ndigits(const char* s) { return digits(s); }
static_assert(1234567890123456789012345_ndigits == 25);   // 太大，unsigned long long 装不下——但原始形式不在乎
int main() {}
```

注意原始字面量运算符**不能**用于字符串字面量：`"abc"_x` 要求 `(const char*, std::size_t)` 版本或字符串字面量运算符模板。

## ¶5：两种模板

¶5 字面量运算符模板只有两种：

- **数值字面量运算符模板**（[[g:numeric-literal-operator-template|numeric literal operator template]]）：模板形参列表只有一个**元素类型为 `char` 的常量模板形参包**，即 `template<char...>`。整数/浮点字面量的拼写被拆成字符作为模板实参：`101_bin` 调用 `operator""_bin<'1','0','1'>()`。
- **字符串字面量运算符模板**（[[g:string-literal-operator-template|string literal operator template]]）{{c++20}}：模板形参列表只有一个声明**类类型**常量模板形参的 *parameter-declaration*，如 `template<FixedString S>`。字符串字面量 `str` 若是这个形参的良构模板实参，`"..."_x` 就调用 `operator""_x<str>()`。

两种模板都必须有**空的** *parameter-declaration-clause*——所有信息都通过模板实参传入。

```cpp run ok
#include <cstddef>
template<char... Cs>
constexpr int operator""_bin() {          // 数值字面量运算符模板
  int v = 0;
  ((v = v * 2 + (Cs - '0')), ...);
  return v;
}
static_assert(101_bin == 5);

template<std::size_t N>
struct FixedString {
  char s[N];
  constexpr FixedString(const char (&a)[N]) { for (std::size_t i = 0; i < N; ++i) s[i] = a[i]; }
};
template<FixedString F>
constexpr std::size_t operator""_len() { return sizeof(F.s) - 1; }   // 字符串字面量运算符模板
static_assert("hello"_len == 5);
int main() {}
```

字符串字面量运算符模板的价值在于：字符串内容成为**编译期常量**，可以在编译期解析（格式串检查、正则编译、单位解析……）。这依赖 C++20 允许类类型作为常量模板形参（[[P0732R2]]，[[temp.arg.nontype]]）。

```cpp
template<char...> int operator""_j(const char*);   // error: 模板的形参列表必须为空
template<int N> int operator""_n();                // error: 既不是 char... 也不是类类型形参
template<class T, T...> int operator""_g();        // 非标准：GNU 扩展的字符串模板形式
```

最后一种 `template<class T, T...>` 是 GCC/Clang 在 C++20 之前提供的扩展（Clang 给出 `-Wgnu-string-literal-operator-template` 警告），标准从未接受它；C++20 的类类型形参方案取而代之。

数值模板不能用于字符串字面量，字符串模板也不能用于数值字面量：

```cpp error
template<char...> int operator""_t();
int a = "abc"_t;    // error: 字符串字面量需要 (const char*, size_t) 版本或字符串字面量运算符模板
```

## ¶6：不得有 C 语言链接

¶6 字面量运算符及其模板不得有 C 语言链接（[[dcl.link]]）。C 没有这样的名字，也无法为其生成 C 风格的符号。

```cpp error
extern "C" void operator""_m(long double);   // error: C 语言链接
```

## ¶7：除此之外，它们只是普通函数

¶7 注 1：字面量运算符通常经用户定义字面量隐式调用，但除上述约束外，它们就是**普通的命名空间作用域函数和函数模板**：按普通函数查找、遵循相同的重载决议规则；可以 `inline`、`constexpr`（以及 `consteval`）；可以有内部、模块或外部链接；可以显式调用；可以取地址……

```cpp run ok
namespace {
  constexpr int operator""_k(unsigned long long v) { return int(v) * 1000; }   // 内部链接
}
int main() {
  static_assert(3_k == 3000);
  auto p = &operator""_k;              // 取地址：int(*)(unsigned long long)
  int v = operator""_k(4);             // 显式调用：实参 4 是 int，经普通转换为 unsigned long long
  return p(1) + v - 5000;
}
```

显式调用时没有 [[lex.ext]] 的魔法：`operator""_k(4)` 就是一次普通的函数调用，走 [[over.match]]。

一个常见的模式是让字面量运算符成为 `consteval`，从而在编译期拒绝非法字面量：

```cpp run ok
consteval unsigned char operator""_u8(unsigned long long v) {
  if (v > 255) throw "out of range";   // 在常量求值中抛出：调用不是常量表达式，编译期报错
  return static_cast<unsigned char>(v);
}
int main() {
  auto x = 200_u8;
  // auto y = 300_u8;   // error: 不是常量表达式
  return x == 200 ? 0 : 1;
}
```

## ¶8：标准的例子

| 声明 | 判定 | 原因 |
|---|---|---|
| `void operator ""_km(long double);` | OK | 注意 `""` 前的空格无关紧要，`""_km` 仍是一个记号 |
| `string operator "" _i18n(const char*, std::size_t);` | OK，已弃用 | 形式一 |
| `template <char...> double operator ""_π();` | OK | 后缀可以用通用字符名（`_π`） |
| `float operator ""_e(const char*);` | OK | 原始字面量运算符 |
| `float operator ""E(const char*);` | IFNDR | 保留后缀（不以 `_` 开头） |
| `double operator""_Bq(long double);` | OK | `_Bq` 不是标识符记号 |
| `double operator"" _Bq(long double);` | IFNDR | 使用了保留标识符 `_Bq` |
| `float operator " "B(const char*);` | 非良构 | 字符串非空 |
| `string operator ""5X(const char*, std::size_t);` | 非良构 | `5X` 不是合法后缀标识符 |
| `double operator ""_miles(double);` | 非良构 | 形参列表不在 ¶3 中 |
| `template <char...> int operator ""_j(const char*);` | 非良构 | 模板的形参列表必须为空 |
| `extern "C" void operator ""_m(long double);` | 非良构 | C 语言链接 |

第一行值得多看一眼：`operator ""_km` 中 `operator` 与 `""_km` 之间的空格无所谓；有所谓的只是 `""` 与后缀**之间**的空格。

## 实现视角

!!! impl
    - **名字修饰**：Itanium C++ ABI 用 `li` 加后缀名编码字面量运算符，例如 `operator""_km(long double)` 修饰为 `_Zli3_kme`。
    - **诊断**：Clang 对形参列表错误给出很友好的提示，如 "invalid literal operator parameter type 'double', did you mean 'long double'?"；对类内声明报 "literal operator 'operator""_x' must be in a namespace or global scope"；对 C 链接报 "literal operator must have C++ linkage"。
    - **数值模板的代价**：`template<char...>` 每个不同拼写的字面量都产生一个不同的特化（`1_x` 与 `01_x` 也不同），大量使用会增加编译时间和符号数量；运算符本身通常 `consteval`/`constexpr` 且被内联，运行时没有代价。

## 历史与演进

!!! history
    - **C++11**：[[N2765]] 引入用户定义字面量：原始、整数、浮点、字符、字符串五类字面量运算符，以及数值字面量运算符模板。
    - **C++14**：标准库首次提供 UDL（`std::string` 的 `s`、`<chrono>` 的 `h`/`min`/`s`/`ms`、`<complex>` 的 `i` 等），全部放在 `std::literals` 的内联命名空间中。
    - **C++20**：[[P0732R2]] 让类类型可以作为常量模板形参，并据此引入字符串字面量运算符模板；[[P0482R6]] 引入 `char8_t`，于是增加 `char8_t` 与 `const char8_t*, std::size_t` 两种形参列表。
    - **C++23**：[[CWG2521]] 弃用 `operator "" _x`（带空格）的写法，并厘清了它与保留标识符的关系。

## 陷阱

!!! pitfall "后缀不以下划线开头"
    `operator""km` 是 IFNDR——这类后缀保留给标准。用户后缀一律以 `_` 开头，且第二个字符最好不是大写字母（虽然在形式二下 `_Km` 也合法，但会诱使人写成形式一）。

!!! pitfall "把字面量运算符写成隐藏友元"
    UDL 的查找只有非限定查找，没有 ADL；只在类内定义的友元字面量运算符永远不会被字面量找到。

!!! pitfall "以为 `int` / `double` 形参也行"
    整数版本只能是 `unsigned long long`，浮点版本只能是 `long double`。需要窄类型时在函数内检查范围（最好 `consteval`）。

!!! pitfall "`-` 不是字面量的一部分"
    `-5_km` 是对 `5_km` 的结果应用一元 `-`，不是把 `-5` 传给运算符。返回类型需要支持一元 `-`。

## 思考题

!!! question "1. 同时声明了 `int operator""_x(unsigned long long)` 与 `int operator""_x(const char*)`，`12_x` 和 `1.5_x` 各调用哪个？"

<details markdown="1">
<summary>答案</summary>

`12_x` 调用 `unsigned long long` 版本：[[lex.ext#3]] 先看有没有 `unsigned long long` 形参的字面量运算符，有就用它，原始版本根本不参与比较。`1.5_x` 是浮点字面量，没有 `long double` 版本，于是退回原始字面量运算符，调用 `operator""_x("1.5")`。这个选择是 [[lex.ext]] 按固定顺序做的，而不是 [[over.match]] 的转换序列排序。
</details>

!!! question "2. 下面两个声明哪个合法？`int operator""_s(const wchar_t*, unsigned long);` 与 `int operator""_s(const wchar_t*, unsigned);`"

<details markdown="1">
<summary>答案</summary>

取决于实现：¶3 要求形参列表**等价于** `const wchar_t*, std::size_t`。`std::size_t` 是实现定义的无符号整型的别名——在 LP64 平台（Linux、macOS 的 64 位）上是 `unsigned long`，第一个声明合法、第二个非良构；在其他平台上可能反过来。可移植的代码应当直接写 `std::size_t`。
</details>

!!! question "3. 为什么字面量运算符不允许默认实参？"

<details markdown="1">
<summary>答案</summary>

如果允许，`(const char*, std::size_t = 0)` 既能当原始字面量运算符（一个实参）又能当字符串版本（两个实参），`(unsigned long long, int = 0)` 则让"形参列表必须是 ¶3 之一"的检查失去意义。[[lex.ext]] 的分派完全依据形参列表的形状，默认实参会让同一个函数同时属于多个类别，因此一律禁止。
</details>

## 小结

!!! summary
    | 方面 | 规则 |
    |---|---|
    | 名字 | `operator""_x`；`operator"" _x`（带空格）已弃用；字符串必须为空、无编码前缀 |
    | 后缀 | 不以 `_` 开头的保留给标准，含 `__` 的保留给实现，使用它们 IFNDR |
    | 作用域 | 只能在命名空间（可以是友元，但隐藏友元找不到） |
    | 非模板形参 | 13 种固定列表之一，不得有默认实参；只有 `const char*` 的是原始字面量运算符 |
    | 模板 | `template<char...>`（数值）或单个类类型常量模板形参（字符串，C++20）；函数形参列表为空 |
    | 链接 | 不得是 C 语言链接 |
    | 其他 | 与普通函数无异：可 `constexpr`/`consteval`、可取址、可显式调用 |
