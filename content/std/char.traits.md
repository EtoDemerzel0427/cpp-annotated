---
title: 字符 traits
summary: basic_string、string_view 和 iostream 通过 traits 类比较、复制字符和表示文件尾；本页讲 traits 必须提供什么、五个标准特化的规定，以及怎样写自己的 traits。
status: done
covers: *
papers: P0426R1, P0482R6, P1614R2
related: strings, string.view, basic.string, string.classes, c.strings, iostreams.limits.pos, cmp.categories, namespace.std, basic.fundamental
tags: 标准库, 字符串, char_traits, EOF, 定制点
updated: 2026-10-19
---

!!! tldr
    - `basic_string`、`basic_string_view` 和 iostream 不直接对字符用 `==`、`<`、`memcpy`，而是调用第二个模板参数 `traits` 的静态成员。
    - `char_traits<char>` 按 `unsigned char` 比较字符，所以 `std::string` 的排序与 `memcmp` 一致，不随 `char` 是否有符号而变。
    - `int_type` 要能装下所有字符外加一个文件尾值 `eof()`。把 `get()` 的结果存进 `char` 再和 `EOF` 比较是经典错误；`char16_t`、`char32_t` 的 `int_type` 在主流平台上其实装不下。
    - traits 的可选成员 `comparison_category` 决定 `<=>` 的结果类型，缺省时是 `weak_ordering`。
    - 自定义比较规则要写自己的 traits 类，并且一致地覆盖所有比较成员；不能为 `unsigned char` 等类型特化 `std::char_traits`。

## traits 是什么 [char.traits.general]

`std::string` 的完整类型是 `std::basic_string<char, std::char_traits<char>, std::allocator<char>>`。第二个模板参数就是**字符 traits**（character traits，[[g:character-traits]]）：一个只有类型成员和静态函数的类，告诉字符串怎样比较两个字符、怎样求一个以零结尾的序列的长度、怎样批量复制，以及用什么值表示文件尾。

把这些操作放进单独的类，有三个好处：

1. 比较规则成为类型的一部分。同样是 `char`，换一个 traits 就能得到大小写不敏感的字符串（见下文），不必在每次调用时传比较器。
2. 批量操作可以直接用 C 库的原语实现。标准特化的 `length` 就是 `strlen`，`compare` 是 `memcmp`，`copy` 是 `memcpy`。
3. iostream 需要一个比字符多一个取值的类型来表示文件尾，即 `int_type`。这个需求与字符本身无关，放在 traits 里正合适。

¶1 本节定义 traits 类的要求，并给出类模板 `char_traits` 和它的五个特化：`char`、`char8_t`、`char16_t`、`char32_t`、`wchar_t`。

¶2 [[string.classes]]、[[string.view]] 和第 31 章 iostream 中的模板都从模板参数 `traits` 取这组类型和函数。

¶3 字符类型 `C` 和它的 traits 类 `X` 成对地作为 `charT`、`traits` 传给这些模板。如果 `X::char_type` 不是 `C`，程序非良构。libc++ 用 `static_assert` 检查这一点：

```cpp error
#include <string>
std::basic_string<wchar_t, std::char_traits<char>> s;
// error: traits_type::char_type must be the same type as CharT
```

## traits 类必须提供什么 [char.traits.require]

¶1 Table 87 列出了 traits 类 `X` 必须支持的表达式。其中 `c`、`d` 是字符，`p`、`q` 是 `const C*`，`s` 是 `C*`，`n` 是 `size_t`，`e`、`f` 是 `X::int_type`，`r` 是 `C` 类型的左值。紧接着有一条对所有表达式的总要求：

!!! std
    No expression which is part of the character traits requirements specified in [char.traits.require] shall exit via an exception.

所以 traits 的任何操作都不能抛异常。标准特化中 `compare`、`length`、`copy` 等函数没有标 `noexcept`（库的惯例是有前置条件的函数不标），但它们同样不许抛。`basic_string` 的强异常保证（[[basic.string]]）依赖这一点。

