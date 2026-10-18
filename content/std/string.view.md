---
title: 字符串视图
summary: basic_string_view 逐条精读——"指针 + 长度"的非拥有只读视图；不保证 '\0' 终止的 data()、从临时对象构造导致的悬垂、五个构造函数的约束（nullptr 被删除、迭代器对、C++23 explicit range 构造函数及其排除条件）、比加固后的 string 更严的 operator[]、type_identity_t 让比较与隐式转换共存的技巧、hash 与 string 一致带来的异构查找，以及 sv 字面量
status: done
covers: *
papers: P0254R2, P0403R1, P1391R4, P1989R2, P2499R0, P2166R1, P2251R1, P0457R2, P1679R3, P3471R4, P0919R3, P1690R1
related: strings, char.traits, basic.string, string.classes, views.contiguous, class.temporary, range.range, over.match.oper, unord.hash, lex.string, structure.specifications
tags: 标准库, string_view, 悬垂, 加固, 视图
updated: 2026-10-18
---

`std::string_view` 是"`const char*` + 长度"的正式化：它不拥有字符，不分配内存，不保证终止符，拷贝它只是拷两个机器字。C++17 引入它（[[P0254R2]] 同时让 `std::string` 可以隐式转换为它），目的写在 [string.view.general] ¶2 的注里：

> 库提供从 `const charT*` 和 `std::basic_string` 到 `basic_string_view` 的隐式转换，以便用户代码只需接受 `basic_string_view<charT>` 这一个**非模板**参数类型。

也就是说，它首先是一个**参数类型**。以前 `void f(const std::string&)` 遇到字面量要先构造临时 `string`（可能分配内存），`void f(const char*)` 又丢了长度；`void f(std::string_view)` 两头都接，而且零开销。所有麻烦都出在把它用作**返回类型、成员变量或局部变量**的时候——那时你要自己保证被引用的字符活得够久。

它和 [[views.contiguous]] 里的 `std::span<const charT>` 几乎是同一个东西，区别在于 `string_view` 带 traits、有一整套查找/比较成员，而且元素只读。

## 概念模型（[string.view.general] ¶1）

!!! std
    The class template `basic_string_view` describes an object that can refer to a constant contiguous sequence of char-like objects with the first element of the sequence at position zero.

    `basic_string_view` 的对象**引用**一段**常量**、**连续**的 char-like 对象序列（[[g:char-like-type]]）。

三个关键词：*refer to*（不拥有）、*constant*（只读，所以 `iterator` 与 `const_iterator` 是同一个类型，脚注 190）、*contiguous*（可以用 `data()` 拿到裸指针）。

说明用成员（[string.view.template.general] 的类定义末尾）只有两个：

```cpp
const charT* data_;   // exposition only
size_type size_;      // exposition only
```

libc++ 正是这样实现的，本机 `sizeof(std::string_view) == 16`。

## 概要（[string.view.synop]）

几个值得注意的点：

- 头注释 `// mostly freestanding`：独立实现也提供 `string_view`；会抛异常的 `at`、`copy`、`substr`、`subview` 和带位置参数的 `compare` 被标为 *freestanding-deleted*，`operator<<` 被标为 *hosted*。
- `ranges::enable_view` 与 `ranges::enable_borrowed_range` 都特化为 `true`。后者意味着对**右值** `string_view` 调用 ranges 算法会返回真正的迭代器而不是 `ranges::dangling`（[[g:borrowed-range]]，[[range.range]]）——因为视图死了，字符还在。
- 比较运算符只有 `==` 和 `<=>` 两个，其余由重写候选（[[over.match.oper]]）生成；参数之一用 `type_identity_t` 包裹，见下文。
- 五个类型别名 `string_view`、`u8string_view`、`u16string_view`、`u32string_view`、`wstring_view`，对应五个 `hash` 特化。
- `sv` 字面量在 `std::literals::string_view_literals` 中（[[P0403R1]]）。
- ¶1：包含 `<string_view>` 即可使用 `std::swap`（[utility.swap]）和 `std::begin`/`std::size`/`std::data` 等（[iterator.range]）。

## 类模板的总体规定（[string.view.template.general]）

¶1：`traits` 必须满足字符 traits 要求（[[char.traits]]）；注：`traits::char_type` 与 `charT` 不同则非良构。

