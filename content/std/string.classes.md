---
title: 字符串类
summary: <string> 中 basic_string 成员以外的部分：类型别名、operator+、比较、输入输出、erase、stoi 与 to_string、hash 和 ""s 字面量。
status: done
covers: string.classes.general, string.syn, string.nonmembers, string.op.plus, string.cmp, string.special, string.io, string.erasure, string.conversions, basic.string.hash, basic.string.literals
papers: P2591R5, P2587R3, P1614R2, P1209R0, P0254R2
related: strings, basic.string, string.view, char.traits, charconv, format, format.string.std, unord.hash, over.match.oper, lex.string, over.literal, istream.formatted.reqmts
tags: 标准库, string, operator+, to_string, stoi, 字面量
updated: 2026-10-19
---

!!! tldr
    - `a + b + c + d` 只在第一步创建新字符串，之后的 `+` 都接管左边那个临时对象的缓冲区继续追加。
    - C++26 起 `string + string_view` 可以直接编译；`"abc" + "def"` 仍然非良构，`"abc" + 1` 则是指针运算。
    - `>>` 跳过前导空白、读到空白为止；`getline` 不跳过空白，读走换行符但不存储。两者混用时 `getline` 常常读到一个空行。
    - `stoi` 一族按 C 的 `strtol` 解释字符串：跳过前导空白，遇到非数字就停下而不报错，`stoul("-1")` 不抛异常。
    - C++26 起 `to_string(double)` 定义为 `format("{}", val)`，`to_string(0.1)` 从 `"0.100000"` 变成 `"0.1"`。

`basic_string` 的成员函数见 [[basic.string]]，本页讲 `<string>` 中的其余内容。

## 头文件 <string> [string.classes.general]

[string.classes.general] ¶1 `<string>` 定义类模板 `basic_string` 和五个别名：

| 别名 | 类型 |
|---|---|
| `string` | `basic_string<char>` |
| `u8string` | `basic_string<char8_t>`（C++20） |
| `u16string` | `basic_string<char16_t>` |
| `u32string` | `basic_string<char32_t>` |
| `wstring` | `basic_string<wchar_t>` |

[string.syn] 中还有几点值得知道：

- `namespace pmr` 中有一组同名别名，使用 `polymorphic_allocator<charT>`，例如 `std::pmr::string`。
- `<string>` 同时声明 `char_traits` 的主模板和五个特化（[[char.traits]]），它们在独立实现中也提供；`basic_string` 本身不是。
- `<string>` 包含 `<compare>` 和 `<initializer_list>`。
- 数值转换函数只为 `string` 和 `wstring` 提供，`u8string`、`u16string`、`u32string` 没有。
- 整数版本的 `to_string`、`to_wstring` 是 `constexpr` 的，浮点版本不是。

## 拼接 [string.op.plus]

### 右值重载复用缓冲区

```cpp run ok
#include <string>
#include <cstdio>
#include <cstdlib>
#include <new>

static int allocs = 0;
void* operator new(std::size_t n) {
  ++allocs;
  if (void* p = std::malloc(n)) return p;
  throw std::bad_alloc{};
}
void operator delete(void* p) noexcept { std::free(p); }
void operator delete(void* p, std::size_t) noexcept { std::free(p); }

int main() {
  std::string a(30, 'a'), b(30, 'b'), c(30, 'c'), d(30, 'd');
  allocs = 0;
  std::string r = a + b + c + d;            // ((a + b) + c) + d
  std::printf("%d allocations\n", allocs);  // 本机 libc++：2
}
```

`a + b + c + d` 按左结合解析为 `((a + b) + c) + d`。`a + b` 产生一个临时字符串，之后每一次 `+` 的左操作数都是右值，于是选中接受 `basic_string&&` 的重载：直接在这个临时对象上追加，再把它移动出去作为结果。整个表达式只有一个缓冲区在增长。

本机 libc++ 一共分配两次：`a + b` 一次，追加 `c` 时容量不够又增长一次，增长后的容量足以放下 `d`。如果没有右值重载，每个 `+` 都要分配一个新字符串。

概要中一共有 16 个 `operator+` 重载。下表中 `S` 是 `basic_string<charT, traits, Allocator>`，`SV` 是 `type_identity_t<basic_string_view<charT, traits>>`：