表中的表达式分成四组。

**类型成员**：`char_type` 必须是 `C`；`int_type` 见下文；`off_type`、`pos_type` 用于流定位（[[iostreams.limits.pos]]）；`state_type` 是多字节转换的状态类型。

**单个字符**，复杂度都是常数：

| 表达式 | 语义 |
|---|---|
| `X::eq(c, d)` | `c` 是否视为等于 `d` |
| `X::lt(c, d)` | `c` 是否视为小于 `d` |
| `X::assign(r, d)` | `r = d` |

原文用的是 is to be treated as，比较规则由 traits 自己决定。自定义比较就是从这里实现的。

**字符序列**，复杂度都是线性：

| 表达式 | 语义 | 对应的 C 函数 |
|---|---|---|
| `X::compare(p, q, n)` | 用 `eq`、`lt` 逐个比较前 `n` 个字符，返回负数、0 或正数 | `memcmp` |
| `X::length(p)` | 第一个满足 `eq(p[i], C())` 的 `i` | `strlen` |
| `X::find(p, n, c)` | `[p, p+n)` 中第一个等于 `c` 的位置，没有则返回空指针 | `memchr` |
| `X::move(s, p, n)` | 逐个 `assign`，两个区间可以重叠 | `memmove` |
| `X::copy(s, p, n)` | 逐个 `assign`，前置条件是两个区间不重叠 | `memcpy` |
| `X::assign(s, n, c)` | 把 `n` 个位置都设为 `c` | `memset` |

`compare` 只看前 `n` 个字符，遇到空字符不会停下；只有 `length` 关心空字符。`copy` 的区间重叠是这一组中唯一的 {{ub}} 来源，和 `memcpy` 的规定一致（[[c.strings]]）。

**`int_type` 相关**，复杂度都是常数：

| 表达式 | 语义 |
|---|---|
| `X::eof()` | 一个与所有字符的 `to_int_type(c)` 都不相等（按 `eq_int_type` 判断）的值 |
| `X::not_eof(e)` | `e` 不是 `eof()` 就返回 `e`，否则返回某个非 `eof()` 的值 |
| `X::to_char_type(e)` | `e` 对应某个字符就返回它，否则返回未指定的值 |
| `X::to_int_type(c)` | 把字符映射到 `int_type` |
| `X::eq_int_type(e, f)` | 对字符的映射值与 `eq` 一致；两个都是 `eof()` 时为真，只有一个是时为假 |

¶2 `<string>` 声明了主模板 `template<class charT> struct char_traits;`，只作为显式特化的基础，主模板本身没有定义。后果见下文的 `basic_string<unsigned char>`。

## char 按 unsigned char 比较 [char.traits.specializations]

```cpp run ok
#include <string>
#include <cassert>

int main() {
  // 无论 char 是否有符号，'\xff' 都大于 'a'
  static_assert(!std::char_traits<char>::lt('\xff', 'a'));
  assert(std::string("\xff") > std::string("a"));
}
```

`char` 是否有符号由实现决定（[[basic.fundamental]]）：x86-64 和 Apple arm64 上有符号，Linux AArch64 上无符号。如果 `lt` 直接比较 `char`，`"\xff" < "a"` 的结果就会随平台变化。

!!! std
    The two-argument members `eq` and `lt` are defined identically to the built-in operators `==` and `<` for type `unsigned char`.

[char.traits.specializations.char] ¶2 的这条规定让 `std::string` 的顺序与平台无关，并且与 C 的 `memcmp`、`strcmp` 一致（C 标准规定它们按 `unsigned char` 比较）。¶1 说明 `state_type` 是 `<cwchar>` 中的 `mbstate_t`。

