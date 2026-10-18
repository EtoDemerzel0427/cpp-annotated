---
title: 字符串类
summary: <string> 头文件中 basic_string 类模板之外的一切——概要与五个别名、pmr 别名；operator+ 的十六个重载为什么有一半接受右值（以及 C++26 加入的 string_view 拼接）；只有 == 与 <=> 的比较；operator>>/getline 的精确语义；erase/erase_if；stoi 族的 strtol 语义与陷阱、to_string 在 C++26 改为 format("{}")；hash 与 string_view 一致；""s 字面量
status: done
covers: string.classes.general, string.syn, string.nonmembers, string.op.plus, string.cmp, string.special, string.io, string.erasure, string.conversions, basic.string.hash, basic.string.literals
papers: P2591R5, P2587R3, P1614R2, P1209R0, P0254R2
related: strings, basic.string, string.view, char.traits, charconv, format, format.string.std, unord.hash, over.match.oper, lex.string, over.literal, istream.formatted.reqmts
tags: 标准库, string, operator+, to_string, stoi, 字面量
updated: 2026-10-18
---

[string.classes] 的主体是类模板 `basic_string`，它的成员函数在 [[basic.string]] 中逐条讲解。本页覆盖剩下的部分：头文件概要、非成员函数（拼接、比较、交换、I/O、擦除）、数值转换、哈希和 `""s` 字面量。

## 概述与概要（[string.classes.general]、[string.syn]）

[string.classes.general] ¶1：`<string>` 定义 `basic_string` 与五个 *typedef-name*：

| 别名 | 类型 |
|---|---|
| `string` | `basic_string<char>` |
| `u8string` | `basic_string<char8_t>`（C++20） |
| `u16string` | `basic_string<char16_t>` |
| `u32string` | `basic_string<char32_t>` |
| `wstring` | `basic_string<wchar_t>` |

[string.syn] 的概要里还有几个容易忽略的事实：

- `<string>` 同时声明了 `char_traits` 的主模板和五个特化（[[char.traits]]），并且它们是 *freestanding* 的；`basic_string` 本身不是。
- `<string>` 必须包含 `<compare>` 和 `<initializer_list>`。
- `namespace pmr` 中有 `basic_string` 别名模板与五个别名，使用 `polymorphic_allocator<charT>`。
- 数值转换函数只为 `string` 和 `wstring` 提供，没有 `u8string`/`u16string`/`u32string` 版本。
- 整数版本的 `to_string`/`to_wstring` 在当前草案里是 `constexpr`，浮点版本不是。

## `operator+`（[string.op.plus]）

概要中一共有 16 个 `operator+` 重载。按左右操作数分类：

| 左 | 右 | 定义（¶） |
|---|---|---|
| `const S&` | `const S&` 或 `const charT*` | 复制 `lhs` 再 `append`（¶1） |
| `S&&` | `const S&` 或 `const charT*` | `lhs.append(rhs); return std::move(lhs);`（¶2） |
| `S&&` | `S&&` | 同上，但两者都处于有效但未指明状态（¶3） |
| `const S&` 或 `const charT*` | `S&&` | `rhs.insert(0, lhs); return std::move(rhs);`（¶4） |
| `const charT*` | `const S&` | 复制 `rhs` 再在开头插入（¶5） |
| `charT` | `const S&` / `S&&` | 在开头插入一个字符（¶6–7） |
| `const S&` / `S&&` | `charT` | `push_back`（¶8–9） |
| `const S&` / `S&&` | `string_view` | 追加（¶10–11）{{c++26}} |
| `string_view` | `const S&` / `S&&` | 在开头插入（¶12–13）{{c++26}} |

（表中 `S` 是 `basic_string<charT, traits, Allocator>`，`string_view` 指 `type_identity_t<basic_string_view<charT, traits>>`。）

### 为什么一半重载接受右值

