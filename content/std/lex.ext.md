---
title: 用户定义字面量
summary: 带 ud-suffix 的整数、浮点、字符、字符串字面量如何被改写为对字面量运算符（或其模板）的调用：词法规则、四种调用形式的选择、拼接时后缀的处理，以及保留后缀与已弃用的声明形式。
status: draft
since: c++11
papers: N2765, P0732R2
related: over.literal, usrlit.suffix, depr.lit, lex.string, lex.icon, lex.fcon, basic.lookup.unqual
tags: 字面量, 用户定义字面量, UDL
updated: 2026-10-17
---

[[g:user-defined-literal|**用户定义字面量**]]（user-defined literal，UDL）让程序员可以写 `10_km`、`"abc"s`、`1.5i` 这样带后缀的字面量，其含义由一个**字面量运算符**（literal operator）函数或函数模板决定。[[lex.ext]] 负责词法部分和"改写为什么调用"；字面量运算符本身的声明规则在 [[over.literal]]；哪些后缀保留在 [[usrlit.suffix]]。

UDL 于 C++11 引入（[[N2765]]）。标准库用它提供了 `std::string_literals`（`"abc"s`）、`std::string_view_literals`（`"abc"sv`）、`std::chrono_literals`（`10ms`、`2h`）、`std::complex_literals`（`1.5i`）等。

## 文法

```
user-defined-literal:
    user-defined-integer-literal
    user-defined-floating-point-literal
    user-defined-string-literal
    user-defined-character-literal
user-defined-integer-literal:
    decimal-literal ud-suffix
    octal-literal ud-suffix
    hexadecimal-literal ud-suffix
    binary-literal ud-suffix
user-defined-floating-point-literal:
    fractional-constant exponent-part(opt) ud-suffix
    digit-sequence exponent-part ud-suffix
    hexadecimal-prefix hexadecimal-fractional-constant binary-exponent-part ud-suffix
    hexadecimal-prefix hexadecimal-digit-sequence binary-exponent-part ud-suffix
user-defined-string-literal:
    string-literal ud-suffix
user-defined-character-literal:
    character-literal ud-suffix
ud-suffix:
    identifier
```

注意：

- 整数和浮点 UDL 的"本体"**不含**内建后缀：`12_km` 的本体是 `12`，没有 `12u_km` 这种东西——`12u_km` 会被解析为本体 `12`、后缀 `u_km`。
- 整数/浮点 UDL 在阶段 3 是一个 *pp-number*（[[lex.ppnumber]]），字符/字符串 UDL 是 *user-defined-character-literal* / *user-defined-string-literal* 预处理记号（[[lex.pptoken]]）。它们在词法上始终是**一个**记号，后缀不是独立的标识符记号——所以后缀永远不会被宏展开。

## ¶1：与普通字面量的竞争

¶1 若一个记号既匹配 *user-defined-literal* 又匹配其他种类的 *literal*，则按后者处理。例：`123_km` 是用户定义字面量，而 `12LL` 是整数字面量（`LL` 本可以当作 ud-suffix，但 `12LL` 首先是合法的整数字面量）。

*user-defined-literal* 中 *ud-suffix* 之前的那个文法非终结符，取**能匹配该非终结符的最长字符序列**。

```cpp run title="udl-split.cpp" ok
template<char... C> constexpr int operator""_cnt() { return sizeof...(C); }
static_assert(0x1F_cnt == 4);      // 本体 0x1F：最长的 hexadecimal-literal
static_assert(1.5e3_cnt == 5);     // 本体 1.5e3：最长的浮点本体
static_assert(1'000_cnt == 5);     // 本体包含数字分隔符：'1' '\'' '0' '0' '0'
int main() {}
```

一个后果：内建后缀"混进"自定义后缀时，结果往往不是你想要的。`12LL_x` 的最长整数本体是 `12`（`12LL` 带了 *integer-suffix*，不是 *decimal-literal*），于是后缀是 `LL_x`——一个不以下划线开头的保留后缀。

## ¶2：查找字面量运算符

¶2 UDL 被当作对字面量运算符或字面量运算符模板（[[over.literal]]）的**调用**。对后缀为 X 的 UDL L，先对以 X 为字面量后缀标识符的 *literal-operator-id*（即 `operator""X`）做**非限定查找**（[[basic.lookup.unqual]]），得到声明集合 S。**S 不得为空。**

