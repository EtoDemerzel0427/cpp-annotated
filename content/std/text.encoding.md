---
title: 文本编码识别
summary: C++26 的 std::text_encoding 以 IANA 字符集注册表为依据标识一种编码：MIB 编号、宽松比较的名字、别名列表；literal() 在编译期给出字面量编码，environment() 在运行时给出环境编码；它只识别编码，不做转换。
status: done
covers: *
since: c++26
papers: P1885R12
related: text, lex.charset, character.seq, localization, locale.members, c.locales, unord.hash
tags: 标准库, 编码, text_encoding, C++26, Unicode
updated: 2026-10-19
---

!!! tldr
    - `std::text_encoding` 是一个小的值类型：一个 IANA 注册编号（MIB）加一个最长 63 字符的名字，平凡可复制，不分配内存。
    - 名字按 Unicode UTS #22 的规则宽松比较，`"UTF-8"`、`"utf8"`、`"u.t.f-008"` 都对应 `text_encoding::UTF8`。
    - `literal()` 是 `consteval` 的，返回普通字面量编码；`environment()` 在运行时返回进程环境的编码，不受 `setlocale` 影响。
    - 未注册的名字得到 `id::other`；两个 `other` 按名字比较，其余情况只比较 MIB。
    - 它只识别编码，标准库仍然没有 Unicode 转码设施。

## 为什么需要它

在 C++26 之前，程序想知道字符串字面量是什么编码、运行环境用什么编码，只能借助编译器宏、`nl_langinfo(CODESET)`、`GetACP()` 之类的平台接口，得到的名字也五花八门：`UTF-8`、`utf8`、`65001`。