`a + b + c + d` 按左结合解析为 `((a + b) + c) + d`。第一次 `a + b` 产生一个临时 `string`（prvalue），之后的每一次 `+` 左操作数都是右值，于是选中 `S&&` 重载：直接在那个临时对象上 `append`，然后**把它移动出去**作为返回值。整个表达式只有一个缓冲区在不断增长，而不是每一步都分配一个新字符串。

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
  std::string r = a + b + c + d;          // (((a+b)+c)+d)
  std::printf("%d allocations\n", allocs); // 本机 libc++：2
}
```

本机 libc++ 实测两次分配：`a + b` 一次（60 个字符），`+ c` 时容量不够再增长一次（几何增长后的容量足以容纳 `+ d`）。如果没有右值重载，每个 `+` 都要分配一个新的结果字符串。

¶3 的 `S&& + S&&`：注 1 指出，若两个分配器相等，实现可以从**任何一个**移动——比如右边的容量更大时，往右边的开头插入可能比往左边追加更省。所以标准说两者都处于"有效但未指明状态"，不能假定右操作数没被动过。

### 与 `string_view` 拼接 {{c++26}}

¶10–13 由 [[P2591R5]] 加入。在此之前 `str + sv` 不能编译：既没有对应的重载，`string_view` 也不能隐式转换为 `string`（[[basic.string]]，[[P0254R2]] 的设计）。只能写 `str + std::string(sv)`，平白多一次分配。

新重载的 `string_view` 参数用 `type_identity_t` 包裹（¶14 的注），与 [[string.view]] 的比较运算符是同一个技巧：`charT`、`traits`、`Allocator` 只从 `basic_string` 那一侧推导，另一侧可以是任何能隐式转换为 `basic_string_view<charT, traits>` 的类型。

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

本机 libc++ 已支持。

### 陷阱

- `"abc" + "def"` 非良构：两个数组退化为指针，指针相加没有定义（[[expr.add]]）。
- `"abc" + 1` **合法**，结果是指向 `"bc"` 的指针；`std::string s = "abc" + 1;` 得到 `"bc"`（Clang 默认给出 `-Wstring-plus-int` 警告）。
- `s + 'a' + 'b'` 没问题；`'a' + 'b' + s` 先算 `'a' + 'b'`（整数 195），再找 `int + string`——`charT` 推导失败，非良构。
- `std::string_view` 与 `std::string_view` 之间仍然没有 `+`。

## 比较（[string.cmp]）

C++20 起只剩两个运算符模板，各有 `(const S&, const S&)` 与 `(const S&, const charT*)` 两个版本，其余（`!=`、`<`、反向的 `const charT* == S` 等）全部由重写候选生成（[[over.match.oper]]，[[P1614R2]]）。¶1：全部等价于先转换为 `basic_string_view` 再比较，所以语义完全由 [[string.view]] 与 [[char.traits]] 决定——`std::string` 的 `<` 按 `unsigned char` 比较，`<=>` 的结果类型是 `strong_ordering`。

注意 `S == S` 是 `noexcept` 的，`S == const charT*` 不是（后者有前置条件：指针必须指向以终止符结尾的序列）。

## `swap`（[string.special]）

¶1：等价于 `lhs.swap(rhs)`，`noexcept` 条件与成员版本一致。分配器不相等且不传播时是 {{ub}}（见 [[basic.string]]）。

## 输入输出（[string.io]）

### `operator>>`（¶1–4）

格式化输入函数（[[istream.formatted.reqmts]]）：构造 sentry（默认跳过前导空白），成功则先 `str.erase()`，然后逐个提取字符追加，直到以下之一发生：

- 已存储 `n` 个字符（`n` 是 `is.width()`，若为正；否则 `str.max_size()`）；
- 遇到文件尾；
- 下一个字符 `c` 满足 `isspace(c, is.getloc())`——**该字符不被提取**。

之后调用 `is.width(0)`。一个字符都没提取则设置 `failbit`。

### `getline`（¶6–10）

非格式化输入函数，但**不影响** `gcount()`。sentry 构造时**不跳过**空白。先 `str.erase()`，然后提取字符，按顺序检查（¶7："The conditions are tested in the order shown"）：

1. 文件尾；
2. 下一个字符等于 `delim`——**提取但不存储**；
3. 已存储 `str.max_size()` 个字符——设置 `failbit`。

一个字符都没提取（不是"没存储"）才设置 `failbit`。所以空行 `"\n"` 会成功返回空字符串，因为分隔符被提取了。

经典组合陷阱：`>>` 不提取结尾的空白/换行，紧接着的 `getline` 读到的是这一行剩下的部分：

```cpp run ok
#include <sstream>
#include <string>
#include <cassert>