¶2 定义了**失效**的含义，这是整个视图语义的关键：

!!! std
    For a `basic_string_view` `str`, any operation that invalidates a pointer in the range `[str.data(), str.data() + str.size())` invalidates pointers, iterators, and references to elements of `str`.

    任何使 `[str.data(), str.data()+str.size())` 中的指针失效的操作，都会使 `str` 的元素的指针、迭代器和引用失效。

换句话说，`string_view` **没有自己的失效规则**，它完全继承被引用存储的命运：源 `string` 被销毁、被重新分配（见 [[basic.string]] 的 [string.require] ¶4）、源缓冲区被释放——视图里的一切同时失效。注意这条只说"元素的指针、迭代器和引用"失效，视图对象本身依然是一个合法对象：可以对它赋值，`size()` 也照样能读，只是不能再访问字符。

¶3：成员函数复杂度默认 O(1)，除非另有说明。

¶4：`basic_string_view<charT, traits>` 是**平凡可复制类型**（[[g:trivially-copyable-type]]）。这是 C++23 的 [[P2251R1]] 补上的规定（各实现原本就是如此，标准此前没有保证）。后果之一：在 Itanium C++ ABI 下按值传递 `string_view` 走两个寄存器，比 `const std::string&` 少一次间接寻址——这就是"`string_view` 按值传"的惯用法的 ABI 依据。

## 构造与赋值（[string.view.cons]）

类定义里列出的构造函数：

```cpp
constexpr basic_string_view() noexcept;
constexpr basic_string_view(const basic_string_view&) noexcept = default;
constexpr basic_string_view(const charT* str);
basic_string_view(nullptr_t) = delete;
constexpr basic_string_view(const charT* str, size_type len);
template<class It, class End> constexpr basic_string_view(It begin, End end);
template<class R> constexpr explicit basic_string_view(R&& r);
```

### 默认构造（¶1）

后置条件：`size_ == 0` 且 `data_ == nullptr`。所以 `std::string_view{}.data()` 是**空指针**，`printf("%s", sv.data())` 在这里是 {{ub}}（C 要求 `%s` 的实参指向一个字符串）。与之相对，`std::string{}.data()` 永远指向一个 `'\0'`。

### 从 `const charT*`（¶2–4）

前置条件：`[str, str + traits::length(str))` 是有效范围——即 `str` 指向一个以 `charT()` 终止的序列。效果：`size_ = traits::length(str)`，复杂度 O(length)。

这有两个后果：

1. 内嵌的 `'\0'` 会截断：`std::string_view sv = "abc\0def";` 的 `size()` 是 3，而 `"abc\0def"sv` 的 `size()` 是 7（字面量运算符拿到的是数组的完整长度，见 [[over.literal]]）。
2. 从字符**数组**构造时，走的也是这个构造函数（数组退化为指针），**不是** range 构造函数：

```cpp run ok
#include <string_view>
#include <array>
#include <cassert>

int main() {
  char buf[8] = "ab";
  std::array<char, 4> arr{'x', 'y', 'z', 'w'};
  assert(std::string_view{buf}.size() == 2);   // const char*：strlen 语义
  assert(std::string_view{arr}.size() == 4);   // range：整个 array
}
```

`buf` 能隐式转换为 `const char*`，所以被 range 构造函数的 ¶12.4 排除（见下文）。这是有意为之：字符数组几乎总是被当作 C 字符串使用，把尾部的 `'\0'` 和未用空间都算进视图会出乎所有人的意料。

### 从 `nullptr`：被删除 {{c++23}}

`basic_string_view(nullptr_t) = delete;` 来自 [[P2166R1]]。以前 `std::string_view sv = nullptr;` 能编译（走 `const charT*` 构造函数），然后在 `traits::length(nullptr)` 里崩溃——违反 ¶2 的前置条件，{{ub}}。现在它在编译期被拒绝：

```cpp error
#include <string_view>
std::string_view sv = nullptr;   // error: invokes a deleted function
```

注意这只拦得住字面的 `nullptr`。一个值为空的 `const char*` 变量照样能通过编译，然后违反前置条件。

### 从指针 + 长度（¶5–6）

前置条件：`[str, str + len)` 有效。**不要求**终止符，也不检查内嵌 `'\0'`。`str` 可以为空指针，只要 `len == 0`（`[nullptr, nullptr)` 是有效的空范围）。