另外四个特化（`char8_t`、`char16_t`、`char32_t`、`wchar_t`）的 ¶1 都规定 `assign`、`eq`、`lt` 等同于内建的 `=`、`==`、`<`，不需要特殊处理。

五个特化都在 `<string>` 中定义，所有成员都是 `constexpr`，单字符操作和 `int_type` 操作是 `noexcept`，并且都定义了 `comparison_category = strong_ordering`：

| 特化 | `int_type` | `eof()` | `pos_type` |
|---|---|---|---|
| `char_traits<char>` | `int` | `EOF` | `streampos` |
| `char_traits<char8_t>` | `unsigned int` | 实现定义，不能是合法的 UTF-8 码元 | `u8streampos` |
| `char_traits<char16_t>` | `uint_least16_t` | 实现定义，不能是合法的 UTF-16 码元 | `u16streampos` |
| `char_traits<char32_t>` | `uint_least32_t` | 实现定义，不能是 Unicode 码点 | `u32streampos` |
| `char_traits<wchar_t>` | `wint_t` | `WEOF` | `wstreampos` |

## int_type 与文件尾 [char.traits.typedefs]

¶1 `int_type` 必须能表示每个字符转换来的值，外加一个文件尾值 `eof()`。`char_traits<char>` 的 `int_type` 是 `int`，`eof()` 返回 `EOF`（[char.traits.specializations.char] ¶3），几乎所有实现上是 −1。为了不与 −1 冲突，`to_int_type('\xff')` 必须得到 255，实现的做法是先转成 `unsigned char` 再转 `int`。

`istream::get()` 返回的就是 `int_type`。把它先存进 `char` 再和 `EOF` 比较，就会出错：

```cpp run ok
#include <sstream>
#include <iostream>

int main() {
  std::istringstream in1("\xff" "abc"), in2("\xff" "abc");
  int n1 = 0, n2 = 0;

  char c;                                              // 错误写法
  while ((c = static_cast<char>(in1.get())) != EOF) ++n1;

  using T = std::char_traits<char>;
  for (T::int_type i; !T::eq_int_type(i = in2.get(), T::eof()); )
    ++n2;                                              // 正确写法

  std::cout << n1 << ' ' << n2 << '\n';                // char 有符号时：0 4
}
```

`get()` 读到字节 0xFF 时返回 255，存进有符号的 `char` 变成 −1，再提升为 `int` 与 `EOF` 比较，第一个字节就被当成了文件尾。这段代码没有未定义行为（C++20 起整数转换按模 2^N 进行），只是逻辑错了。正确的做法是一直用 `int_type` 保存 `get()` 的结果，确认不是 `eof()` 之后再转换成字符。

`char_traits<char>` 沿用 C 的 `getc`/`EOF` 约定，所以用了有符号的 `int`。`char8_t` 是 C++20 新增的类型（[[P0482R6]]），没有这个包袱，`int_type` 是 `unsigned int`，`eof()` 只要取 0–255 以外的值即可。

!!! lawyer "char16_t 和 char32_t 的 eof() 放不下"
    `char_traits<char16_t>::int_type` 是 `uint_least16_t`，在主流平台上与 `char16_t` 一样是 16 位。每个 `int_type` 值都对应一个 `char16_t` 值，所以不存在一个与所有 `to_int_type(c)` 都不相等的值，Table 87 对 `eof()` 的要求无法满足。`char32_t` 与 32 位的 `uint_least32_t` 是同样的情况。

    实现只能挑一个不太会出现的值。本机 libc++ 中 `char16_t` 的 `eof()` 是 0xFFFF（U+FFFF 是 Unicode 的非字符），`char32_t` 的是 0xFFFFFFFF：

    ```cpp run ok
    #include <string>
    #include <cstdio>
    int main() {
      using T = std::char_traits<char16_t>;
      std::printf("%d\n", T::eq_int_type(T::to_int_type(u'\xFFFF'), T::eof()));   // 本机输出 1
    }
    ```

    脚注 189 预见到了这种情况：如果 `eof()` 能放进 `char_type`，某些 iostream 操作会给出意外的结果。一个 `basic_istream<char16_t>` 读到码元 0xFFFF 时会以为到了文件尾。实践中很少有人使用 `char16_t` 流，标准库也没有为它提供 `istream`、`ostream` 别名。