int main() {
  std::istringstream in("  hello world\nsecond line\n");
  std::string w, l;
  in >> w;               // "hello"（跳过前导空白）
  std::getline(in, l);   // " world"：从 hello 之后接着读到行尾
  assert(w == "hello" && l == " world");
}
```

`getline` 有接受 `basic_istream&&` 的重载，所以 `std::getline(std::istringstream(text), line)` 能直接作用于临时流。

`operator<<`（¶5）：等价于 `os << basic_string_view<charT, traits>(str)`，按长度输出，内嵌的 `'\0'` 也会写出。

## 擦除（[string.erasure]）

C++20（[[P1209R0]]）加入的统一擦除接口：

```cpp
template<class charT, class traits, class Allocator, class U = charT>
  constexpr size_type erase(basic_string<charT, traits, Allocator>& c, const U& value);
template<class charT, class traits, class Allocator, class Predicate>
  constexpr size_type erase_if(basic_string<charT, traits, Allocator>& c, Predicate pred);
```

¶1–2：就是 erase-remove 惯用法，返回删除的元素个数。`U` 的默认模板实参 `charT` 让 `std::erase(s, {})` 这样的花括号实参也能推导。注意它比较元素用的是 `operator==`（`remove` 算法的语义），**不是** `traits::eq`——对自定义 traits 的字符串，两者可能不一致。

## 数值转换（[string.conversions]）

### `stoi` 族（¶1–3、¶8–10）

```cpp
int stoi(const string& str, size_t* idx = nullptr, int base = 10);
// stol、stoul、stoll、stoull 同形
```

¶1：`stoi` 与 `stol` 调用 `strtol(str.c_str(), ptr, base)`，其余分别调用 `strtoul`、`strtoll`、`strtoull`。¶3：`strto*` 报告无法转换时抛 `invalid_argument`；设置 `errno` 为 `ERANGE` **或**结果超出返回类型范围时抛 `out_of_range`。`idx` 非空时存入第一个未转换字符的下标。

因为语义完全来自 C 的 `strtol` 一族，所有 C 的怪癖都被继承了：

| 输入 | 结果 | 原因 |
|---|---|---|
| `stoi("  42abc", &idx)` | 42，`idx == 4` | 跳过前导空白；遇到非数字停止，**不报错** |
| `stoi("abc")` | 抛 `invalid_argument` | 无法转换 |
| `stoi("3000000000")` | 抛 `out_of_range` | `strtol` 能表示，但超出 `int`（这就是"或结果超出返回类型范围"那一句的用途） |
| `stoul("-1")` | `ULONG_MAX` | `strtoul` 接受负号，结果按无符号取反 |
| `stoi("0x1f", nullptr, 16)` | 31 | 基数 16 接受 `0x` 前缀 |
| `stoi("0x1f", nullptr, 0)` | 31 | 基数 0：按前缀自动识别 |
| `stoi("1'000")` | 1 | 不认识数字分隔符 |

`stoi` 族还受 C locale 影响（`strtol` 的"空白"判断依赖当前 C locale），并且在内部读写 `errno`。想要不分配、不抛异常、与 locale 无关、明确报告失败位置的转换，用 `std::from_chars`（[[charconv]]）。

### `stof`/`stod`/`stold`（¶4–6、¶11–13）

调用 `strtof`/`strtod`/`strtold`。`errno == ERANGE` 时抛 `out_of_range`——这包括**下溢**：C 标准允许 `strtod` 在结果为次正规数时设置 `ERANGE`（是否设置由实现定义）。本机（macOS libc）实测 `std::stod("1e-310")` 抛 `out_of_range`，尽管 `1e-310` 能用 `double` 的次正规数表示。

### `to_string`/`to_wstring`（¶7、¶14）：C++26 的语义变更

当前草案：

!!! std
    *Returns*: `format("{}", val)`.

C++26 之前，`to_string` 被定义为"如同用 `sprintf` 配合 `%d`/`%u`/`%ld`/…/`%f`/`%Lf`"。整数结果不变，但浮点完全不同：

| 调用 | C++23（`%f`） | C++26（`format("{}")`） |
|---|---|---|
| `to_string(0.1)` | `"0.100000"` | `"0.1"` |
| `to_string(1e-7)` | `"0.000000"` | `"1e-07"` |
| `to_string(1e20)` | `"100000000000000000000.000000"` | `"1e+20"` |

旧语义的 `%f` 固定输出六位小数：小数会被截成 `0.000000`，大数会输出一长串数字，而且受全局 C locale 的小数点字符影响。新语义（[[P2587R3]]）使用 `format` 的默认格式，即 `to_chars` 的最短往返表示（[[format.string.std]]、[[charconv]]），并且与 locale 无关。这是一个**静默的行为变更**：旧代码不会编译失败，只是输出变了。

!!! impl "实现状态"
    本机 libc++（LLVM 23）的 `to_string(0.1)` 仍返回 `"0.100000"`，`to_string(1e-7)` 返回 `"0.000000"`，即尚未实现 [[P2587R3]] 的新语义；整数版 `to_string` 也尚未是 `constexpr`（在常量表达式中调用会报"non-constexpr function"）。标准规定如此，但截至本文编写时编译器与标准库仍未跟进。

## 哈希（[basic.string.hash]）

五个部分特化 `hash<basic_string<charT, char_traits<charT>, A>>`——**对任意分配器 `A`**，所以 `std::pmr::string` 也能直接放进 `unordered_set`。¶1 是唯一的规范性要求：

!!! std
    If `S` is one of these string types, `SV` is the corresponding string view type, and `s` is an object of type `S`, then `hash<S>()(s) == hash<SV>()(SV(s))`.

这条等式让异构查找（用 `string_view` 查 `unordered_map<string, V>`）成为可能，示例见 [[string.view]]。自定义 traits 的 `basic_string` 没有标准 `hash` 特化。

## `""s` 字面量（[basic.string.literals]）

¶1–5：`operator""s(const charT* str, size_t len)` 返回 `basic_string{str, len}`，位于 `std::literals::string_literals`。由于长度来自字面量本身，内嵌的 `'\0'` 会被保留：

```cpp run ok
#include <string>
#include <cassert>
using namespace std::literals;