### 从迭代器对（¶7–10）{{c++20}}

[[P1391R4]] 加入。约束（¶7）：

- ¶7.1 `It` 满足 `contiguous_iterator`；
- ¶7.2 `End` 满足 `sized_sentinel_for<It>`；
- ¶7.3 `iter_value_t<It>` 就是 `charT`；
- ¶7.4 `End` **不能**转换为 `size_type`。

¶7.4 是为了避免与 `(const charT*, size_type)` 争抢：`string_view(p, 5)` 中 `int` 如果能当作哨兵类型推导，就会出现歧义或选错重载。¶8 的前置条件要求这些概念被**建模**（不仅语法满足），¶9：`data_ = to_address(begin)`、`size_ = end - begin`。

推导指引（[string.view.deduct] ¶1）：`basic_string_view(It, End) -> basic_string_view<iter_value_t<It>>`。

### 从 range（¶11–14）{{c++23}}

这是被讨论得最多的一个构造函数。它由 [[P1989R2]] 加入 C++23，又在 C++23 定稿前由 [[P2499R0]] 改为 **`explicit`**。约束（¶12，其中 `d` 是 `remove_cvref_t<R>` 类型的左值）：

| 条款 | 约束 | 目的 |
|---|---|---|
| ¶12.1 | `remove_cvref_t<R>` 不是 `basic_string_view` | 不劫持拷贝构造 |
| ¶12.2 | `R` 建模 `contiguous_range` 与 `sized_range` | 能取得 `data()`/`size()` |
| ¶12.3 | `range_value_t<R>` 是 `charT` | 不做元素类型转换 |
| ¶12.4 | `R` **不能**转换为 `const charT*` | 字符数组走 C 字符串语义（见上） |
| ¶12.5 | `d.operator ::std::basic_string_view<charT, traits>()` 不是有效表达式 | 自带转换函数的类型（例如 `std::string`）走自己的转换函数 |

¶12.5 的作用往往被忽略：`std::string` 有 `operator basic_string_view()`（[string.accessors] ¶3），于是 `string → string_view` 永远走那个**隐式**转换函数，而不是这个 `explicit` 构造函数。它还有一个更微妙的效果——traits 不同时（例如 `basic_string<char, ci_traits>` 转 `std::string_view`），转换函数的目标类型不匹配，¶12.5 不再排除，于是**显式**的 range 构造函数可以把它转过来。

**为什么要 `explicit`？** 因为"连续的字符 range"不等于"字符串"。`std::vector<char>` 可能是一段以 `'\0'` 结尾的 C 缓冲区，也可能是二进制数据；`std::array<char, 16>` 可能只用了前几个字节。隐式转换会让 `f(std::string_view)` 悄悄接受这些东西，而它们的长度语义（"包括尾部的零"）与字符串的直觉不同：

```cpp run ok
#include <string_view>
#include <vector>
#include <cassert>

int main() {
  std::vector<char> v{'a', 'b', '\0'};
  // std::string_view s1 = v;     // error: explicit
  std::string_view s2{v};          // OK：直接初始化
  assert(s2.size() == 3);          // 尾部的 '\0' 也算在内
}
```

¶12 的约束里**没有** `borrowed_range`。这与 `std::span` 不同（[[views.contiguous]] 的 range 构造函数要求右值 range 是 borrowed 的，或者元素是 const 的——而 `string_view` 的元素本来就是 const）。所以下面的代码能编译，并立刻悬垂：

```cpp ub
#include <string_view>
#include <vector>
std::string_view x{std::vector<char>{'a', 'b'}};   // UB 隐患：临时 vector 在完整表达式结束时销毁
```

推导指引（[string.view.deduct] ¶2）：`basic_string_view(R&&) -> basic_string_view<range_value_t<R>>`，约束只要求 `contiguous_range`。

## 迭代器、容量、元素访问

**迭代器**（[string.view.iterators]）：¶1 `const_iterator` 是实现定义的类型，满足常量 *Cpp17RandomAccessIterator*、建模 `contiguous_iterator`、满足 constexpr 迭代器要求；¶2 容器迭代器的全部要求（[[container.requirements]]）同样适用。¶3：非空时 `addressof(*begin()) == data_`；**空时 `begin()` 是一个未指明的值**，只保证 `[begin(), end())` 是有效范围——所以不要假定空视图的 `begin()` 能还原出 `data()`。libc++ 的迭代器就是 `const char*`。

