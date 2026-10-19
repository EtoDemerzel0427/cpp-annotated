---
title: 用户定义字面量
summary: 10_km、"abc"s 这类带后缀的字面量怎样改写成对字面量运算符的调用：后缀怎样切分、运算符怎样查找、整数和浮点字面量在三种形式中怎样选择、字符串字面量的模板形式，以及拼接时后缀的规则。
status: done
since: c++11
papers: N2765, P0732R2
related: over.literal, usrlit.suffix, depr.lit, lex.string, lex.icon, lex.fcon, basic.lookup.unqual
tags: 字面量, 用户定义字面量, UDL
updated: 2026-10-19
---

!!! tldr
    - `10_km` 会被改写成对 `operator""_km` 的调用；这个运算符靠非限定查找找到，所以用标准库的 `"abc"s` 之前要写 `using namespace std::literals;`。
    - 整数字面量优先调用参数为 `unsigned long long` 的版本；没有它，才在原始形式 `(const char*)` 和模板形式 `template<char...>` 中选一个，两者不能同时存在。浮点字面量同理，优先 `long double`。
    - 字符串字面量优先使用能把整个字符串当作模板实参的运算符模板（C++20），否则调用 `(str, len)`。
    - 一个记号如果也能当作普通字面量，就按普通字面量处理，所以 `12LL` 不是用户定义字面量。
    - 用户的后缀必须以下划线开头；声明时写 `operator""_x`，带空格的 `operator"" _x` 已弃用。

**用户定义字面量**（user-defined literal，UDL）是在整数、浮点、字符或字符串字面量后面紧跟一个标识符后缀（**ud-suffix**）构成的字面量，例如 `10_km`、`"abc"s`、`1.5i`。它的含义由一个名为 `operator""后缀` 的函数或函数模板决定，这种函数叫**字面量运算符**（literal operator）。

本节规定 UDL 怎样改写成对字面量运算符的调用。字面量运算符的声明规则在 [[over.literal]]，后缀的保留规则在 [[usrlit.suffix]]。

```cpp run title="udl-intro.cpp" ok
struct Meters { double v; };
constexpr Meters operator""_km(long double x) {
  return {static_cast<double>(x) * 1000};
}
constexpr Meters operator""_km(unsigned long long x) {
  return {static_cast<double>(x) * 1000};
}
static_assert((1.5_km).v == 1500 && (2_km).v == 2000);
int main() {}
```

## 字面量怎样切分（¶1）

文法上，UDL 由普通字面量的本体加上一个标识符后缀组成。整数和浮点 UDL 的本体不含内建后缀：`12_km` 的本体是 `12`。

¶1 第一条规则：如果一个记号既能匹配用户定义字面量，又能匹配其他种类的字面量，就按后者处理。例 1 指出，`123_km` 是用户定义字面量，而 `12LL` 是整数字面量，尽管 `LL` 在拼写上也是一个标识符。这保证了引入 UDL 不会改变任何已有字面量的含义。

¶1 第二条规则：后缀之前的本体取能匹配的最长字符序列。

```cpp run title="udl-split.cpp" ok
template<char... C> constexpr int operator""_cnt() {
  return sizeof...(C);
}
static_assert(0x1F_cnt == 4);   // 本体 0x1F
static_assert(1.5e3_cnt == 5);  // 本体 1.5e3
static_assert(1'000_cnt == 5);  // 本体包含分隔符：1 ' 0 0 0
int main() {}
```

因为本体是整数或浮点字面量的数字部分，不含内建后缀，`12LL_x` 的本体只能是 `12`，后缀是 `LL_x`。这个后缀不以下划线开头，是保留后缀，本机 Clang 23 直接报错 "invalid suffix 'LL_x' on integer constant"。内建后缀和自定义后缀不能叠加。

在预处理阶段，整数和浮点 UDL 是一个预处理数字（[[lex.ppnumber]]），字符和字符串 UDL 也各是一个预处理记号（[[lex.pptoken]]）。后缀不是独立的标识符记号，所以不会被宏展开。

## 查找字面量运算符（¶2）