C++26 的 `<text_encoding>`（[[P1885R12]]）用 IANA Character Sets 注册表作为编码的统一命名：每个注册编码有一个 MIB 编号（UTF-8 是 106），对应枚举 `text_encoding::id` 的一个枚举器。它提供三个查询点：`literal()` 给出普通字面量编码（[[lex.charset]]），`environment()` 给出执行环境的编码（[[character.seq]]），`std::locale::encoding()` 给出某个 locale 的编码（[[locale.members#7]]）。这几种编码的区别见 [[text]]。

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
    static_assert(a.mib() == te::UTF8);                       // 宽松匹配
    static_assert(std::string_view(a.name()) == "u.t.f-008"); // 名字原样保存

    te b("x-my-enc"), c("X_MY_ENC");
    assert(b.mib() == te::other && b == c);               // 都是 other：按名字比较
    assert(b == te::other && !(b == te("x-other")));      // == other 不是等价关系

    te sjis(te::ShiftJIS);
    assert(sjis != te(te::Windows31J));                   // 不可互换的两个注册编码
    assert(std::strcmp(sjis.aliases().front(), "Shift_JIS") == 0);  // front() 是主名

    auto ascii = te(te::ASCII).aliases();
    assert(std::ranges::contains(ascii, std::string_view("ASCII")));  // 标准要求的别名

    te u;                                                 // 默认构造
    assert(u.mib() == te::unknown && *u.name() == '\0');
}
```

## 类的形状 [text.encoding.overview]

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

仅用于说明的成员表明了它的实现模型：一个 MIB 编号加一个内嵌的名字数组，没有动态分配。¶2 规定它是平凡可复制类型（[[basic.types.general]]），可以 `memcpy`，可以放进共享内存，也可以做 `constexpr` 变量。`using enum id;`（[[enum.udecl]]）把所有枚举器引入类作用域，`text_encoding::UTF8` 与 `text_encoding::id::UTF8` 是同一个值。

## 注册编码与别名 [text.encoding.general]

¶1 **注册字符编码**（[[g:registered-character-encoding|registered character encoding]]）是 IANA Character Sets 注册表中的字符编码方案。注 1 提醒，注册表把它们叫 character sets，实际指的是编码。注册表给出的名字叫这个编码的主名（primary name）。

¶2 已知的注册编码是注册表中除 NATS-DANO（33）和 NATS-DANO-ADD（34）之外的全部编码。这两个在枚举中没有对应项，所以枚举值从 32 直接跳到 35。

¶3–¶4 每个已知注册编码对应 `id` 的一个枚举器，并有一组别名。别名集合是 IANA 所列别名的一个超集，具体由实现定义（{{impl}}）。标准只额外要求 US-ASCII 的别名中有 `"ASCII"`，并保证不同编码的主名和别名在 *comp-name*（见下文）比较下互不相等，所以按名字查找的结果是唯一的。

¶5 一个 `text_encoding` 对象怎样被认定代表翻译环境或执行环境中的某种编码，由实现定义。

¶6 只要 `mib()` 既不是 `unknown` 也不是 `other`，就有两条不变式：`name()` 非空（¶6.1）；`text_encoding(e.name()).mib() == e.mib()`，即名字能映射回同一个 MIB（¶6.2）。

¶7 建议实现不要把不同的注册编码视为可以互换（例 1：Shift_JIS 与 Windows-31J 是两个编码）；也不要用某个注册编码的名字去描述一个相似但不同的未注册编码，除非该实现上已有先例（例 2：Big5，历史上各平台的 Big5 差异很大）。

## 构造与访问 [text.encoding.members]

### 从名字构造（¶1–¶2）

```cpp
constexpr explicit text_encoding(string_view enc) noexcept;
```

¶1 前置条件：`enc` 以普通字面量编码表示，只含基本字符集（[[lex.charset]]）的字符；长度不超过 63；不含 `'\0'`。违反任何一条都是 {{ub}}。

¶2 如果某个已知注册编码的主名或别名与 `enc` 按 *comp-name* 相等，`mib_` 取该编码的枚举值，否则 `mib_ == id::other`。无论哪种情况，`name_` 保存的都是 `enc` 原样的拷贝，而不是规范化后的主名。所以 `text_encoding("u.t.f-008").name()` 返回 `"u.t.f-008"`，`mib()` 却是 `UTF8`。

### 从 `id` 构造（¶3–¶4）

¶3 前置条件：`i` 是某个枚举器的值，`id{9999}` 这样的值是 {{ub}}。¶4 构造后 `mib_ == i`；`i` 为 `unknown` 或 `other` 时名字为空，否则 `name()` 是该编码的某个别名。标准只要求 `ranges::contains(aliases(), name())`，并没有规定一定是主名。

### `mib()`、`name()`、`aliases()`（¶5–¶10）

¶5–¶7 `mib()` 返回 `mib_`。`name()` 返回 `name_`，是一个 [[g:ntbs]]；访问 `name()+[0, strlen(name())+1)` 之外的元素是 {{ub}}，即使底层数组有 64 字节，也不能读结尾空字符之后的部分。

¶8–¶10 `aliases()` 返回一个 `aliases_view`。如果 `*this` 代表已知注册编码，它的 `front()` 是主名，范围包含全部别名，按 `strcmp` 没有重复；否则是空范围。每个元素都是非空、只含基本字符集字符的 ntbs，别名的顺序未指定（注 1）。

### `literal()`（¶11–¶12）

```cpp
static consteval text_encoding literal() noexcept;
```

¶11–¶12 要求 `CHAR_BIT == 8`，返回代表普通字面量编码的对象。它是 `consteval` 的立即函数，只能在常量求值中调用，因为字面量编码本来就是翻译时确定的属性。

!!! impl "libc++ 怎样得知字面量编码"
    libc++ 读取编译器的预定义宏：GCC 的 `__GNUC_EXECUTION_CHARSET_NAME`，或 Clang 的 `__clang_literal_encoding__`（本机 Clang 23 为 `"UTF-8"`）。两者都不存在时返回默认构造的 `text_encoding`，即 `unknown`。

### `environment()` 与 `environment_is<i>()`（¶13–¶18）

¶13–¶14 要求 `CHAR_BIT == 8`，返回代表执行环境编码的对象，具体是什么由实现定义。在 POSIX 实现上，它是空字符串 `""` 所表示的 POSIX locale 关联的编码，也就是由 `LC_ALL`、`LC_CTYPE`、`LANG` 环境变量决定的那个。

!!! std
    This function is not affected by calls to setlocale.

¶15 注 2：它不受 `setlocale` 影响。¶16 进一步建议，返回值也不应受 POSIX `setenv` 等修改环境的函数影响。

¶17–¶18 `environment_is<i>()` 返回 `environment() == i`。把 `id` 作为模板实参，实现就可以为常见编码提供不必查表的快速路径。

!!! impl "libc++ 没有遵循 ¶16 的建议"
    libc++ 每次调用 `environment()` 都用 `""` 重新构造 POSIX locale 再查询编码。本机实测，程序启动时输出 `US-ASCII`；调用 `setlocale(LC_ALL, "en_US.UTF-8")` 后仍是 `US-ASCII`，符合注 2；执行 `setenv("LC_ALL", "en_US.UTF-8", 1)` 后变成 `UTF-8`。¶16 只是建议，这不算不符合标准，但移植时两种行为都不要依赖。在 macOS 上，`environment()` 需要 LLVM 23 的 libc++ 动态库（可用性标注见 [[text]]）。

### *comp-name*：名字的宽松比较（¶19）

¶19 两个名字相等，当且仅当从左到右忽略以下内容后相同：

1. 所有既不是字母也不是数字的字符（¶19.1）；
2. 大小写（¶19.2）；
3. 任何不紧跟在数字前缀之后的连续 `0`。数字前缀指 1 到 9 中的一个数字，后面可以跟若干非字母数字的字符（¶19.3）。

注 3 说明这就是 UTS #22 的 Charset Alias Matching 算法。第 3 条去掉的是前导零：`utf-008` 中的 `00` 前面是 `-`，再往前是字母 `f`，不构成数字前缀，于是被忽略，得到 `utf8`；`utf-80` 的 `0` 跟在数字 `8` 之后，保留下来，得到 `utf80`。标准例 1：

| a | b | 结果 |
|---|---|---|
| `"UTF-8"` | `"utf8"` | true |
| `"u.t.f-008"` | `"utf8"` | true |
| `"ut8"` | `"utf8"` | false |
| `"utf-80"` | `"utf8"` | false |

## 比较 [text.encoding.cmp]

¶1 两个 `text_encoding` 比较时，如果两者都是 `other`，用 *comp-name* 比较名字；否则只比较 MIB。所以两个都叫 `"x-my-enc"`、`"X_MY_ENC"` 的未注册编码相等，而 `text_encoding("utf8") == text_encoding(text_encoding::UTF8)` 也为真，尽管名字不同。

¶2–¶3 与 `id` 比较时只比较 MIB。¶3 指出，`i == id::other` 时这个运算符不是等价关系：`a == other` 和 `b == other` 都为真，不能推出 `a == b`，因为名字可能不同。

## `aliases_view`、枚举 `id` 与散列

[text.encoding.aliases] ¶1–¶3 `aliases_view` 是可复制的 `view`，是 `random_access_range` 和 `borrowed_range`。别名字符串存放在静态表里，视图销毁后迭代器仍然有效。注 1 指出它不要求是 `common_range`，也不要求可默认构造。值类型和引用类型都是 `const char*`；迭代器是 constexpr 迭代器，可以在常量表达式里遍历别名。

[text.encoding.id] `id` 的底层类型是 `int_least32_t`。`other = 1`、`unknown = 2`，其余枚举值就是 IANA 的 MIB 编号，如 `ASCII = 3`、`UTF8 = 106`、`GB18030 = 114`、`UTF16 = 1015`。注 1 说明命名规则：取注册表中以 `cs` 开头的别名，去掉前缀；例外是 `csUnicode` 对应 `UCS2`，`csIBBM904`（注册表里的拼写错误）对应 `IBM904`。

[text.encoding.hash] ¶1 `hash<text_encoding>` 是启用的（[[unord.hash]]），`text_encoding` 可以直接作为无序容器的键。

## 常见误解

!!! pitfall "以为某个别名在所有实现上都能识别"
    别名集合是实现定义的超集，除 `"ASCII"` 外，标准没有要求任何额外的别名。一个名字在 A 实现上能识别为注册编码，在 B 实现上可能只得到 `other`。跨平台交换编码信息时，传 MIB 编号（`std::to_underlying(e.mib())`）或主名（`aliases().front()`）。

!!! pitfall "以为 `name()` 返回的是规范名"
    从名字构造时，`name()` 原样保存传入的字符串。需要规范的主名时用 `aliases().front()`。

## 小结

| 接口 | 求值时机 | 回答的问题 |
|---|---|---|
| `text_encoding::literal()` | `consteval` | 普通字面量用什么编码？（[[lex.charset]]） |
| `text_encoding::environment()` | 运行时 | 进程环境用什么编码？（POSIX 上是 `""` locale，不受 `setlocale` 影响） |
| `std::locale::encoding()` | 运行时 | 这个 `std::locale` 对象用什么编码？（[[locale.members]]） |
| `text_encoding(string_view)` | `constexpr` | 这个名字对应哪个注册编码？未注册则为 `other` |
