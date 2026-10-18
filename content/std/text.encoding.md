---
title: 文本编码识别
summary: C++26 的 std::text_encoding——以 IANA 字符集注册表为基础的编码“身份证”：MIB 枚举 id、按 UTS #22 规则宽松比较的名字、aliases_view；consteval 的 literal() 与运行期的 environment() 分别回答“字面量用什么编码”和“运行环境用什么编码”；它只识别编码，不做转码
status: draft
covers: *
since: c++26
papers: P1885R12
related: text, lex.charset, character.seq, localization, locale.members, c.locales, unord.hash
tags: 标准库, 编码, text_encoding, C++26, Unicode
updated: 2026-10-18
---

在 C++26 之前，一个程序想知道“我的字符串字面量是什么编码”“当前终端/系统用什么编码”，只能靠编译器宏、`nl_langinfo(CODESET)`、`GetACP()` 之类的平台接口，而且各家返回的名字五花八门（`UTF-8`、`utf8`、`65001`……）。`<text_encoding>`（[[P1885R12]]）把这件事标准化了：

- 用 **IANA Character Sets 注册表**作为编码的命名空间，每个注册编码有一个 MIB 号（如 UTF-8 是 106），对应枚举 `text_encoding::id`；
- 名字比较采用 Unicode UTS #22 的“Charset Alias Matching”宽松规则，`"UTF-8"`、`"utf8"`、`"u.t.f-008"` 视为同一个；
- 提供两个查询点：`literal()`（编译期，普通字面量编码，见 [[lex.charset]]）和 `environment()`（运行期，执行环境编码，见 [[character.seq]]），另有 `std::locale::encoding()`（[[locale.members#7]]）。

它**只识别、不转码**：标准库依旧没有 Unicode 转码设施（`<codecvt>` 已在 C++26 删除，见 [[text]]）。

## 概要与类的形状（[text.encoding.syn]、[text.encoding.overview]）

`<text_encoding>` 只声明 `struct text_encoding` 和 `hash<text_encoding>` 特化。类的“仅供说明”成员揭示了它的实现模型：

```cpp
struct text_encoding {
  static constexpr size_t max_name_length = 63;
  enum class id : int_least32_t { /* 见下 */ };
  using enum id;                       // 所以可以写 text_encoding::UTF8
  // ...
private:
  id   mib_ = id::unknown;                     // exposition only
  char name_[max_name_length + 1] = {0};       // exposition only
};
```

也就是说，一个 `text_encoding` 对象就是“一个 MIB 号 + 一个最长 63 字符的名字”，**内嵌存储、没有动态分配**。[text.encoding.overview]/2 规定它是平凡可复制类型（[[basic.types.general]]），因此可以放进共享内存、`memcpy`、做 `constexpr` 变量。`using enum id;`（[[enum.udecl]]）把所有枚举器引入类作用域，于是 `text_encoding::UTF8` 与 `text_encoding::id::UTF8` 是同一个东西。

## 注册编码、别名与不变式（[text.encoding.general]）

**¶1**：[[g:registered-character-encoding]] 是 IANA 注册表里的字符编码方案；注 1 提醒，IANA 把它们叫 “character sets”，但实际指的是编码。注册表里给出的名字称为**主名**（*primary name*）。

**¶2**：“已知注册编码”是注册表里除 NATS-DANO（33）和 NATS-DANO-ADD（34）之外的所有编码——这两个在枚举里没有对应项，所以 `id` 的值从 32 直接跳到 35。

**¶3–¶4**：每个已知注册编码对应一个 `id` 枚举器，并有一组**别名**。别名集合是 IANA 列出的别名的**由实现定义的超集**（{{impl}}），但标准额外要求 US-ASCII 的别名包含 `"ASCII"`；且任意两个不同编码的主名/别名，在 *comp-name* 比较下都不相等——保证按名字查找结果唯一。

**¶5**：一个 `text_encoding` 对象如何被认定“代表”翻译环境或执行环境中实现的某个编码方案，是由实现定义的。

**¶6** 给出不变式：只要 `mib()` 既不是 `unknown` 也不是 `other`，则

- `name()` 非空（¶6.1）；
- `text_encoding(e.name()).mib() == e.mib()`（¶6.2）——名字能“往返”回同一个 MIB。

**¶7**（Recommended practice）：实现不应把不同的注册编码视为可互换（例 1：Shift_JIS 与 Windows-31J 是两个编码）；也不应拿某个注册编码的名字去描述一个相似但不同的非注册编码，除非该实现上已有先例（例 2：Big5——历史上各平台的 “Big5” 实际差异很大）。

## 成员（[text.encoding.members]）

### 从名字构造（¶1–¶2）

```cpp
constexpr explicit text_encoding(string_view enc) noexcept;
```

*Preconditions*（违反即 {{ub}}）：`enc` 是用普通字面量编码表示的、只含基本字符集（[[lex.charset]]）字符的字符串；长度不超过 63；不含 `'\0'`。

*Postconditions*：如果存在某个已知注册编码的主名或别名 `a` 使 *comp-name*`(a, enc)` 为真，`mib_` 取该编码的枚举值；否则 `mib_ == id::other`。无论哪种情况，**`name_` 保存的都是 `enc` 原样的拷贝**（¶2.2）——不是规范化后的主名。所以 `text_encoding("u.t.f-008").name()` 返回 `"u.t.f-008"`，但 `mib()` 是 `UTF8`。

### 从 `id` 构造（¶3–¶4）

*Preconditions*：`i` 是某个枚举器的值（`id{9999}` 之类的“越界”值是 {{ub}}）。*Postconditions*：`mib_ == i`；若为 `unknown`/`other` 则名字为空，否则 `name()` 是该编码的某个别名（¶4.2 只要求 `ranges::contains(aliases(), name())`，并未规定一定是主名）。

### `mib()`、`name()`、`aliases()`（¶5–¶10）

- `name()` 返回 `name_`，是一个 [[g:ntbs]]；访问 `name()+[0, strlen(name())+1)` 之外的元素是 {{ub}}（¶7）——即使底层数组有 64 字节，也不许读终止符之后的部分。
- `aliases()` 返回 `aliases_view`：若 `*this` 代表已知注册编码，则 `front()` 是**主名**，范围包含全部别名且（按 `strcmp`）无重复；否则是空范围。别名顺序未指明（注 1）。每个元素都是非空、只含基本字符集字符的 ntbs（¶8）。

### `literal()`（¶11–¶12）

```cpp
static consteval text_encoding literal() noexcept;
```

*Mandates*：`CHAR_BIT == 8`。返回代表**普通字面量编码**（[[lex.charset]]）的对象。`consteval`（[[expr.const]] 意义上的立即函数）意味着它只能在常量求值中被调用——字面量编码本来就是翻译期属性。

!!! impl "libc++ 如何得知字面量编码"
    libc++ 的实现直接读取编译器预定义宏：GCC 的 `__GNUC_EXECUTION_CHARSET_NAME`，或 Clang 的 `__clang_literal_encoding__`（本机 clang 23 为 `"UTF-8"`）；两者都不存在时返回默认构造的 `text_encoding`（`unknown`）。

### `environment()` 与 `environment_is<i>()`（¶13–¶18）

*Mandates*：`CHAR_BIT == 8`。返回代表执行环境编码方案的对象，具体是什么由实现定义；**在 POSIX 实现上，是空字符串 `""` 所指 POSIX locale 关联的编码**——也就是由 `LC_ALL`/`LC_CTYPE`/`LANG` 环境变量决定的那个。

!!! std
    This function is not affected by calls to setlocale.

注 2：它不受 `setlocale` 影响。¶16（Recommended practice）进一步建议：返回值也不应受 POSIX `setenv` 等修改环境的函数影响。

`environment_is<i>()` 返回 `environment() == i`。把 `id` 作为模板实参，是为了让实现可以针对常见编码做免查表的快速路径。

!!! impl "libc++ 23 没有遵循 ¶16 的建议"
    libc++ 每次调用 `environment()` 都重新用 `""` 构造 POSIX locale 并查询其编码，因此程序运行中途 `setenv("LC_ALL", "en_US.UTF-8", 1)` 之后，`environment()` 的结果会从 `US-ASCII` 变为 `UTF-8`（本机实测）。¶16 只是 *Recommended practice*，不具强制力，所以这不算不符合标准，但移植时不要依赖任一行为。另外，在 Android 上 libc++ 的 `environment_is` 直接比较 `UTF8`；在 macOS 上 `environment()` 需要 LLVM 23 的 libc++ 动态库（可用性标注见 [[text]]）。

### *comp-name*：UTS #22 名字匹配（¶19）

两个名字相等，当且仅当从左到右忽略以下内容后相同：

1. 所有非字母、非数字的字符（¶19.1）；
2. 大小写（¶19.2）；
3. 任何**不紧跟在数字前缀之后**的连续 `0`——数字前缀指 1–9 中的一个数字，可选地跟着若干非字母数字字符（¶19.3）。

第 3 条就是 UTS #22 的“去前导零”规则：`utf-008` 中的 `00` 前面是 `-`，而 `-` 前面是 `f`，不构成数字前缀，于是被忽略，得到 `utf8`；而 `utf-80` 的 `0` 紧跟在数字 `8` 后面，保留，得到 `utf80`。标准例 1：

| a | b | 结果 |
|---|---|---|
| `"UTF-8"` | `"utf8"` | true |
| `"u.t.f-008"` | `"utf8"` | true |
| `"ut8"` | `"utf8"` | false |
| `"utf-80"` | `"utf8"` | false |

## 比较（[text.encoding.cmp]）

- 两个 `text_encoding` 比较（¶1）：若两者都是 `other`，则用 *comp-name* 比较**名字**；否则只比较 MIB。因此两个都叫 `"x-my-enc"`/`"X_MY_ENC"` 的未注册编码相等；而 `text_encoding("utf8") == text_encoding(text_encoding::UTF8)`，尽管名字不同。
- 与 `id` 比较（¶2）：只比较 MIB。¶3 指出：当 `i == id::other` 时，这个运算符**不是**等价关系——`a == other` 和 `b == other` 都为真，并不意味着 `a == b`（名字可能不同）。

## `aliases_view`（[text.encoding.aliases]）

¶1：它是 `copyable` 的 `view`、`random_access_range` 和 `borrowed_range`——别名字符串存放在静态表里，视图销毁后迭代器仍然有效。注 1 特别指出它**不要求**是 `common_range`，也不要求可默认构造。¶2：值类型和引用类型都是 `const char*`。¶3：迭代器是 constexpr 迭代器，所以可以在常量表达式里遍历别名。

## 枚举 `id` 与散列（[text.encoding.id]、[text.encoding.hash]）

`id` 的底层类型是 `int_least32_t`；`other = 1`、`unknown = 2`，其余枚举值就是 IANA 的 MIB 号（`ASCII = 3`、`UTF8 = 106`、`UTF16 = 1015`、`GB18030 = 114`、`windows1252 = 2252` 等）。注 1 说明命名规则：取 IANA 中以 `cs` 开头的别名并去掉前缀；两个例外是 `csUnicode` → `UCS2`、`csIBBM904`（注册表里的拼写错误）→ `IBM904`。

[text.encoding.hash]：`hash<text_encoding>` 是启用的（[[unord.hash]]），可直接作为 `unordered_set`/`unordered_map` 的键。

## 示例

```cpp run title="text-encoding.cpp" ok
#include <algorithm>
#include <cassert>
#include <cstring>
#include <ranges>
#include <string_view>
#include <text_encoding>

int main() {
    using te = std::text_encoding;

    constexpr te a("u.t.f-008");
    static_assert(a.mib() == te::UTF8);                   // 宽松匹配
    static_assert(std::string_view(a.name()) == "u.t.f-008"); // 名字原样保存

    te b("x-my-enc"), c("X_MY_ENC");
    assert(b.mib() == te::other && b == c);               // 都是 other：按名字比较
    assert(b == te::other && !(b == te("x-other")));      // == other 不是等价关系

    te sjis(te::ShiftJIS);
    assert(sjis != te(te::Windows31J));                   // 不可互换的两个注册编码
    assert(std::strcmp(sjis.aliases().front(), "Shift_JIS") == 0);  // front() 是主名

    auto ascii = te(te::ASCII).aliases();
    assert(std::ranges::contains(ascii, std::string_view("ASCII")));  // ¶4 要求的别名

    te u;                                                 // 默认构造
    assert(u.mib() == te::unknown && *u.name() == '\0');
}
```

!!! pitfall "别名列表是由实现定义的超集"
    除 `"ASCII"` 之外，不要假设某个别名一定存在；用名字构造时，一个在 A 实现上识别为注册编码的别名，在 B 实现上可能只得到 `other`。跨平台交换编码信息时，优先传 MIB 号（`to_underlying(e.mib())`）或主名（`aliases().front()`）。

## 小结

| 接口 | 求值时机 | 回答的问题 |
|---|---|---|
| `text_encoding::literal()` | `consteval` | 普通字面量用什么编码？（[[lex.charset]]） |
| `text_encoding::environment()` | 运行期 | 进程环境用什么编码？（POSIX：`""` locale；不受 `setlocale` 影响） |
| `std::locale::encoding()` | 运行期 | 这个 `std::locale` 对象用什么编码？（[[locale.members]]） |
| `text_encoding(string_view)` | `constexpr` | 这个名字对应哪个注册编码？未注册则 `other` |