非限定查找意味着：字面量运算符必须在使用点可见。标准库的字面量运算符放在内联命名空间 `std::literals::xxx_literals` 中，所以要先 `using namespace std::literals;`（或更细的命名空间）。标准在这里只规定了非限定查找；而且改写后的调用的实参都是内建类型或字符指针，没有关联命名空间，实参依赖查找也找不到什么。

```cpp run title="udl-lookup.cpp" ok
#include <string>
#include <string_view>
int main() {
  // auto s0 = "abc"s;               // error：未找到 operator""s
  using namespace std::literals;
  auto s = "abc"s;                   // std::string
  auto sv = "abc"sv;                 // std::string_view
  return s.size() == sv.size() ? 0 : 1;
}
```

## ¶3：整数 UDL

¶3 设 L 是用户定义整数字面量，n 是去掉后缀的字面量：

1. 若 S 中有参数类型为 `unsigned long long` 的字面量运算符，L 被当作 `operator ""X(nULL)`。
2. 否则，S 中必须有**原始字面量运算符**（raw literal operator，参数为 `const char*`）或**数值字面量运算符模板**（`template<char...>`），**但不能两者都有**。
    - 原始字面量运算符：`operator ""X("n")`——字面量的源码字符组成的字符串；
    - 数值字面量运算符模板：`operator ""X<'c1', 'c2', ... 'ck'>()`，其中 c1c2…ck 是 n 的源码字符序列。注 1：这个序列只能包含基本字符集中的字符。

关键在于**优先级**：只要有 `unsigned long long` 版本就用它（"已烹饪"形式，cooked），哪怕同时存在原始形式。原始形式和模板形式是"备选"，而它们之间不允许共存，否则歧义。

`nULL` 的写法意味着：n 加上 `ULL` 后缀必须是合法的整数字面量。若值超过 `unsigned long long` 的范围，`nULL` 非良构，于是 L 非良构——即使你只是想把它当字符串处理。需要处理任意大的数时，**只**提供原始形式或模板形式。

```cpp run title="udl-int.cpp" ok
#include <cstring>
#include <cassert>
constexpr unsigned long long operator""_u(unsigned long long v) { return v; }
struct Raw { const char* s; };
Raw operator""_raw(const char* s) { return {s}; }
static_assert(42_u == 42 && 0x10_u == 16 && 0b11_u == 3);   // 进制由编译器处理
int main() {
  assert(std::strcmp((123_raw).s, "123") == 0);
  assert(std::strcmp((1'000_raw).s, "1'000") == 0);   // 原始形式看到的是源码字符，包括分隔符
  assert(std::strcmp((0x1p3_raw).s, "0x1p3") == 0);   // 浮点 UDL 也可用原始形式（见 ¶4）
}
```

```cpp title="udl-ambig.cpp" error
int operator""_y(const char*);
template<char...> int operator""_y();
int a = 42_y;                          // error：原始运算符与数值模板不能共存
unsigned long long operator""_z(unsigned long long);
int b = 18446744073709551616_z;        // error：nULL 超出 unsigned long long
```

## ¶4：浮点 UDL

¶4 与 ¶3 平行：若 S 中有参数类型为 `long double` 的字面量运算符，L 被当作 `operator ""X(fL)`；否则同样在原始运算符和数值模板中二选一（不能都有）。

`fL` 意味着值先被转换为 `long double`——对需要精确十进制表示的场景（如定点数、十进制货币），这就已经丢失精度了。原始形式或模板形式让库可以自己解析源码字符，例如在编译期把 `0.1_dec` 精确转换为十进制定点值。

## ¶5：字符串 UDL

¶5 设 L 是用户定义字符串字面量，str 是去掉后缀的字面量，len 是 str 的 code unit 数（不含终止空字符）：

1. 若 S 中有一个字面量运算符**模板**，它有一个常量模板形参，且 str 是该形参的合法模板实参，则 L 被当作 `operator ""X<str>()`。
2. 否则，L 被当作 `operator ""X(str, len)`。

第一种形式是 C++20 随类类型非类型模板参数一起引入的（[[P0732R2]]）：字符串内容成为模板实参，可以在编译期完全处理（如编译期格式串检查、编译期正则）。形参类型必须是**类类型**（字符串字面量本身不能作为模板实参，见 [[lex.string]]），通常是一个能从字符数组构造的"固定字符串"类模板：

