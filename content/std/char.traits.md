---
title: 字符 traits
summary: char_traits 为什么存在、Table 87 的每一行到底约束了什么、int_type/eof 的设计与 char16_t 上的内在矛盾、char 特化按 unsigned char 比较的规定、comparison_category 如何决定 <=> 的结果类型，以及自定义 traits（大小写不敏感字符串）的写法与代价
status: done
covers: *
papers: P0426R1, P0482R6, P1614R2
related: strings, string.view, basic.string, string.classes, c.strings, iostreams.limits.pos, cmp.categories, namespace.std, basic.fundamental
tags: 标准库, 字符串, char_traits, EOF, 定制点
updated: 2026-10-18
---

`basic_string`、`basic_string_view` 和整个 iostream 都不直接对 `charT` 做 `==`、`<`、`memcpy`。它们把"字符怎么比较、怎么复制、序列多长、文件尾怎么表示"这些操作全部委托给第二个模板参数 `traits`。本节规定这个参数必须提供什么（[char.traits.require]），并给出标准库自带的五个实现（[char.traits.specializations]）。

为什么不直接用运算符？有三个历史原因，到今天仍然成立：

1. **比较语义可以和类型分离**。同样是 `char`，你可能想要大小写不敏感的比较。traits 让"比较规则"成为类型的一部分，而不是每次调用都传一个比较器。
2. **批量操作可以换成 C 库原语**。`traits::length` 就是 `strlen`/`wcslen`，`traits::copy` 是 `memcpy`，`traits::compare` 是 `memcmp`——标准特化把这些写成 `constexpr` 函数，实现通常在常量求值时走循环，运行期走内建函数。
3. **iostream 需要一个"比任何字符都多一个值"的类型**来表示 EOF，即 `int_type`。这个需求和字符本身无关，只能放在一个旁路类里。

## 总则（[char.traits.general]）

¶1：本节定义 *character traits*（[[g:character-traits]]）的要求，以及满足要求的类模板 `char_traits<charT>` 和它的五个特化：`char`、`char8_t`、`char16_t`、`char32_t`、`wchar_t`。

¶2：[string.classes]、[string.view] 和 [input.output] 中的大部分模板都需要这样一组成员 *typedef-name* 和函数，它们统一从模板参数 `traits` 中取。

¶3 是本节唯一一条带 {{ill-formed}} 后果的规则：

!!! std
    If `X::char_type` is not the same type as `C`, the program is ill-formed.

    `basic_string<C, X>` 中，`X::char_type` 必须恰好是 `C`，否则程序非良构。

[string.view.template.general] ¶1 与 [string.require] ¶3 的注里重复了这句话。实现通常用 `static_assert` 落地：

```cpp error
#include <string>
std::basic_string<wchar_t, std::char_traits<char>> s;   // error: traits_type::char_type must be the same type as CharT
```

## 要求表：Table 87 逐行（[char.traits.require]）

¶1 先约定记号：`X` 是 traits 类，`C` 是字符类型，`c`/`d` 是 `C` 的值，`p`/`q` 是 `const C*`，`s` 是 `C*`，`n`/`i`/`j` 是 `size_t`，`e`/`f` 是 `X::int_type`，`pos` 是 `X::pos_type`，`r` 是 `C` 类型的左值。紧接着一句很重的话：

!!! std
    No expression which is part of the character traits requirements specified in [char.traits.require] shall exit via an exception.

    要求表中的任何表达式都**不得**以异常退出。

这是一条对 traits 类作者的要求。标准特化里 `compare`、`length`、`find`、`move`、`copy`、`assign(s,n,c)` 并没有写 `noexcept`（因为它们有前置条件，按库的惯例不标 `noexcept`），但它们照样不许抛。`basic_string` 的强异常保证（[string.require] ¶2）在很大程度上依赖这一点。

把表格按用途分成四组：

**类型成员**

| 成员 | 含义 |
|---|---|
| `char_type` | 必须是 `C` |
| `int_type` | 能表示所有字符**以及** `eof()` 的整数类型（[char.traits.typedefs] ¶1） |
| `off_type`、`pos_type` | 流定位用，见 [[iostreams.limits.pos]] |
| `state_type` | 多字节转换状态，见下文 |