**容量**（[string.view.capacity]）：`size()`/`length()` 返回 `size_`；`max_size()` 是能引用的最大字符数；`empty()`。

**元素访问**（[string.view.access]）——这里有 C++26 的加固（[[P3471R4]]，*Hardened preconditions* 的含义见 [[structure.specifications]]）：

| 成员 | 前置条件 | 失败时 |
|---|---|---|
| `operator[](pos)` | 加固：`pos < size()` | 加固实现中为契约违反，否则 {{ub}} |
| `at(pos)` | — | 抛 `out_of_range` |
| `front()`/`back()` | 加固：`!empty()` | 同上 |
| `data()` | — | — |

!!! note "比 `string::operator[]` 更严"
    ¶1 的注明确指出：这个前置条件比 `basic_string::operator[]` 的更强。`string` 允许 `s[s.size()]`（返回终止符的引用），`string_view` 不允许 `sv[sv.size()]`——视图后面不一定有字符。

在 libc++ 中，加固模式由宏 `_LIBCPP_HARDENING_MODE` 选择（本机默认为 none）。用 fast 模式编译 `sv[3]`（`sv == "abc"`），程序在越界处以陷阱指令终止（本机退出码 133，即 SIGTRAP）；默认模式下则读出字面量的终止符 0 并"正常"运行——这正是 UB 最危险的样子。

### `data()` 不保证终止（¶12–13）

!!! std
    Unlike `basic_string::data()` and *string-literal*s, `data()` can return a pointer to a buffer that is not null-terminated. Therefore it is typically a mistake to pass `data()` to a function that takes just a `const charT*` and expects a null-terminated string.

    `data()` 返回的缓冲区**可以不以空字符终止**。把它交给只接受 `const charT*` 并期待 C 字符串的函数，通常是错误的。

这是一条注（不具规范效力），但它总结的是规范内容的直接后果：

```cpp run
#include <string_view>
#include <cstdio>
#include <cstdlib>

int main() {
  std::string_view whole = "1234567";
  std::string_view part = whole.substr(0, 3);    // "123"
  std::printf("%d\n", std::atoi(part.data()));   // 打印 1234567，而不是 123
  std::printf("%.*s\n", static_cast<int>(part.size()), part.data());  // 正确：显式长度
}
```

这段代码没有 UB（`whole` 来自字面量，后面确实有终止符），但结果错了；如果 `part` 引用的是一个没有终止符的缓冲区，`atoi` 就会越界读，成为 {{ub}}。需要 C 字符串时只有两条路：用带长度的 API（`printf("%.*s")`、`fwrite`、`std::from_chars`），或者构造一个 `std::string`。

## 修改器（[string.view.modifiers]）

修改的是**视图**而不是字符：

- `remove_prefix(n)`：加固前置条件 `n <= size()`，效果 `data_ += n; size_ -= n;`；
- `remove_suffix(n)`：加固前置条件 `n <= size()`，效果 `size_ -= n;`；
- `swap(s)`：交换两个视图。

## 字符串操作（[string.view.ops]）

**`copy(s, n, pos)`**（¶1–6）：复制 `min(n, size() - pos)` 个字符到 `s`，返回复制数；`pos > size()` 抛 `out_of_range`。**不写终止符**。

**`substr(pos, n)` 与 `subview(pos, n)`**（¶7–10）：返回 `basic_string_view(data() + pos, rlen)`，`rlen = min(n, size() - pos)`；`pos > size()` 抛 `out_of_range`。注意：

- `pos == size()` 合法，返回空视图；
- `n` 可以超过剩余长度，自动截断；
- 结果和原视图引用**同一块存储**，不复制字符；
- `subview` 是工作草案在 C++26 之后新增的同义成员，存在的意义在 `basic_string` 那边：`string::substr` 返回 `string`（复制），`string::subview` 返回 `string_view`（不复制），给 `string_view` 也加上 `subview` 是为了让泛型代码能对两者用同一个名字。