```cpp run title="udl-string.cpp" ok
#include <cstddef>
template<std::size_t N> struct FixedString {
  char buf[N]{};
  constexpr FixedString(const char (&s)[N]) {
    for (std::size_t i = 0; i < N; ++i) buf[i] = s[i];
  }
};
template<FixedString S> constexpr std::size_t operator""_fs() { return sizeof(S.buf); }
constexpr std::size_t operator""_len(const char*, std::size_t n) { return n; }

static_assert("hello"_fs == 6);    // 模板形式：S 是 FixedString<6>{"hello"}
static_assert("abc"_len == 3);     // len 不含终止空字符
int main() {}
```

注意字符串 UDL 没有"原始形式"，`(str, len)` 形式也按前缀区分参数类型：`u8"x"_len` 需要 `operator""_len(const char8_t*, std::size_t)`。

## ¶6：字符 UDL

¶6 设 L 是用户定义字符字面量，ch 是去掉后缀的字面量。S 中必须有一个唯一形参类型为 ch 的类型的字面量运算符，L 被当作 `operator ""X(ch)`。

```cpp run title="udl-char.cpp" ok
constexpr int operator""_ord(char c) { return c; }
constexpr char32_t operator""_c(char32_t c) { return c; }
static_assert('A'_ord == 'A' && U'x'_c == U'x');
int main() {}
```

## ¶7：标准的例子

```cpp title="udl-example.cpp" error
#include <string>
#include <cstddef>
long double operator ""_w(long double);
std::string operator ""_w(const char16_t*, std::size_t);
unsigned operator ""_w(const char*);
int main() {
  1.2_w;      // 调用 operator ""_w(1.2L)
  u"one"_w;   // 调用 operator ""_w(u"one", 3)
  12_w;       // 调用 operator ""_w("12")：没有 unsigned long long 版本，回退到原始形式
  "two"_w;    // error：没有适用的字面量运算符（只有 char16_t 版本）
}
```

## ¶8–¶9：拼接

¶8 在阶段 5（[[lex.phases]]），相邻的字符串字面量被拼接，用户定义字符串字面量在这里也被当作字符串字面量。拼接时**去掉并忽略** *ud-suffix*，按 [[lex.string]] 的方式拼接。阶段 5 结束时，如果某个字符串字面量是由至少一个用户定义字符串字面量参与拼接而成的，则所有参与的用户定义字符串字面量必须具有**相同的** *ud-suffix*，该后缀被应用到拼接结果上。

```cpp title="udl-concat.cpp" error
#include <cstddef>
constexpr std::size_t operator""_x(const wchar_t*, std::size_t n) { return n; }
constexpr std::size_t operator""_x(const char*, std::size_t n) { return n; }
static_assert(L"A" "B" "C"_x == 3);   // OK：等价于 L"ABC"_x
static_assert("a" "b"_x == 2);         // OK：后缀可以只出现在其中一段
auto e = "P"_x "Q" "R"_y;             // error：两个不同的 ud-suffix
```

也就是说，后缀可以出现在任意一个（或多个）片段上，但不能互相矛盾。

## 声明形式与保留后缀（[[over.literal]]）

虽然这些规则在第 12 章，但写 UDL 时离不开它们：

- **允许的形参列表**只有固定的几种：`const char*`、`unsigned long long int`、`long double`、`char`、`wchar_t`、`char8_t`、`char16_t`、`char32_t`、以及 `(const charT*, std::size_t)` 五种；不得有默认实参。模板只有两种：`template<char...>`（数值模板）和"单个类类型常量模板形参"（字符串模板）。
- 字面量运算符必须在命名空间作用域（可以是友元），不得有 C 语言链接。
- **以下划线开头**的后缀留给用户；**不以下划线开头**的后缀保留给标准（[[usrlit.suffix]]），声明它们是 IFNDR；含 `__` 的后缀保留给实现。标准库的 `s`、`sv`、`ms`、`i` 等正因此不以下划线开头——它们不会与用户代码冲突。

### `operator"" _x` 已弃用 {{deprecated}}

*literal-operator-id* 有两种写法：

```cpp
operator "" _x     // 字符串字面量 "" + 标识符 _x：已弃用（[[depr.lit]]）
operator ""_x      // 一个用户定义字符串字面量记号 ""_x：推荐
```