¶2 `state_type` 必须可默认构造、可复制、可析构。五个标准特化都用 `mbstate_t`，即 C 库 `mbrtowc` 一族函数的转换状态（[[c.strings]]、[[text.c.strings]]）。`basic_string` 和 `basic_string_view` 用不到 `state_type`、`off_type`、`pos_type`，它们只服务于 `basic_filebuf` 和 `codecvt`。

## comparison_category 决定 <=> 的结果

`comparison_category` 不在 Table 87 里，是可选成员。`basic_string_view` 的 `<=>` 会查找它（[[string.view.comparison#2]]）：

- 存在时，`<=>` 的结果类型就是它；它必须是比较类别类型，否则非良构；
- 不存在时，结果类型是 `weak_ordering`。

`basic_string` 的比较转发给 `basic_string_view`，规则相同。五个标准特化都给出 `strong_ordering`。

缺省值选 `weak_ordering` 是为了自定义 traits。`strong_ordering` 承诺相等的值可以互相替换（[[cmp.categories]]），而自定义 traits 最常见的用途是大小写不敏感比较，`"Hello"` 与 `"HELLO"` 相等，却不能互相替换。

## 自定义 traits：大小写不敏感的字符串

需要改的只有与比较有关的四个成员：`eq`、`lt`、`compare`、`find`。其余成员（`length`、`copy`、`move`、`assign`、`eof` 等）可以从 `std::char_traits<char>` 继承。

```cpp run ok title="ci_string.cpp"
#include <string>
#include <string_view>
#include <cctype>
#include <compare>
#include <iostream>
#include <type_traits>

struct ci_traits : std::char_traits<char> {
  static char up(char c) {
    return static_cast<char>(std::toupper(static_cast<unsigned char>(c)));
  }
  static bool eq(char a, char b) { return up(a) == up(b); }
  static bool lt(char a, char b) {
    return static_cast<unsigned char>(up(a)) < static_cast<unsigned char>(up(b));
  }
  static int compare(const char* p, const char* q, std::size_t n) {
    for (std::size_t i = 0; i != n; ++i) {
      if (lt(p[i], q[i])) return -1;
      if (lt(q[i], p[i])) return 1;
    }
    return 0;
  }
  static const char* find(const char* p, std::size_t n, const char& c) {
    for (; n != 0; --n, ++p)
      if (eq(*p, c)) return p;
    return nullptr;
  }
  using comparison_category = std::weak_ordering;   // 相等不等于可替换
};

using ci_string = std::basic_string<char, ci_traits>;

int main() {
  ci_string s = "Hello World";
  std::cout << (s == "HELLO world") << ' '
            << (s.find("WORLD") != ci_string::npos) << '\n';      // 1 1
  static_assert(std::is_same_v<decltype(s <=> s), std::weak_ordering>);
  std::cout << std::string_view(s.data(), s.size()) << '\n';     // 输出时要换回默认 traits
}
```

写自定义 traits 时要注意几点：

- 比较成员要一起覆盖。`char_traits<char>` 的成员是静态函数，不是虚函数，`basic_string` 调用 `traits::compare` 时找到的是派生类里同名的版本，没有覆盖的就用基类的。只覆盖 `eq` 而不覆盖 `compare`，`==` 仍然区分大小写，见思考题 2。
- `std::toupper` 的实参必须能表示为 `unsigned char` 或等于 `EOF`，传入负的 `char` 是 {{ub}}，所以先转成 `unsigned char`。
- `std::cout << s` 不能编译：`operator<<` 要求流的 traits 与字符串的 traits 相同，需要 `basic_ostream<char, ci_traits>`。例子里先转换成默认 traits 的 `string_view` 再输出。
- `ci_string` 和 `std::string` 是不同的类型，`std::string b = s;` 非良构，只能写 `std::string(s.data(), s.size())`。这种不便是现在很少有人使用自定义 traits 的原因，大小写不敏感比较一般直接写成比较函数或透明比较器。
- 这里的成员没有 `constexpr`，所以 `ci_string` 不能用于常量求值。

## 为什么没有 basic_string<unsigned char>

```cpp error
#include <string>
std::basic_string<unsigned char> s;
// error: implicit instantiation of undefined template 'std::char_traits<unsigned char>'
```

`basic_string<unsigned char>` 需要 `std::char_traits<unsigned char>`，但主模板只有声明（[char.traits.require] ¶2），标准也没有提供这个特化。程序自己也不能补上：[[namespace.std]] 只允许在特化依赖于程序定义的类型时向 `std` 添加特化，`unsigned char` 不是程序定义的类型。`std::byte`、`int` 同理。

唯一合法的做法是写一个自己的 traits 类，作为第二个模板实参传入。libc++ 早期版本曾为任意类型提供过主模板的定义作为扩展，后来移除了。

## 历史

!!! history
    - C++17 起，标准特化的成员都是 `constexpr`（[[P0426R1]]），`std::string_view` 因此可以在常量求值中比较和查找。
    - C++20 加入 `char8_t` 和 `char_traits<char8_t>`（[[P0482R6]]）。
    - C++20 加入 `comparison_category`，字符串的比较运算符改为 `==` 和 `<=>`（[[P1614R2]]）。

## 思考题

!!! question "思考题 1"
    `std::string("a\0b", 3) == std::string("a\0c", 3)` 的比较会在 `'\0'` 处停下吗？

<details markdown="1">
<summary>答案</summary>

不会，结果是 `false`。`basic_string` 的比较最终调用 `traits::compare(p, q, n)`，`n` 是两者长度的较小值（[[string.view.ops#12]]）。Table 87 中 `compare` 只是逐个用 `eq`、`lt` 比较，不认识空字符，于是在第三个字符处得出 `'b' < 'c'`。在 `'\0'` 处停下的是 `strcmp` 这类 C 函数。
</details>

!!! question "思考题 2"
    自定义 traits 只覆盖了 `eq` 和 `lt`，没有覆盖 `compare`。`s1 == s2` 用哪一种相等？

<details markdown="1">
<summary>答案</summary>

用继承来的 `char_traits<char>::compare`，即区分大小写的比较。`basic_string_view` 的 `==` 定义为 `compare(rhs) == 0`（[[string.view.comparison#1]]），`compare` 调用 `traits::compare`（[[string.view.ops#12]]），全程不会直接用到 `eq`。而 `find(charT)` 用 `traits::find`，`starts_with(charT)` 用 `traits::eq`，同一个字符串类型里出现了两套相等的标准。

Table 87 要求 `compare` 的结果由 `eq`、`lt` 决定，这样的 traits 类不满足要求。按 [[res.on.functions#1]]，用不满足要求的类型实例化标准库模板时，标准对结果不作任何要求，效果等同于 {{ub}}。
</details>

!!! question "思考题 3"
    `char_traits<char>::to_char_type(char_traits<char>::eof())` 返回什么？

<details markdown="1">
<summary>答案</summary>

Table 87 规定，`e` 不对应任何字符时 `to_char_type(e)` 返回未指定的值。`eof()` 按定义不对应任何字符，所以结果是未指定的。libc++ 直接把 −1 转换为 `char`，得到 `'\xff'`。所以 `eof()` 和字符 0xFF 转换成 `char` 之后无法区分，必须在转换之前用 `eq_int_type` 判断。
</details>