**单字符操作**（复杂度均为常数）

| 表达式 | 语义 |
|---|---|
| `X::eq(c, d)` | `c` 是否"被视为"等于 `d` |
| `X::lt(c, d)` | `c` 是否"被视为"小于 `d` |
| `X::assign(r, d)` | `r = d` |

注意措辞是 *is to be treated as*：这正是允许自定义比较语义的那扇门。表格没有要求 `eq` 与 `lt` 构成严格弱序，但 `compare` 的定义依赖它们，`<=>` 的结果类型又取决于 `comparison_category`（见下文），所以实际上应当保持一致。

**序列操作**（复杂度均为线性）

| 表达式 | 语义 | 要点 |
|---|---|---|
| `X::compare(p, q, n)` | 字典序比较前 `n` 个字符，返回负/零/正 | 只看前 `n` 个，**不**在终止符处停 |
| `X::length(p)` | 第一个满足 `eq(p[i], charT())` 的 `i` | 就是 `strlen`；`p` 必须指向以 `charT()` 结尾的序列 |
| `X::find(p, n, c)` | `[p, p+n)` 中第一个与 `c` 相等的位置，没有则 `nullptr` | 就是 `memchr` |
| `X::move(s, p, n)` | 逐个 `assign`，**允许重叠** | 就是 `memmove` |
| `X::copy(s, p, n)` | 逐个 `assign`，前置条件：**不重叠** | 就是 `memcpy`；重叠是 {{ub}} |
| `X::assign(s, n, c)` | 把 `n` 个位置都设为 `c` | 就是 `memset` |

`copy` 的前置条件是这一组里唯一的 UB 来源，它和 [[c.strings]] 中 `memcpy` 的重叠规则一脉相承。

**`int_type` 操作**（常数）

| 表达式 | 语义 |
|---|---|
| `X::eof()` | 一个与**所有**字符的 `to_int_type(c)` 都不相等（按 `eq_int_type`）的值 |
| `X::not_eof(e)` | `e` 不是 EOF 就返回 `e`，否则返回某个非 EOF 值 |
| `X::to_char_type(e)` | 若 `e` 对应某个字符 `c` 就返回 `c`，否则返回未指明的值 |
| `X::to_int_type(c)` | 把字符映射到 `int_type` |
| `X::eq_int_type(e, f)` | 对字符映射值与 `eq` 一致；两个都是 EOF 为真；只有一个是 EOF 为假；其余未指明 |

¶2：类模板 `template<class charT> struct char_traits;` 在 `<string>` 中提供，"as a basis for explicit specializations"。标准**没有给主模板任何成员**。这句话的后果见下文"`basic_string<unsigned char>` 为什么不行"。

## `int_type` 与 `state_type`（[char.traits.typedefs]）

¶1：`int_type` 必须能表示所有由 `char_type` 转换来的有效字符，**外加**一个 `eof()` 值。脚注 189 补了一句耐人寻味的话：

> 如果 `eof()` 能放进 `char_type`，某些 iostream 操作可能产生令人意外的结果。

这句话不是假设，它正好描述了 `char_traits<char16_t>`——见下文。

¶2：`state_type` 必须满足 *Cpp17Destructible*、*Cpp17CopyAssignable*、*Cpp17CopyConstructible*、*Cpp17DefaultConstructible*。五个标准特化都用 `mbstate_t`，它是 C 库 `mbrtowc` 一族函数的转换状态（[[text.c.strings]]）。`basic_string` 和 `basic_string_view` 根本不使用 `state_type`、`off_type`、`pos_type`；它们只服务于 `basic_filebuf` 和 `codecvt`。

## 五个标准特化（[char.traits.specializations]）

[char.traits.specializations.general] ¶1：`<string>` 定义五个特化。它们的成员全部 `constexpr`（C++17 起，[[P0426R1]]），单字符操作和 `int_type` 操作是 `noexcept`，并且都有 `using comparison_category = strong_ordering;`（C++20，[[P1614R2]]）。