**`compare`**（¶11–19）：核心是 ¶12——用 `traits::compare(data(), str.data(), rlen)` 比较前 `rlen = min(size(), str.size())` 个字符，非零就返回它；为零时按 Table 88 由长度决定（短的小）。其余重载都是 `substr(...).compare(...)` 的简写，所以带位置参数的版本会抛 `out_of_range`。`compare(basic_string_view)` 是 `noexcept` 的。

**`starts_with`/`ends_with`**（¶20–27，C++20，[[P0457R2]]）与 **`contains`**（¶28，C++23，[[P1679R3]]）：

- `starts_with(x)` 等价于 `basic_string_view(data(), min(size(), x.size())) == x`；
- `starts_with(charT)` 等价于 `!empty() && traits::eq(front(), x)`——空视图返回 `false`，**不会**违反 `front()` 的前置条件；
- `contains(x)` 等价于 `find(x) != npos`。

接受 `basic_string_view` 和 `charT` 的版本是 `noexcept`，接受 `const charT*` 的版本不是（它要先构造视图，有前置条件）。

## 查找（[string.view.find]）

¶1：最坏复杂度 O(`size() * str.size()`)，"although implementations should do better"。¶2 把所有 `const charT*`、`(const charT*, n)`、`charT` 重载归结为 `basic_string_view` 版本。六个函数的定义（¶3–20）形式完全一样：找满足条件的最低/最高位置 `xpos`，找不到返回 `npos`。

| 函数 | 方向 | `xpos` 条件 |
|---|---|---|
| `find` | 最低，`xpos >= pos` | 子串匹配 |
| `rfind` | 最高，`xpos <= pos` | 子串匹配 |
| `find_first_of` | 最低 | `data_[xpos]` 等于 `str` 中**某个**字符 |
| `find_last_of` | 最高 | 同上 |
| `find_first_not_of` | 最低 | `data_[xpos]` 不等于 `str` 中**任何**字符 |
| `find_last_not_of` | 最高 | 同上 |

边界：

- `find("", pos)`：当 `pos <= size()` 时返回 `pos`（空串在任何位置都匹配，条件 ¶3.2 `pos + 0 <= size()`）；`pos > size()` 返回 `npos`。**查找函数从不抛异常**，`pos` 越界只是找不到。
- `rfind` 的 `pos` 是"匹配起点的上界"，不是"搜索区间的终点"，所以 `rfind(x, pos)` 可以找到跨过 `pos` 的匹配。
- `find_first_of(charT)` 与 `find(charT)` 等价。

## 比较运算符（[string.view.comparison]）

```cpp
template<class charT, class traits>
  constexpr bool operator==(basic_string_view<charT, traits> lhs,
                            type_identity_t<basic_string_view<charT, traits>> rhs) noexcept;
template<class charT, class traits>
  constexpr see below operator<=>(basic_string_view<charT, traits> lhs,
                                  type_identity_t<basic_string_view<charT, traits>> rhs) noexcept;
```

¶1：`==` 返回 `lhs.compare(rhs) == 0`。¶2–4：`<=>` 的结果类型 `R` 是 `traits::comparison_category`（若存在），否则 `weak_ordering`；*Mandates* `R` 是比较类别类型；返回 `static_cast<R>(lhs.compare(rhs) <=> 0)`。

**为什么第二个参数要包 `type_identity_t`？** ¶5 的注解释了：要让 `string_view` 能和"任何可隐式转换为 `string_view` 的类型"比较。模板实参推导不考虑隐式转换（[[temp.deduct.call]]），所以如果两个参数都是 `basic_string_view<charT, traits>`，`sv == "abc"` 会推导失败（`const char*` 推不出 `charT`）。`type_identity_t<...>` 把第二个参数变成**非推导语境**（[[g:non-deduced-context]]），`charT`/`traits` 只从 `lhs` 推导，`rhs` 就可以经隐式转换匹配。

那 `"abc" == sv` 呢？C++20 的重写候选会把它当作 `sv == "abc"` 再试一次（[[over.match.oper]]），所以一个模板足够覆盖两个方向。C++17 时代标准用一句"实现应提供足够多的额外重载"来解决这个问题，C++20 换成了这种显式写法。

```cpp run ok
#include <string>
#include <string_view>
#include <cassert>
using namespace std::literals;

int main() {
  std::string s = "abc";
  assert("abc"sv == "abc");     // const char* → string_view
  assert("abc" == "abc"sv);     // 重写候选：交换参数
  assert("abc"sv == s);         // string 的转换函数
  assert(("abc"sv <=> "abd"sv) < 0);
}
```