¶2 UDL 被当作对字面量运算符或字面量运算符模板的调用。对后缀为 X 的 UDL，先对名字 `operator""X` 做非限定查找（[[basic.lookup.unqual]]），得到声明集合 S。S 不能为空。

非限定查找意味着字面量运算符必须在使用处可见。标准库的字面量运算符放在内联命名空间 `std::literals::string_literals` 等处，所以要先写 `using namespace std::literals;` 或更具体的命名空间。改写后的调用实参都是内建类型或字符指针，没有关联命名空间，实参依赖查找帮不上忙。

```cpp run title="udl-lookup.cpp" ok
#include <string>
#include <string_view>
int main() {
  // auto s0 = "abc"s;   // error: 找不到 operator""s
  using namespace std::literals;
  auto s = "abc"s;       // std::string
  auto sv = "abc"sv;     // std::string_view
  return s.size() == sv.size() ? 0 : 1;
}
```

## 整数和浮点 UDL（¶3–¶4）

字面量运算符有几种形式，[[over.literal]] 给它们起了名字。参数为 `const char*` 的叫**原始字面量运算符**（raw literal operator），它收到的是字面量的源码字符。形如 `template<char...>` 的模板叫**数值字面量运算符模板**（numeric literal operator template），源码字符作为模板实参传入。

¶3 设整数 UDL 去掉后缀后是 n。按下面的顺序决定调用形式：

1. S 中有参数类型为 `unsigned long long` 的字面量运算符，就调用 `operator""X(nULL)`。
2. 否则，S 中必须有原始字面量运算符或数值字面量运算符模板之一，不能两者都有。原始运算符的调用是 `operator""X("n")`；模板的调用是 `operator""X<'c1', 'c2', ..., 'ck'>()`，其中 c1…ck 是 n 的源码字符。注 1 说明，这些字符只能来自基本字符集。

```cpp run title="udl-int.cpp" ok
#include <cstring>
#include <cassert>
constexpr unsigned long long operator""_u(unsigned long long v) {
  return v;
}
struct Raw { const char* s; };
Raw operator""_raw(const char* s) { return {s}; }
static_assert(42_u == 42 && 0x10_u == 16 && 0b11_u == 3);
int main() {
  assert(std::strcmp((123_raw).s, "123") == 0);
  assert(std::strcmp((1'000_raw).s, "1'000") == 0);  // 看到的是源码字符
  assert(std::strcmp((0x1p3_raw).s, "0x1p3") == 0);  // 浮点 UDL 也可以用
}
```

`unsigned long long` 版本收到的是编译器已经解析好的值，进制和数字分隔符都处理过了。只要它存在就优先使用，即使同时有原始版本。原始形式和模板形式只是后备，它们不能同时存在，否则调用有歧义。

`nULL` 的写法有一个后果：n 加上 `ULL` 必须是合法的整数字面量。值超出 `unsigned long long` 时，`nULL` 非良构，整个 UDL 也就非良构，即使你提供了原始版本。需要处理任意大的数（例如大整数库）时，只提供原始形式或模板形式。

```cpp title="udl-ambig.cpp" error
int operator""_y(const char*);
template<char...> int operator""_y();
int a = 42_y;   // error: 原始运算符与数值模板不能共存
unsigned long long operator""_z(unsigned long long);
int b = 18446744073709551616_z;   // error: nULL 超出范围
```

¶4 浮点 UDL 的规则与此平行，只是首选的版本参数为 `long double`，调用 `operator""X(fL)`，其中 f 是去掉后缀的字面量。

值先被转换为 `long double`，对需要精确十进制的场合，例如定点数和货币，这一步已经损失了精度。原始形式和模板形式让库可以自己解析源码字符，在编译期把 `0.1_dec` 精确地转换成十进制定点值。

## 字符串和字符 UDL（¶5–¶6）

¶5 设字符串 UDL 去掉后缀后是 str，len 是 str 的 code unit 个数，不含结尾的空字符：

1. S 中有一个字面量运算符模板，它有一个常量模板形参，而 str 可以作为这个形参的模板实参，就调用 `operator""X<str>()`。
2. 否则调用 `operator""X(str, len)`。