| 特化 | `int_type` | `eof()` | `pos_type` |
|---|---|---|---|
| `char_traits<char>` | `int` | `EOF` | `streampos` |
| `char_traits<char8_t>` | `unsigned int` | 实现定义，不是合法的 UTF-8 码元 | `u8streampos` |
| `char_traits<char16_t>` | `uint_least16_t` | 实现定义，"不能作为合法的 UTF-16 码元出现" | `u16streampos` |
| `char_traits<char32_t>` | `uint_least32_t` | 实现定义，不是 Unicode 码点 | `u32streampos` |
| `char_traits<wchar_t>` | `wint_t` | `WEOF` | `wstreampos` |

### `char`：按 `unsigned char` 比较（[char.traits.specializations.char] ¶1–3）

¶1：`mbstate_t` 定义在 `<cwchar>`，能表示实现定义的一组多字节编码规则中可能出现的任何转换状态。

¶2 是 `char` 特化最重要的一段：

!!! std
    The two-argument members `eq` and `lt` are defined identically to the built-in operators `==` and `<` for type `unsigned char`.

    `eq` 与 `lt` 按 **`unsigned char`** 的内建 `==`、`<` 定义。

`char` 是否有符号是实现定义的（[[basic.fundamental]]；x86-64 与 Apple arm64 上有符号，Linux AArch64 上无符号）。如果 `lt` 直接比较 `char`，那么 `"\xff" < "a"` 的结果会随平台变化。这条规定让 `std::string` 的排序与 `memcmp`/`strcmp` 一致（C 标准规定它们按 `unsigned char` 比较），并且与平台无关：

```cpp run ok
#include <string>
#include <cassert>

int main() {
  // 无论 char 是否有符号，0xFF 都大于 'a'
  static_assert(!std::char_traits<char>::lt('\xff', 'a'));
  assert(std::string("\xff") > std::string("a"));
}
```

¶3：`eof()` 返回 `EOF`（几乎所有实现上是 `-1`）。相应地 `to_int_type(c)` 必须把 `'\xff'` 映射到 **255** 而不是 −1，否则它会和 EOF 撞车——实现都是先转成 `unsigned char` 再转 `int`。这就是经典 bug 的根源：

```cpp run ok
#include <sstream>
#include <iostream>

int main() {
  std::istringstream in1("\xff" "abc"), in2("\xff" "abc");
  int n1 = 0, n2 = 0;

  char c;                                              // 错误写法
  while ((c = static_cast<char>(in1.get())) != EOF) ++n1;

  for (std::char_traits<char>::int_type i;             // 正确写法
       !std::char_traits<char>::eq_int_type(i = in2.get(), std::char_traits<char>::eof()); )
    ++n2;

  std::cout << n1 << ' ' << n2 << '\n';                // char 有符号时：0 4
}
```

`get()` 返回 `int_type` 的 255，存进有符号 `char` 变成 −1，再提升回 `int` 与 `EOF` 比较——第一个字节就被当成了文件尾。程序本身行为明确（转换结果是实现定义的，C++20 起规定为模 2^N），但逻辑错了。

### `char8_t`、`char16_t`、`char32_t`、`wchar_t`

三个 Unicode 特化的 ¶1 都只说 `assign`/`eq`/`lt` 等同于内建 `=`/`==`/`<`。它们本来就是无符号类型，不需要 `char` 那样的特殊处理。`wchar_t` 特化的 ¶1 同理，¶2 规定 `eof()` 返回 `WEOF`。

各自的 ¶2 规定 `eof()` 的取值：

- `char8_t`：`int_type` 是 `unsigned int`，空间富余，EOF 可以取任何非 0x00–0xFF 的值；
- `char32_t`：`uint_least32_t` 至少 32 位，而 Unicode 码点最大 0x10FFFF，EOF 可以取 0xFFFFFFFF；
- `char16_t`：麻烦来了。