| 左操作数 | 右操作数 | 效果 |
|---|---|---|
| `const S&` | `const S&` 或 `const charT*` | ¶1 复制 `lhs`，再追加 |
| `S&&` | `const S&` 或 `const charT*` | ¶2 `lhs.append(rhs); return std::move(lhs);` |
| `S&&` | `S&&` | ¶3 同上，但两个操作数都处于有效但未指定的状态 |
| `const S&` 或 `const charT*` | `S&&` | ¶4 `rhs.insert(0, lhs); return std::move(rhs);` |
| `const charT*` | `const S&` | ¶5 复制 `rhs`，在开头插入 |
| `charT` | `const S&` 或 `S&&` | ¶6–¶7 在开头插入一个字符 |
| `const S&` 或 `S&&` | `charT` | ¶8–¶9 `push_back` |
| `const S&` 或 `S&&` | `SV` | ¶10–¶11 追加 {{c++26}} |
| `SV` | `const S&` 或 `S&&` | ¶12–¶13 在开头插入 {{c++26}} |

¶3 中两个操作数都是右值时，注 1 指出，如果两者的分配器相等，实现可以从任何一个移动。例如右边的容量更大时，在右边开头插入可能比在左边追加更省。所以标准规定两者都处于有效但未指定的状态，不能假定右操作数没有被动过。

### 与 string_view 拼接 {{c++26}}

```cpp run ok
#include <string>
#include <string_view>
#include <cassert>
using namespace std::literals;

int main() {
  std::string s = "hello";
  std::string r = s + " "sv + "world";   // C++26：string + string_view
  assert(r == "hello world");
}
```

¶10–¶13 由 [[P2591R5]] 加入。在此之前 `str + sv` 不能编译：没有对应的重载，`string_view` 也不能隐式转换为 `string`（[[P0254R2]] 的设计，见 [[basic.string]]）。只能写 `str + std::string(sv)`，多一次分配。本机 libc++ 已经支持新重载。

¶14 视图一侧的形参包了一层 `type_identity_t`，与 [[string.view]] 的比较运算符是同一个技巧：`charT`、`traits`、`Allocator` 只从 `basic_string` 一侧推导，另一侧可以是任何能隐式转换为 `basic_string_view<charT, traits>` 的类型。

### 容易出错的写法

- `"abc" + "def"` 非良构：两个数组都退化为指针，指针不能相加（[[expr.add]]）。
- `"abc" + 1` 合法，结果是指向 `"bc"` 的指针，所以 `std::string s = "abc" + 1;` 得到 `"bc"`。Clang 默认给出 `-Wstring-plus-int` 警告。
- `s + 'a' + 'b'` 没有问题；`'a' + 'b' + s` 先算 `'a' + 'b'`，得到整数 195，再找 `int + string`，`charT` 推导失败，非良构。
- 两个 `std::string_view` 之间仍然没有 `+`。

## 比较与 swap

[string.cmp] C++20 起只有 `==` 和 `<=>` 两个运算符模板，各有 `(const S&, const S&)` 和 `(const S&, const charT*)` 两个版本（[[P1614R2]]）。`!=`、`<`、反方向的 `const charT* == S` 等都由重写候选得到（[[over.match.oper]]）。

¶1 它们都等价于先把两边转换为 `basic_string_view` 再比较，所以语义完全由 [[string.view]] 和 [[char.traits]] 决定：`std::string` 的 `<` 按 `unsigned char` 比较字符，`<=>` 的结果类型是 `strong_ordering`。`S == S` 是 `noexcept` 的，`S == const charT*` 不是，因为指针必须指向以空字符结尾的序列，这是前置条件。

[string.special] ¶1 非成员 `swap` 等价于 `lhs.swap(rhs)`。分配器不相等又不传播时是 {{ub}}（见 [[basic.string]]）。

## 输入输出 [string.io]

```cpp run ok
#include <sstream>
#include <string>
#include <cassert>

int main() {
  std::istringstream in("  hello world\nsecond line\n");
  std::string w, l;
  in >> w;               // "hello"：跳过前导空白，停在空格前
  std::getline(in, l);   // " world"：从 hello 后面接着读到行尾
  assert(w == "hello" && l == " world");
}
```

### operator>>

¶1–¶3 `>>` 是格式化输入函数（[[istream.formatted.reqmts]]），构造 sentry 时默认跳过前导空白。sentry 成功后，它先清空 `str`，然后逐个提取字符并追加，直到下面任何一种情况发生：

- 已存储 `n` 个字符。`is.width()` 为正时 `n` 就是它，否则是 `str.max_size()`；
- 输入到达文件尾；
- 下一个字符 `c` 满足 `isspace(c, is.getloc())`，这个字符不提取。

之后调用 `is.width(0)`。一个字符都没提取时设置 `failbit`。

### getline

¶6–¶8 `getline(is, str, delim)` 是非格式化输入函数，但不影响 `gcount()`。构造 sentry 时不跳过空白。它先清空 `str`，然后提取字符，按顺序检查（¶7 规定了这个顺序）：