```cpp run title="udl-string.cpp" ok
#include <cstddef>
template<std::size_t N> struct FixedString {
  char buf[N]{};
  constexpr FixedString(const char (&s)[N]) {
    for (std::size_t i = 0; i < N; ++i) buf[i] = s[i];
  }
};
template<FixedString S>
constexpr std::size_t operator""_fs() { return sizeof(S.buf); }
constexpr std::size_t operator""_len(const char*, std::size_t n) {
  return n;
}
static_assert("hello"_fs == 6);   // S 是 FixedString<6>{"hello"}
static_assert("abc"_len == 3);    // len 不含空字符
int main() {}
```

第一种形式由 C++20 的 [[P0732R2]] 随类类型常量模板形参一起引入。整个字符串成为模板实参，于是可以在编译期完整地处理它，例如检查格式串或编译正则表达式。形参必须是类类型，因为字符串字面量本身不能作模板实参（[[lex.string]]），通常用一个能从字符数组构造的定长字符串类模板。

字符串 UDL 没有原始形式。`(str, len)` 的参数类型随前缀变化：`u8"x"_len` 需要 `operator""_len(const char8_t*, std::size_t)`。

¶6 字符 UDL 去掉后缀后是 ch。S 中必须有一个字面量运算符，它唯一的形参就是 ch 的类型，调用形式是 `operator""X(ch)`。

```cpp run title="udl-char.cpp" ok
constexpr int operator""_ord(char c) { return c; }
constexpr char32_t operator""_c(char32_t c) { return c; }
static_assert('A'_ord == 'A' && U'x'_c == U'x');
int main() {}
```

¶7 标准的例 2 把这几种情况放在了一起：

```cpp title="udl-example.cpp" error
#include <string>
#include <cstddef>
long double operator ""_w(long double);
std::string operator ""_w(const char16_t*, std::size_t);
unsigned operator ""_w(const char*);
int main() {
  1.2_w;      // 调用 operator ""_w(1.2L)
  u"one"_w;   // 调用 operator ""_w(u"one", 3)
  12_w;       // 没有 unsigned long long 版本，调用 operator ""_w("12")
  "two"_w;    // error: 只有 char16_t 版本，没有适用的字面量运算符
}
```

## 拼接（¶8–¶9）

¶8 在翻译阶段 5，相邻的字符串字面量被拼接，用户定义字符串字面量在这一步也当作字符串字面量。拼接时先去掉后缀，按 [[lex.string]] 的规则拼接。如果参与拼接的有用户定义字符串字面量，它们的后缀必须都相同，这个后缀应用到拼接的结果上。

```cpp title="udl-concat.cpp" error
#include <cstddef>
constexpr std::size_t operator""_x(const wchar_t*, std::size_t n) { return n; }
constexpr std::size_t operator""_x(const char*, std::size_t n) { return n; }
static_assert(L"A" "B" "C"_x == 3);  // OK：等价于 L"ABC"_x
static_assert("a" "b"_x == 2);       // OK：后缀只出现在一段上
auto e = "P"_x "Q" "R"_y;            // error: 两个不同的后缀
```

后缀可以出现在任意一段或几段上，但不能互相矛盾。¶9 的例 3 就是上面的第一行和最后一行。

## 声明字面量运算符（[[over.literal]]）

写 UDL 时离不开第 12 章的这些规则：

- 字面量运算符的形参列表只能是固定的几种：`const char*`、`unsigned long long int`、`long double`、`char`、`wchar_t`、`char8_t`、`char16_t`、`char32_t`，以及五种 `(const charT*, std::size_t)`，不能有默认实参。模板只有两种：数值模板 `template<char...>`，和带一个类类型常量模板形参的字符串模板。
- 字面量运算符必须属于某个命名空间（可以是友元），不能有 C 语言链接。
- 不以下划线开头的后缀保留给标准将来使用（[[usrlit.suffix]]），用它们声明字面量运算符是 IFNDR（非良构，但编译器不必报告）。含 `__` 的后缀保留给实现。标准库的 `s`、`sv`、`ms`、`i` 不以下划线开头，正因如此才不会和用户代码冲突。