!!! lawyer "char16_t 的 EOF 放不下"
    `char_traits<char16_t>::int_type` 被规定为 `uint_least16_t`，在所有主流平台上是 16 位——**和 `char16_t` 一样宽**。于是每一个 `int_type` 值都对应一个 `char16_t`，不存在一个"不等于任何 `to_int_type(c)`"的值，Table 87 对 `eof()` 的要求在类型层面就无法满足。实现只好挑一个"不太会出现"的码元：libc++ 用 0xFFFF（U+FFFF 是 Unicode 非字符）。本机实测：

    ```cpp
    using T = std::char_traits<char16_t>;
    T::eq_int_type(T::to_int_type(u'\xFFFF'), T::eof());   // libc++: true
    ```

    这正是脚注 189 所说的"`eof()` 能放进 `char_type`"的情形：一个 `basic_istream<char16_t>` 读到码元 0xFFFF 时会以为到了文件尾。好在 `char16_t` 流在实践中几乎没人用（标准库也没有为 `char16_t` 提供任何 `istream`/`ostream` 类型别名）。

## `comparison_category` 与 `<=>`

C++20 起标准特化都定义了 `comparison_category = strong_ordering`。它不在 Table 87 里，是**可选**成员：`basic_string_view` 的 `<=>` 会去查它（[string.view.comparison] ¶2），查不到就退化为 `weak_ordering`；查到的不是比较类别类型则 *Mandates* 失败、程序非良构（¶3）。`basic_string` 的 `<=>` 转发给 `basic_string_view`（[string.cmp] ¶1），规则相同。

为什么默认是 `weak_ordering` 而不是 `strong_ordering`？因为 `strong_ordering` 承诺"相等即可替换"（[[cmp.categories]]），而自定义 traits 最常见的用途——大小写不敏感比较——恰恰违反这一点：`"Hello"` 与 `"HELLO"` 相等，却不能互相替换。

## 自定义 traits：大小写不敏感字符串

只需要覆盖与比较有关的四个成员：`eq`、`lt`、`compare`、`find`，其余（`length`、`copy`、`move`、`assign`、`eof`……）从 `std::char_traits<char>` 继承即可。

```cpp run ok title="ci_string.cpp"
#include <string>
#include <string_view>
#include <cctype>
#include <compare>
#include <iostream>

struct ci_traits : std::char_traits<char> {
  static char up(char c) { return static_cast<char>(std::toupper(static_cast<unsigned char>(c))); }
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
  using comparison_category = std::weak_ordering;   // 相等 ≠ 可替换
};

using ci_string_view = std::basic_string_view<char, ci_traits>;
using ci_string = std::basic_string<char, ci_traits>;

int main() {
  ci_string s = "Hello World";
  std::cout << (s == "HELLO world") << ' '
            << (s.find("WORLD") != ci_string::npos) << '\n';      // 1 1
  static_assert(std::is_same_v<decltype(s <=> s), std::weak_ordering>);
  ci_string_view v = s;
  std::cout << std::string_view(v.data(), v.size()) << '\n';     // 换 traits 必须显式
}
```

几个值得注意的细节：

- **继承必须"整体覆盖"**。`char_traits<char>` 的成员是静态函数，不是虚函数。`basic_string` 调用的是 `traits::find`，名字查找会找到派生类里的版本——前提是你**真的覆盖了**。如果只覆盖 `eq` 而不覆盖 `compare`/`find`，继承来的 `compare` 仍然是 `memcmp` 语义，比较结果就会自相矛盾。
- **toupper 前转 `unsigned char`**：`<cctype>` 的函数对负的 `char` 值是 {{ub}}（参数必须可表示为 `unsigned char` 或等于 `EOF`）。
- **`std::cout << s` 不能直接用**：`operator<<` 要求流的 traits 与字符串的 traits 一致（`basic_ostream<char, ci_traits>` 才行），所以例子里转回 `std::string_view` 再输出。
- **与 `std::string` 不互通**：`std::string b = s;` 非良构——它们是不同类型，必须显式 `std::string(s.data(), s.size())`。这也是现代代码很少再用自定义 traits 的原因：大小写不敏感比较通常直接写成一个比较函数或透明比较器。
- **常量求值**：这里的成员没写 `constexpr`，所以 `ci_string` 不能在常量表达式里用，但运行期完全正常。

## `basic_string<unsigned char>` 为什么不行