1. 输入到达文件尾；
2. 下一个字符等于 `delim`，这个字符提取但不存储；
3. 已存储 `str.max_size()` 个字符，此时设置 `failbit`。

只有一个字符都没提取时才设置 `failbit`。空行 `"\n"` 中的换行符被提取了，所以 `getline` 成功，得到空字符串。上面的例子说明了 `>>` 和 `getline` 混用的常见问题：`>>` 不提取后面的空白和换行，紧接着的 `getline` 读到的是这一行剩下的部分。

`getline` 也有接受 `basic_istream&&` 的重载，`std::getline(std::istringstream(text), line)` 可以直接作用于临时流。¶10 不带 `delim` 的版本以 `is.widen('\n')` 为分隔符。

¶5 `operator<<` 等价于 `os << basic_string_view<charT, traits>(str)`，按长度输出，中间的空字符也会写出去。

## erase 与 erase_if [string.erasure]

```cpp
template<class charT, class traits, class Allocator, class U = charT>
  constexpr size_type erase(basic_string<charT, traits, Allocator>& c, const U& value);
template<class charT, class traits, class Allocator, class Predicate>
  constexpr size_type erase_if(basic_string<charT, traits, Allocator>& c, Predicate pred);
```

¶1–¶2 C++20 加入（[[P1209R0]]），效果就是 erase-remove 惯用法，返回删除的字符个数。它用 `remove` 算法比较字符，即用 `operator==`，而不是 `traits::eq`；对自定义 traits 的字符串，两者可能不一致。

`U` 的默认模板实参 `charT` 是 C++26 加入的，让 `std::erase(s, {})` 这样的花括号实参也能推导。截至写作时，本机 libc++ 还没有实现这个默认实参，`std::erase(s, {})` 编译失败。

## 数值转换 [string.conversions]

### stoi 一族

```cpp
int stoi(const string& str, size_t* idx = nullptr, int base = 10);
// stol、stoul、stoll、stoull 形式相同
```

¶1 `stoi` 和 `stol` 调用 `strtol(str.c_str(), ptr, base)`，其余三个分别调用 `strtoul`、`strtoll`、`strtoull`。`idx` 非空时，存入第一个未转换字符的下标。¶3 `strto*` 报告无法转换时抛 `invalid_argument`；把 `errno` 设为 `ERANGE`，或者结果超出返回类型的范围时，抛 `out_of_range`。

语义完全来自 C 的 `strtol` 一族，C 的行为也一并继承了。本机实测：

| 调用 | 结果 | 原因 |
|---|---|---|
| `stoi("  42abc", &idx)` | 42，`idx == 4` | 跳过前导空白；遇到非数字停下，不报错 |
| `stoi("abc")` | 抛 `invalid_argument` | 无法转换 |
| `stoi("3000000000")` | 抛 `out_of_range` | 64 位 `long` 能表示，但超出 `int`，由超出返回类型范围这一条处理 |
| `stoul("-1")` | `ULONG_MAX` | `strtoul` 接受负号，结果按无符号取负 |
| `stoi("0x1f", nullptr, 16)` | 31 | 基数 16 接受 `0x` 前缀 |
| `stoi("0x1f", nullptr, 0)` | 31 | 基数 0 按前缀判断进制 |
| `stoi("1'000")` | 1 | 不认识数字分隔符 |

`strtol` 判断空白时依赖当前的 C locale，并且会读写 `errno`。需要不分配内存、不抛异常、不受 locale 影响、明确报告失败位置的转换，用 `std::from_chars`（[[charconv]]）。

¶4–¶6 `stof`、`stod`、`stold` 调用 `strtof`、`strtod`、`strtold`，`errno == ERANGE` 时抛 `out_of_range`。这包括下溢：C 标准允许 `strtod` 在结果是次正规数时设置 `ERANGE`，是否设置由实现决定。本机（macOS 的 C 库）上 `std::stod("1e-310")` 抛 `out_of_range`，尽管 `1e-310` 能用 `double` 的次正规数表示。

¶8–¶13 接受 `wstring` 的版本调用 `wcstol` 等宽字符函数，规定相同。

### to_string 的语义变更 {{c++26}}

¶7 当前草案中 `to_string(val)` 返回 `format("{}", val)`，¶14 `to_wstring` 返回 `format(L"{}", val)`。C++26 之前，`to_string` 定义为如同用 `sprintf` 配合 `%d`、`%f` 等格式。整数的结果不变，浮点数完全不同：