### 带空格的写法已弃用 {{deprecated}}

声明字面量运算符有两种写法：

<div class="compare" markdown="1">

```cpp
// 已弃用：字符串 "" 加标识符 _x
double operator"" _x(long double);
```

```cpp
// 推荐：一个记号 ""_x
double operator""_x(long double);
```

</div>

区别不只是空格。前一种写法里 `_x` 是一个独立的标识符记号，受 [[lex.name]] 的保留标识符规则约束，所以 `operator"" _Bq` 用了保留标识符 `_Bq`（下划线加大写字母）。后一种写法里 `_Bq` 不是单独的记号，完全合法。为了消除这种不合常理的差别，带空格的写法被弃用（[[depr.lit]]，经 [[CWG2521]] 处理）。本机 Clang 23 对它给出 `-Wdeprecated-literal-operator` 警告。

## 历史与演进

!!! history
    | 版本 | 变化 |
    |---|---|
    | C++11 | 引入 UDL（[[N2765]]）：整数和浮点的解析值、原始、`template<char...>` 三种形式；字符串的 `(str, len)` 形式；字符形式 |
    | C++14 | 标准库首批 UDL：`s`（string）；chrono 的 `h`、`min`、`s`、`ms`、`us`、`ns`；complex 的 `i`、`il`、`if` |
    | C++17 | `sv`（string_view） |
    | C++20 | 字符串字面量运算符模板（[[P0732R2]]）；`char8_t` 形式；chrono 的 `d`、`y` |
    | C++23 | 带空格的 `operator"" _x` 弃用 |

## 常见误解

!!! pitfall "字符串紧贴着 PRId64 宏也能展开"
    C++11 起，`printf("%"PRId64"\n", v)` 中的 `"%"PRId64` 是一个后缀为 `PRId64` 的用户定义字符串字面量，宏不会展开（[[diff.cpp03.lex]]）。本机 Clang 23 报错 "invalid suffix on literal; C++11 requires a space between literal and identifier"。在字符串和宏名之间加一个空格即可。

!!! pitfall "`-5_km` 把 -5 传给字面量运算符"
    字面量里没有负号，`-5_km` 是 `-(5_km)`，一元负号作用于字面量运算符的返回值。返回类型不支持一元负号时就会出错。

## 思考题

!!! question "思考题 1"
    给定下面的声明，各表达式分别调用哪个函数？

    ```cpp
    int operator""_a(unsigned long long);
    int operator""_a(const char*);
    int operator""_a(long double);
    // (1) 0x1F_a   (2) 1e3_a   (3) 1'000_a   (4) 99999999999999999999_a
    ```

<details markdown="1">
<summary>答案</summary>

1. `0x1F_a`：整数 UDL，有 `unsigned long long` 版本，调用 `operator""_a(0x1FULL)`。
2. `1e3_a`：`1e3` 有指数，是浮点 UDL，有 `long double` 版本，调用 `operator""_a(1e3L)`。
3. `1'000_a`：整数 UDL，调用 `operator""_a(1'000ULL)`，即 1000。
4. `99999999999999999999_a`：整数 UDL。因为有 `unsigned long long` 版本，必须使用 `99999999999999999999ULL`，而它超出了 `unsigned long long` 的范围，所以非良构。原始版本虽然存在，却不会被考虑：只有没有 `unsigned long long` 版本时，才会走到 ¶3 的否则分支。
</details>

!!! question "思考题 2"
    为什么 ¶1 规定同时匹配时按普通字面量处理？举一个没有这条规则就会出问题的例子。

<details markdown="1">
<summary>答案</summary>

后缀可以是任何标识符，而内建后缀 `u`、`l`、`ll`、`f`、`z` 在拼写上也都是标识符。没有这条规则，`12u` 既可以是带后缀 `u` 的整数字面量，也可以是后缀为 `u` 的用户定义字面量。优先按普通字面量处理，就保证了加入 UDL 不会改变已有字面量的含义。同样的考虑也解释了为什么不以下划线开头的后缀保留给标准：将来新增的内建后缀，例如 C++23 的 `z`，不会和用户的字面量运算符冲突。
</details>