[char.traits.require] ¶2 只**声明**了主模板。用户想要 `std::basic_string<unsigned char>`（或 `std::byte`、`int` 等）时，需要 `std::char_traits<unsigned char>` 的定义，但：

- 标准没有提供这个特化；
- 用户也**不能**自己特化它：[[namespace.std]] 只允许在特化依赖于程序定义类型（*program-defined type*）时向 `std` 添加模板特化，`unsigned char` 不是。

所以唯一合法的做法是写自己的 traits 类，作为第二个模板参数传入。libc++ 早期版本曾为任意类型提供过一个通用的主模板定义作为扩展，现已移除；本机 libc++ 下：

```cpp error
#include <string>
std::basic_string<unsigned char> s;   // error: implicit instantiation of undefined template 'std::char_traits<unsigned char>'
```

## 思考题

!!! question "1. `std::string(“a\\0b”, 3) == std::string(“a\\0c”, 3)` 的比较会在 `\\0` 处停下吗？"

<details markdown="1">
<summary>展开查看答案与解析</summary>

不会。`basic_string` 的比较最终调用 `traits::compare(p, q, n)`，其中 `n` 是两者长度的较小值（[string.view.ops] ¶12）。Table 87 对 `compare` 的定义只是逐个看 `eq`/`lt`，**不**认识终止符——那是 `length` 的事。所以结果是 `false`（第三个字符 `'b' < 'c'`）。只有 `strcmp` 这类 C 函数才会在 `'\0'` 处停。

</details>

!!! question "2. 自定义 traits 只覆盖了 `eq` 和 `lt`，没有覆盖 `compare`。`s1 == s2` 用哪个语义？"

<details markdown="1">
<summary>展开查看答案与解析</summary>

用继承来的 `char_traits<char>::compare`，即区分大小写的 `memcmp` 语义。`basic_string_view::operator==` 定义为 `compare(rhs) == 0`（[string.view.comparison] ¶1），`compare` 又调用 `traits::compare`（[string.view.ops] ¶12），从头到尾没有直接用到 `eq`。而 `find(charT)` 会用 `traits::find`，`starts_with(charT)` 会用 `traits::eq`——同一个字符串类型里出现了两套相等语义。Table 87 要求 `compare` 的结果"由 `eq`/`lt` 定义"，这样的 traits 类**不满足要求**。[[res.on.functions#1]] 规定：程序提供的组件（包括用来实例化标准库模板的类型）不满足要求时，标准对实现不再有任何要求——效果上等同于 {{ub}}。

</details>

!!! question "3. 为什么 `char_traits<char>::eof()` 是 `int` 的 −1，而不是像 `char8_t` 那样用无符号 `int_type`？"

<details markdown="1">
<summary>展开查看答案与解析</summary>

历史兼容：`char` 流要与 C 的 `getc`/`EOF` 体系对齐，C 规定 `EOF` 是负的 `int`，`getc` 返回 `unsigned char` 转成的 `int`。`char_traits<char>` 只是把这套约定搬了过来（¶3 直接写 "returns `EOF`"）。`char8_t` 是 C++20 的新类型，没有包袱，所以选了 `unsigned int`，EOF 只需是一个不在 0–255 内的值。

</details>

## 小结

| 主题 | 规则 |
|---|---|
| 作用 | 把字符的比较、复制、长度、EOF 表示从字符类型中分离出来 |
| `char_type` 不匹配 | 非良构（¶3） |
| 异常 | 要求表中的表达式一律不得抛出 |
| `copy` vs `move` | `copy` 要求不重叠（否则 UB），`move` 允许重叠 |
| `char` 比较 | 按 `unsigned char`，与 `memcmp` 一致、与平台无关 |
| `int_type` | 需容纳所有字符外加 EOF；`char16_t` 实际放不下，libc++ 的 EOF 与 U+FFFF 冲突 |
| `comparison_category` | 标准特化为 `strong_ordering`；自定义 traits 缺省时 `<=>` 用 `weak_ordering` |
| 非字符类型 | 主模板无定义，用户也不能为 `unsigned char` 特化 `std::char_traits`；须自写 traits |