区别不只是空格：前者中 `_x` 是一个**独立的标识符记号**，于是受 [[lex.name#4]] 的保留标识符规则约束——`operator"" _Bq` 使用了保留标识符 `_Bq`（`_` + 大写），是 IFNDR；而 `operator""_Bq` 中 `_Bq` 不作为记号出现，完全合法。为了消除这种怪异的差别，带空格的形式被弃用（C++23 起，经核心语言问题 [[CWG2521]] 处理）。Clang 对它给出 `-Wdeprecated-literal-operator` 警告。

```cpp run title="udl-decl.cpp" ok
double operator""_Bq(long double);       // OK
// double operator"" _Bq(long double);   // IFNDR：_Bq 是保留标识符；且此形式已弃用
// float operator""E(const char*);       // IFNDR：E 不以下划线开头，保留给标准
int main() {}
```

## 历史与演进

!!! history
    | 版本 | 变化 |
    |---|---|
    | C++11 | 引入 UDL（[[N2765]]）：整数/浮点的 cooked、raw、`template<char...>` 形式；字符串 `(str, len)` 形式；字符形式 |
    | C++14 | 标准库首批 UDL：`s`（string）、chrono 的 `h` `min` `s` `ms` `us` `ns`、complex 的 `i` `il` `if` |
    | C++17 | `sv`（string_view） |
    | C++20 | 字符串字面量运算符模板（类类型常量模板形参，[[P0732R2]]）；`char8_t` 形式；chrono 的 `d`、`y` |
    | C++23 | `operator"" _x`（带空格）弃用 |

    C++11 引入 UDL 时有一个著名的破坏性变化：`"%"PRId64` 这种"字符串紧贴宏名"的写法从"字符串 + 宏"变成了一个用户定义字符串字面量（[[diff.cpp03.lex]]），必须改成 `"%" PRId64`。

## 陷阱

!!! pitfall "`\"%\"PRId64`"
    在 C++11 及以后，`printf("%"PRId64"\n", v)` 中的 `"%"PRId64` 是一个后缀为 `PRId64` 的 UDL，宏不会展开。Clang 把这种"不以下划线开头的后缀紧贴字面量"报为错误（"invalid suffix on literal; C++11 requires a space between literal and identifier"）。在字符串与宏之间加空格。

!!! pitfall "负数"
    `-5_km` 是 `-(5_km)`：一元负号作用于字面量运算符的返回值。如果返回类型不支持一元负号，就会出错。

!!! pitfall "同时提供 raw 与 template"
    同一后缀的原始字面量运算符和数值字面量运算符模板不能同时可见（¶3），否则整数/浮点 UDL 的调用有歧义。只有 cooked 形式可以与它们共存（且优先）。

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

1. `0x1F_a`：整数 UDL，S 中有 `unsigned long long` 版本 ⇒ `operator""_a(0x1FULL)`。
2. `1e3_a`：浮点 UDL（`1e3` 是 *digit-sequence exponent-part*），S 中有 `long double` 版本 ⇒ `operator""_a(1e3L)`。
3. `1'000_a`：整数 UDL ⇒ `operator""_a(1'000ULL)`，即 1000。
4. `99999999999999999999_a`：整数 UDL，有 `unsigned long long` 版本，所以**必须**用 cooked 形式 `99999999999999999999ULL`——它超出了 `unsigned long long` 的范围，非良构。原始版本虽然存在，但不会被考虑：¶3 的"否则"分支只在没有 `unsigned long long` 版本时才进入。
</details>

!!! question "思考题 2"
    为什么 ¶1 要规定"同时匹配时按普通字面量处理"？举一个没有这条规则就会产生问题的例子。

<details markdown="1">
<summary>答案</summary>

`ud-suffix` 是任意 *identifier*，而内建后缀 `u`、`l`、`ll`、`f`、`z` 等在拼写上也都是标识符。没有这条规则，`12u` 可以同时解析为"整数字面量 12，后缀 u"和"用户定义字面量 12，ud-suffix `u`"。规定优先普通字面量，就保证了加入 UDL 不会改变任何既有字面量的含义；同时也解释了为什么标准保留不以下划线开头的后缀：未来标准新增的内建后缀（如 C++23 的 `z`）不会与用户的字面量运算符冲突。
</details>

## 小结

!!! summary
    - UDL = 字面量本体 + *ud-suffix*；同时匹配普通字面量时按普通字面量处理；本体取最长匹配。
    - 改写为对 `operator""X` 的调用，X 经非限定查找（要 `using namespace std::literals`）。
    - 整数：优先 `unsigned long long`，否则 raw 或 `template<char...>` 二选一；浮点：优先 `long double`，同上。
    - 字符串：优先可接受 str 作为模板实参的字符串模板（C++20），否则 `(str, len)`；字符：`(ch)`。
    - 拼接时后缀可出现在任意片段，但必须一致。
    - 用户后缀以 `_` 开头；写 `operator""_x` 而不是已弃用的 `operator"" _x`。