## 流输出（[string.view.io]）

¶1：作为格式化输出函数（[[ostream.formatted.reqmts]]）：按 `os.width()` 填充，写出 `max(os.width(), str.size())` 个字符，然后 `os.width(0)`。它按长度输出，**内嵌的 `'\0'` 会原样写出**，不会被截断。

## 哈希（[string.view.hash]）

¶1：五个 `hash` 特化都是启用的（[[unord.hash]]）。注：字符串视图的哈希值等于对应字符串对象的哈希值（[basic.string.hash] 的规范条款保证 `hash<S>()(s) == hash<SV>()(SV(s))`）。

这条等式是**异构查找**（C++20，[[P0919R3]]、[[P1690R1]]）的基础：`unordered_map<std::string, V>` 想用 `string_view` 查找而不构造临时 `string`，需要一个透明的哈希器——而它可以直接委托给 `hash<string_view>`，因为结果与 `hash<string>` 一致：

```cpp run ok
#include <string>
#include <string_view>
#include <unordered_map>
#include <functional>
#include <cassert>
using namespace std::literals;

struct string_hash {
  using is_transparent = void;
  std::size_t operator()(std::string_view s) const noexcept {
    return std::hash<std::string_view>{}(s);
  }
};

int main() {
  std::unordered_map<std::string, int, string_hash, std::equal_to<>> m{{"key", 1}};
  assert(m.find("key"sv)->second == 1);   // 不构造临时 std::string
}
```

注意只有标准的五种字符类型、默认 traits 的视图有 `hash` 特化；`basic_string_view<char, ci_traits>` 没有。

## `sv` 字面量（[string.view.literals]）

¶1–5：`operator""sv(const charT* str, size_t len)` 返回 `basic_string_view{str, len}`。`len` 是字面量数组长度减一（不含末尾的终止符，但**包含**内嵌的 `'\0'`）。字面量对象具有静态存储期（[[lex.string]]），所以 `"..."sv` 永远不会悬垂——这是返回 `string_view` 最安全的写法。

## 悬垂：string_view 的头号事故

`string_view` 的所有危险都可以归结为一句话：**它不延长任何东西的生命周期**。引用绑定临时对象时的生命周期延长（[[class.temporary]]）只对引用有效，`string_view` 是类类型，从临时 `string` 构造它只是调用了 `string` 的转换函数，临时对象照常在完整表达式结束时销毁。

```cpp
std::string make();

void f(std::string_view);
f(make());                                   // OK：临时对象活到 f 返回之后

std::string_view a = make();                 // 悬垂
std::string_view b = std::string("x") + "y"; // 悬垂
std::string_view c = "abc"s;                 // 悬垂：s 字面量产生临时 string
std::string_view d = "abc";                  // OK：字面量是静态存储期

std::string_view g() {
  std::string s = "local";
  return s;                                  // 悬垂：返回局部 string 的视图
}
```

Clang 对上面的 `a`/`b`/`c`/`g` 都会给出警告（`-Wdangling-gsl`、`-Wreturn-stack-address`，默认开启），因为 Clang 内置了一份标准库类型清单，自动把 `std::string_view` 当作"指针类"（`gsl::Pointer`）类型、把 `std::string` 当作"所有者"（`gsl::Owner`）类型。但只要中间隔一层函数，编译器就看不见了：

```cpp run ub
#include <string>
#include <string_view>
#include <iostream>

std::string_view trim(std::string_view s) {          // 返回实参的子视图
  while (!s.empty() && s.front() == ' ') s.remove_prefix(1);
  return s;
}
std::string read_line() { return "   a line long enough to avoid SSO, really"; }

int main() {
  std::cout << trim(read_line()) << '\n';            // OK：临时对象活到完整表达式结束
  std::string_view v = trim(read_line());            // 悬垂：临时 string 已销毁，没有警告
  std::cout << v << '\n';                            // UB：AddressSanitizer 报 heap-use-after-free
}
```

Clang 的扩展属性 `[[clang::lifetimebound]]` 可以把这层关系告诉编译器：把 `trim` 的形参声明为 `std::string_view s [[clang::lifetimebound]]` 之后，第二行同样会触发 `-Wdangling-gsl`。