int main() {
  std::string a = "a\0b";     // const char* 构造：遇 '\0' 截断
  auto b = "a\0b"s;            // 字面量运算符：长度 3
  assert(a.size() == 1 && b.size() == 3);
}
```

¶6 的注：`s` 后缀也用于 `chrono::duration` 的秒，但两者不冲突——duration 的后缀作用于数字字面量，字符串的后缀作用于字符串字面量（字面量运算符的形参列表不同，[[over.literal]]）。

注意 `""s` 产生的是**临时** `string`：`std::string_view v = "abc"s;` 立即悬垂，而 `std::string_view v = "abc";` 或 `"abc"sv` 是安全的（[[string.view]]）。这些字面量运算符是 `constexpr` 的，但与 [[basic.string]] 所述相同，结果对象若涉及堆分配就不能成为 `constexpr` 变量。

## 小结

| 主题 | 规则 |
|---|---|
| 别名 | `string`/`u8string`/`u16string`/`u32string`/`wstring`，`pmr::` 版本用 `polymorphic_allocator` |
| `operator+` | 右值重载复用左（或右）操作数的缓冲区；C++26 起可直接与 `string_view` 拼接 |
| 比较 | 只有 `==` 与 `<=>`，转发给 `string_view`；其余由重写生成 |
| `>>` / `getline` | `>>` 跳过前导空白、止于空白；`getline` 不跳过、提取但不存储分隔符 |
| `erase`/`erase_if` | erase-remove，用 `operator==` 而非 `traits::eq` |
| `stoi` 族 | `strtol` 语义：跳空白、接受部分匹配、`stoul` 接受负数；失败抛 `invalid_argument`/`out_of_range` |
| `to_string` | C++26 改为 `format("{}")`（最短往返，与 locale 无关）；本机 libc++ 尚未实现 |
| `hash` | 与对应 `string_view` 相等，对任意分配器都有特化 |
| `""s` | 保留内嵌 `'\0'`；产生临时对象，不要绑定到 `string_view` |