| 调用 | C++23（`%f`） | C++26（`format("{}")`） |
|---|---|---|
| `to_string(0.1)` | `"0.100000"` | `"0.1"` |
| `to_string(1e-7)` | `"0.000000"` | `"1e-07"` |
| `to_string(1e20)` | `"100000000000000000000.000000"` | `"1e+20"` |

旧的 `%f` 固定输出六位小数，很小的数变成 `0.000000`，很大的数输出一长串数字，小数点字符还受全局 C locale 影响。新语义（[[P2587R3]]）使用 `format` 的默认格式，即能精确往返的最短表示（[[format.string.std]]、[[charconv]]），并且与 locale 无关。旧代码不会因此编译失败，只是输出变了。

!!! impl "实现状态"
    截至写作时，本机 libc++（LLVM 23）还没有实现 [[P2587R3]]：`to_string(0.1)` 返回 `"0.100000"`，`to_string(1e-7)` 返回 `"0.000000"`，`to_string(1e20)` 返回 `"100000000000000000000.000000"`。整数版 `to_string` 也还不是 `constexpr`，在常量表达式中调用会报错。

## 哈希 [basic.string.hash]

五个 `hash` 部分特化的形式是 `hash<basic_string<charT, char_traits<charT>, A>>`，对任意分配器 `A` 都有效，所以 `std::pmr::string` 也能直接放进 `unordered_set`。¶1 是唯一的规范要求：

!!! std
    If `S` is one of these string types, `SV` is the corresponding string view type, and `s` is an object of type `S`, then `hash<S>()(s) == hash<SV>()(SV(s))`.

这条等式使得可以用 `string_view` 查找 `unordered_map<string, V>` 而不构造临时 `string`，例子见 [[string.view]]。自定义 traits 的 `basic_string` 没有标准的 `hash` 特化。

## ""s 字面量 [basic.string.literals]

```cpp run ok
#include <string>
#include <cassert>
using namespace std::literals;

int main() {
  std::string a = "a\0b";     // const char* 构造：遇到 '\0' 截断
  auto b = "a\0b"s;            // 字面量运算符：长度 3
  assert(a.size() == 1 && b.size() == 3);
}
```

¶1–¶5 `operator""s(const charT* str, size_t len)` 返回 `basic_string{str, len}`，在 `std::literals::string_literals` 中。长度来自字面量本身，所以中间的空字符会保留。

¶6 的注说明，`s` 后缀也用于 `chrono::duration` 表示秒，但两者不冲突：duration 的后缀作用于数字字面量，字符串的后缀作用于字符串字面量，两个字面量运算符的形参列表不同（[[over.literal]]）。

`""s` 产生的是临时 `string`，所以 `std::string_view v = "abc"s;` 立即悬垂；`std::string_view v = "abc";` 或 `"abc"sv` 才是安全的（[[string.view]]）。

## 历史

!!! history
    - C++11 加入 `stoi` 一族和 `to_string`，`to_string` 当时定义为 `sprintf` 的格式。
    - C++20：比较运算符改为 `==` 和 `<=>`（[[P1614R2]]）；加入 `erase` 和 `erase_if`（[[P1209R0]]）；加入 `u8string`。
    - C++26：`string` 与 `string_view` 直接拼接（[[P2591R5]]）；`to_string` 改为 `format("{}")`（[[P2587R3]]）。

## 思考题

!!! question "思考题 1"
    `std::string s = "x"; s = s + "y" + s;` 中，第二个 `+` 选中哪个重载？结果是什么？

<details markdown="1">
<summary>答案</summary>

`s + "y"` 选中 `(const S&, const charT*)`，产生临时字符串 `"xy"`。第二个 `+` 的左操作数是这个右值，右操作数是左值 `s`，选中 `(S&&, const S&)`（¶2），在临时对象上追加 `s`，得到 `"xyx"`，再移动赋值给 `s`。右操作数 `s` 在追加时只是被读取，没有问题。
</details>

!!! question "思考题 2"
    文件内容是 `"42\nhello\n"`。先 `in >> n;` 读一个 `int`，再 `std::getline(in, line);`，`line` 是什么？怎样改才能读到 `"hello"`？

<details markdown="1">
<summary>答案</summary>

`line` 是空字符串。`>>` 读完 `42` 后停在换行符前，`getline` 立即遇到分隔符，提取它、不存储，返回空串，并且不设置 `failbit`（[[string.io#6]]）。可以在 `getline` 前调用 `in.ignore(std::numeric_limits<std::streamsize>::max(), '\n')` 跳过这一行的剩余部分，或者用 `std::getline(in >> std::ws, line)` 跳过空白。
</details>