!!! pitfall "短字符串让 bug 隐身"
    如果 `read_line()` 返回的是短字符串（libc++ 中 ≤ 22 个 `char`），字符存放在 `string` 对象内部（SSO，见 [[basic.string]]）。临时对象在栈上，销毁后那块栈内存可能原封不动，AddressSanitizer 也未必报告。"测试时没问题"在这里毫无意义。

### 把 `string_view` 存起来的守则

- 作为**参数**：总是安全的（调用者的实参活到调用结束）。
- 作为**返回值**：只在返回的是参数的子视图（调用者负责）或静态存储（字面量、静态对象）时安全。
- 作为**成员**：对象的生命周期必须被被引用对象完全覆盖。容器里存 `string_view` 是常见的悬垂来源。
- 遇到 `auto`：`auto x = s.subview(1);` 推导出 `string_view`，而 `auto x = s.substr(1);` 推导出 `string`——两者的生命周期语义完全不同。

## 思考题

!!! question "1. `std::string_view sv = std::string(\"hi\"); std::cout << sv.size();` 有 UB 吗？"

<details markdown="1">
<summary>展开查看答案与解析</summary>

没有。`sv` 的 `size_` 是在构造时从临时 `string` 复制来的普通整数，读取它不访问被销毁的存储。[string.view.template.general] ¶2 只让"元素的指针、迭代器和引用"失效；`size()` 返回成员值，与元素无关。但 `sv.data()` 返回的指针此时是无效指针值（[[g:invalid-pointer-value]]），解引用它（包括 `sv[0]`、`sv.front()`、输出 `sv`）才是 {{ub}}。这类"能编译、读 size 正常"的视图正是悬垂 bug 难以发现的原因。

</details>

!!! question "2. `void f(std::string_view); std::vector<char> v; f(v);` 能编译吗？`f(std::string_view(v))` 呢？"

<details markdown="1">
<summary>展开查看答案与解析</summary>

`f(v)` 非良构：形参是拷贝初始化，需要隐式转换，而 range 构造函数是 `explicit` 的（[[P2499R0]]），`vector` 也没有到 `string_view` 的转换函数。`f(std::string_view(v))` 合法：函数式转换是直接初始化，可以调用 `explicit` 构造函数；`vector<char>` 满足 ¶12 的全部约束（连续、有大小、值类型为 `char`、不能转换为 `const char*`、没有 `operator string_view`）。

</details>

!!! question "3. 为什么 `string_view::operator[]` 的前置条件是 `pos < size()`，而 `string::operator[]` 是 `pos <= size()`？"

<details markdown="1">
<summary>展开查看答案与解析</summary>

`basic_string` 有不变式：`data() + size()` 指向一个值为 `charT()` 的对象（[basic.string.general] ¶3），所以 `s[s.size()]` 有东西可读。`basic_string_view` 没有这个不变式——它可能引用 `"hello"` 的前三个字符，`sv[3]` 读到的是 `'l'` 而不是终止符；也可能引用一个缓冲区的末尾，`sv[size()]` 越界。[string.view.access] ¶1 的注专门指出了这一差别。

</details>

## 小结

| 主题 | 规则 |
|---|---|
| 本质 | `const charT*` + 长度，不拥有，平凡可复制（¶4），按值传 |
| 默认构造 | `data() == nullptr`，`size() == 0` |
| 从 `const charT*` | 用 `traits::length`，内嵌 `'\0'` 截断；字符数组也走这里 |
| 从 `nullptr` | 删除（C++23） |
| 从 range | `explicit`（C++23）；排除可转 `const charT*` 的类型和自带转换函数的类型；**不要求** borrowed |
| `data()` | 不保证 `'\0'` 终止；不要交给 C 字符串接口 |
| `operator[]` | 加固前置条件 `pos < size()`，比 `string` 严 |
| `substr`/`subview` | 不复制，`pos > size()` 抛 `out_of_range` |
| 查找 | 从不抛；找不到返回 `npos` |
| 比较 | 第二参数 `type_identity_t`，配合重写候选覆盖双向隐式转换 |
| 哈希 | 与对应 `string` 相同，支持异构查找 |
| 生命周期 | 不延长任何对象；临时 `string`、`""s`、局部变量是三大悬垂来源 |
